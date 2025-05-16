FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg git

# Set work directory
WORKDIR /backend

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/
COPY alembic alembic
COPY alembic.ini .

# Expose port
EXPOSE 8000

# Run the FastAPI backend
CMD ["uvicorn", "backend.main:backend", "--host", "0.0.0.0", "--port", "8000"]
