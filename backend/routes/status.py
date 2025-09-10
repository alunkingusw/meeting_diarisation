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

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from datetime import datetime
import os

from backend.db import SessionLocal
from backend.startup import START_TIME

router = APIRouter()
HUGGING_FACE_TOKEN = os.getenv("HUGGING_FACE_TOKEN")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    uptime = datetime.now().astimezone() - START_TIME if START_TIME else "Unknown"
    models = check_model_status()

    # Check PostgreSQL connection
    try:
        db.execute(text('SELECT 1'))  # Lightweight DB health check
        db_status = "connected"
    except SQLAlchemyError as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "ok",
        "uptime": str(uptime),
        "models": models,
        "database": db_status
    }

@router.get("/gpu-status")
def get_gpu_status():
    import torch

    if not torch.cuda.is_available():
        return {"cuda_available": False, "message": "CUDA not available."}

    device_index = torch.cuda.current_device()
    device_name = torch.cuda.get_device_name(device_index)
    memory_allocated = torch.cuda.memory_allocated(device_index)
    memory_reserved = torch.cuda.memory_reserved(device_index)
    total_memory = torch.cuda.get_device_properties(device_index).total_memory

    # Capability of the current GPU (e.g. GTX 1070 → (6, 1))
    device_capability = torch.cuda.get_device_capability(device_index)

    # Architectures supported by the installed PyTorch build
    supported_arches = torch.cuda.get_arch_list()

    return {
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "device_index": device_index,
        "device_name": device_name,
        "device_capability": f"sm_{device_capability[0]}{device_capability[1]}",
        "supported_arches": supported_arches,
        "is_compatible": f"sm_{device_capability[0]}{device_capability[1]}" in supported_arches,
        "memory_allocated_MB": round(memory_allocated / 1024**2, 2),
        "memory_reserved_MB": round(memory_reserved / 1024**2, 2),
        "total_memory_MB": round(total_memory / 1024**2, 2),
    }

def check_model_status():
    status = {}

    # Whisper check
    try:
        import whisper
        model = whisper.load_model("base")
        status["whisper_model"] = {
            "status": "available",
            "version": whisper.__version__ if hasattr(whisper, "__version__") else "unknown"
        }
    except Exception as e:
        status["whisper_model"] = {
            "status": f"unavailable ({str(e)})",
            "version": "unknown"
        }

    # PyAnnote diarisation check
    try:
        from pyannote.audio import Pipeline
        import pyannote
        Pipeline.from_pretrained("pyannote/speaker-diarization", use_auth_token=HUGGING_FACE_TOKEN)
        status["pyannote_diarization"] = {
            "status": "available",
            "version": pyannote.__version__ if hasattr(pyannote, "__version__") else "unknown"
        }
    except Exception as e:
        status["pyannote_diarization"] = {
            "status": f"unavailable ({str(e)})",
            "version": "unknown"
        }

    # PyAnnote embedding model check
    try:
        from pyannote.audio import Inference
        Inference("pyannote/embedding", use_auth_token=HUGGING_FACE_TOKEN)
        status["pyannote_embedding"] = {
            "status": "available",
            "version": "included with pyannote.audio"
        }
    except Exception as e:
        status["pyannote_embedding"] = {
            "status": f"unavailable ({str(e)})",
            "version": "unknown"
        }

    # Torch and CUDA status
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        device_name = torch.cuda.get_device_name(0) if cuda_available else "CPU"

        status["torch"] = {
            "version": torch.__version__,
            "cuda_available": cuda_available,
            "device": device_name,
            "info": "See /gpu-status endpoint for more details" if cuda_available else ""
        }
    except Exception as e:
        status["torch"] = {
            "version": "unknown",
            "cuda_available": False,
            "device": f"unavailable ({str(e)})"
        }

    return status
