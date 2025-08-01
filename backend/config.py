from pydantic_settings import BaseSettings
from pydantic import PrivateAttr
from pathlib import Path
import os

class Settings(BaseSettings):
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