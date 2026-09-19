"""Turns retrieved transcript chunks (app/diarisation/client.py::TranscriptChunk) into a short
prose answer, citing sources. Deliberately narrow and separate from llm/prompt.py's command-
parsing system prompt: this is the one place in the codebase where LLM output becomes email
content sent to a user, rather than a structured command re-validated before anything acts on
it, so the prompt is constrained to summarising the given chunks only - never inventing facts
or citations beyond what was actually retrieved.
"""
from __future__ import annotations

from typing import Protocol

from app.diarisation.client import TranscriptChunk

SYSTEM_PROMPT = """You answer questions about past meetings using ONLY the transcript excerpts
given to you below - never information from anywhere else, and never a fact not directly
supported by one of the excerpts.

Cite the source of every factual claim using the format
[Meeting Title, YYYY-MM-DD, HH:MM:SS-HH:MM:SS, Speaker Name] exactly as given with each excerpt.

If the excerpts don't actually answer the question, say so plainly rather than guessing or
padding the answer - a short, honest "the transcripts I found don't cover this" is a correct
answer. Keep the answer to a few sentences."""


class GeneratesText(Protocol):
    def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.0, json_mode: bool = True
    ) -> str: ...


def synthesize_transcript_answer(
    ollama_client: GeneratesText, question: str, chunks: list[TranscriptChunk]
) -> str:
    if not chunks:
        return "I didn't find anything in past transcripts that speaks to this."

    excerpts = "\n\n".join(f"{c.citation()}\n{c.text}" for c in chunks)
    user_prompt = f"Question: {question}\n\nTranscript excerpts:\n\n{excerpts}"
    return ollama_client.generate(SYSTEM_PROMPT, user_prompt, json_mode=False).strip()
