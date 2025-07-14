FROM python:3.10-slim

ARG HUGGING_FACE_TOKEN
ENV HUGGING_FACE_TOKEN=${HUGGING_FACE_TOKEN}

#set model locations for cache (we set them offline later)
ENV XDG_CACHE_HOME=/models
ENV TRANSFORMERS_CACHE=/models/hf
ENV PYANNOTE_CACHE=/models/pyannote

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg git libsndfile1 build-essential \
    libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Install torch and other related tools. Version is set for cache
# Optional: GPU support setup
# ENV PYTORCH_ENABLE_MPS_FALLBACK=1
# RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
# otherwise install CPU support
RUN pip install torch torchvision torchaudio

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

#download and install a local version of Whisper
RUN python3 -c "import whisper; whisper.load_model('base')"

# Pre-download PyAnnote diarization pipeline model
RUN python3 -c "from pyannote.audio import Pipeline; Pipeline.from_pretrained('pyannote/speaker-diarization')"

# Pre-download embedding model
RUN python3 -c "from pyannote.audio import Model; Model.from_pretrained('pyannote/embedding', use_auth_token=['HUGGING_FACE_TOKEN'])"

#set models to run offline, to ensure data security
#ENV TRANSFORMERS_OFFLINE=1
#ENV HF_DATASETS_OFFLINE=1
ENV WANDB_MODE=offline


# Set work directory
WORKDIR /backend

# Copy backend code
COPY backend/ ./backend/
COPY alembic alembic
COPY alembic.ini .

# Expose port
EXPOSE 8000

# Run the FastAPI backend
CMD ["uvicorn", "backend.main:backend", "--host", "0.0.0.0", "--port", "8000"]
