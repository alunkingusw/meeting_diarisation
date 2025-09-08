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
    
    # this is the default value, overridden by the value in .env
    UPLOAD_DIR: Path = Path("/backend/uploads")
    

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