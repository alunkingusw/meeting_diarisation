# Group Meeting Transcription Platform

A full-stack application for uploading and diarising group meeting audio files using FastAPI, PostgreSQL, Alembic, and a React (Next.js) frontend. The backend handles audio processing and diarisation logic, while the frontend allows users to manage and explore their meeting data.

---

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy, Alembic
- **Database:** PostgreSQL + pgAdmin
- **Frontend:** Next.js (React + TypeScript)
- **Containerisation:** Docker + Docker Compose
- **Environment Management:** `python-dotenv`

---

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/group-meeting-transcripts.git
cd group-meeting-transcripts

### 2. Create a .env file
# .env
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POSTGRES_DB=diarisation_db
POSTGRES_PORT=5432
POSTGRES_HOST=db

PGADMIN_DEFAULT_EMAIL=admin@example.com
PGADMIN_DEFAULT_PASSWORD=admin

### 3. Start the project with Docker Compose
docker-compose up --build

This will:

Build the FastAPI app (web)

Run PostgreSQL (db)

Run pgAdmin (pgadmin)

Run frontend (frontend) if enabled

Automatically apply Alembic migrations on startup

