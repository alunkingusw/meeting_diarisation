from pydantic import BaseSettings
import os

class Settings(BaseSettings):
    UPLOAD_DIR: str = "backend/uploads"
    BASE_UPLOAD_URL: str = "https://yourdomain.com/uploads"  # HTTP base URL

    # Sub-paths built from the base path, built on initialisation
    EMBEDDING_DIR: str = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.EMBEDDING_DIR = os.path.join(self.UPLOAD_DIR, "embeddings")

    class Config:
        env_file = ".env"


settings = Settings()