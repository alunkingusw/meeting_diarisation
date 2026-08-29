# Copyright 2025 Alun King
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Client for an Ollama server, used for meeting summarisation
(backend/summarization). Mirrors GitHub-RAGinator's own
app/llm/ollama_client.py, which talks to the same server - kept as a
separate copy rather than a shared import since the two projects don't
share a Python package.

Ollama typically runs on a *different* machine to this API (set
OLLAMA_BASE_URL to its address, e.g. http://192.168.1.50:11434). It is
unauthenticated by default, so that setting is a network address rather
than a credential - there is no API key to configure.
"""

from dataclasses import dataclass

import httpx

from backend.config import settings


class OllamaError(RuntimeError):
    """Raised when the Ollama server is unreachable or returns an error."""


@dataclass
class LLMAnswer:
    """A generated answer plus the accounting needed to report on the call."""

    text: str
    model: str
    prompt_eval_count: int | None = None
    eval_count: int | None = None


class OllamaClient:
    """
    Thin wrapper over the two Ollama endpoints this project needs:
    `/api/chat` for generation and `/api/tags` for a health check.

    Usable as a context manager:

        with OllamaClient() as llm:
            answer = llm.chat(system_prompt="...", user_prompt="...")
    """

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_model
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=settings.ollama_timeout_seconds,
        )

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def health(self) -> dict:
        """Check the server is reachable and report whether the configured model
        is actually present on it."""
        try:
            response = self._client.get("/api/tags", timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaError(
                f"Could not reach Ollama at {self._base_url}: {exc}. "
                "Check OLLAMA_BASE_URL in .env, that the server is running, and that "
                "it listens on a non-loopback address (OLLAMA_HOST=0.0.0.0) if it is "
                "on another machine."
            ) from exc

        available = [m.get("name", "") for m in response.json().get("models", [])]
        # Ollama reports "llama3.1:8b"; tolerate a configured name without a tag.
        model_present = any(
            name == self._model or name.split(":")[0] == self._model.split(":")[0]
            for name in available
        )
        return {
            "base_url": self._base_url,
            "reachable": True,
            "configured_model": self._model,
            "model_available": model_present,
            "available_models": available,
        }

    def chat(self, system_prompt: str, user_prompt: str) -> LLMAnswer:
        """Send a single-turn chat completion and return the generated text.

        `stream: false` so the whole answer arrives as one JSON response -
        simpler for an API that returns a single JSON body."""
        payload = {
            "model": self._model,
            "stream": False,
            "options": {"temperature": settings.ollama_temperature},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            response = self._client.post("/api/chat", json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise OllamaError(
                f"Ollama timed out after {settings.ollama_timeout_seconds:.0f}s. "
                "Large models on CPU can exceed this - raise OLLAMA_TIMEOUT_SECONDS "
                "or use a smaller model."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip()
            raise OllamaError(
                f"Ollama returned {exc.response.status_code}: {detail}. "
                f"If the model is missing, run `ollama pull {self._model}` on the "
                "Ollama host."
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaError(f"Could not reach Ollama at {self._base_url}: {exc}") from exc

        body = response.json()
        text = (body.get("message") or {}).get("content", "").strip()
        if not text:
            raise OllamaError("Ollama returned an empty response.")

        return LLMAnswer(
            text=text,
            model=body.get("model", self._model),
            prompt_eval_count=body.get("prompt_eval_count"),
            eval_count=body.get("eval_count"),
        )
