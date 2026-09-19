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

from pydantic_settings import BaseSettings
from pydantic import PrivateAttr
from pathlib import Path
import os

class Settings(BaseSettings):
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: str
    pgadmin_default_email: str
    pgadmin_default_password: str
    secret_key: str
    hugging_face_token: str
    email_api_token: str = ""
    email_api_url: str = "http://agent:8080/internal/email"
    email_timeout_seconds: float = 10.0
    
    # this is the default value, overridden by the value in .env
    UPLOAD_DIR: Path = Path("/backend/uploads")

    # Transcript RAG indexing (backend/transcript_rag) - Chroma persist dir and the local
    # sentence-transformers model used to embed transcript chunks, same defaults GitHub-RAGinator
    # uses for its own Chroma indexing so the two projects' embeddings stay comparable.
    TRANSCRIPT_CHROMA_DIR: Path = Path("/backend/transcript_chroma")
    TRANSCRIPT_EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"
    TRANSCRIPT_EMBEDDING_DEVICE: str = "cpu"

    # Local LLM (backend/llm/ollama_client.py) used for meeting summarisation
    # (backend/summarization). Same server/conventions as GitHub-RAGinator's own
    # OLLAMA_* settings - see that project's app/llm/ollama_client.py.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout_seconds: float = 300.0
    ollama_temperature: float = 0.2


    # Sub-paths built from the base path, built on initialisation
    _embedding_dir: Path = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._embedding_dir = self.UPLOAD_DIR / "embeddings"

    @property
    def EMBEDDING_DIR(self) -> Path:
        return self._embedding_dir
    
    class Config:
        env_file = ".env"


settings = Settings()