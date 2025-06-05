# Group Meeting Transcription Platform

This application is developed as part of my research into improved supervision of gruop projects. You can read more about my research by following my ResearchGate profile (link at bottom of page).

This full stack application is developed to help manage groups who are working together on a project. Currently the application allows you to manage:
- multiple groups
- members within the groups
- group meetings with attendance (including guests)
- upload associated audio of meetings
- upload transcriptions from meetings *or* transcribe them from the uploaded audio using diarisation tools

The aim is that the generation of transcription files will improve as the AI learns the voices of the group members. Data storage is kept local so that the data remains private.

The next stage of the application development will be to add interaction with an LLM to:
- query the generated transcripts
- summarise the meetings for a supervisor

Additionally, the application aims to allow a group to reference a repository which will gather development statistics to complement the meeting transcription data.

---

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy, Alembic
- **Database:** PostgreSQL + pgAdmin
- **Frontend:** Next.js (React + TypeScript)
- **Containerisation:** Docker + Docker Compose
- **Environment Management:** `python-dotenv`

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/group-meeting-transcripts.git
cd group-meeting-transcripts
```

### 2. Create a .env file in ./
```
# .env
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POSTGRES_DB=diarisation_db
POSTGRES_PORT=5432
POSTGRES_HOST=db

PGADMIN_DEFAULT_EMAIL=admin@example.com
PGADMIN_DEFAULT_PASSWORD=admin
```

### 3. Generate your HuggingFace token
Accept the terms and conditions on these models
https://huggingface.co/pyannote/segmentation
https://huggingface.co/pyannote/speaker-diarization


### 4. Start the project with Docker Compose
```bash
docker-compose up --build
```

This will:

✔️ Build the FastAPI backend (api)

✔️ Run PostgreSQL (db)

✔️ Run pgAdmin (pgadmin)

✔️ Run frontend (frontend) if enabled

✔️ Automatically apply Alembic migrations on startup

## API Usage
Once the server is running, access:

**FastAPI root:** http://localhost:8000

**Docs:** http://localhost:8000/docs

**pgAdmin:** http://localhost:5050

**Next.js frontend:** http://localhost:3000

---
## Folder Structure


```bash
Copy
Edit
.
├── backend/                # FastAPI backend
│   ├── db.py
│   ├── models.py
│   ├── main.py
│   ├── routes/
├── alembic/            # Alembic migrations
├── frontend/           # Next.js app
├── docker-compose.yml
├── Dockerfile
└── .env                #<- the .env file you need to create
```
---
## Troubleshooting

If database connection fails, confirm .env is loaded and Docker volumes are clean.

- Use docker-compose down -v to reset volume data.

- Use print(os.getenv(...)) to debug env variables in db.py.

## License
MIT License — feel free to use, modify and distribute.

## Contributors
Alun King -
[ResearchGate Profile](https://www.researchgate.net/profile/Alun-King?ev=hdr_xprf)