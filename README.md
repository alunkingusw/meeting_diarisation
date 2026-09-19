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

### 2. Create a .env.docker file in ./
```
# .env
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POSTGRES_DB=diarisation_db
POSTGRES_PORT=5432
POSTGRES_HOST=db

PGADMIN_DEFAULT_EMAIL=admin@example.com
PGADMIN_DEFAULT_PASSWORD=admin

HUGGING_FACE_TOKEN = see step 3
```

### 3. Generate your HuggingFace token
Accept the terms and conditions on these models
https://huggingface.co/pyannote/segmentation
https://huggingface.co/pyannote/speaker-diarization
https://huggingface.co/pyannote/embedding


### 4. Start the project with Docker Compose
```bash
docker compose -f deploy/docker-compose.yml up --build
```

This will:

✔️ Build the FastAPI backend (api)

✔️ Run PostgreSQL (db)

✔️ Run pgAdmin (pgadmin)

✔️ Run frontend (frontend) if enabled

✔️ Automatically apply Alembic migrations on startup

The repository also includes the email agent under `services/email-agent`. To enable the
integrated deployment, copy its example files and configure the mailbox, backend, and internal
API token:

```bash
cp services/email-agent/config/config.example.yaml services/email-agent/config/config.yaml
cp services/email-agent/.env.example services/email-agent/.env
mkdir -p services/email-agent/data
```

Set `internal_api.enabled: true` in the agent configuration and use the same token as
`EMAIL_API_TOKEN` in the meeting manager `.env`. The agent is reachable from the API container at
`http://agent:8080/internal/email`; it is not published to the host by default.

## API Usage
Once the server is running, access:

**FastAPI root:** http://localhost:8000

**Docs:** http://localhost:8000/docs

**pgAdmin:** http://localhost:5050

**Next.js frontend:** http://localhost:3000

## API contract

The FastAPI application is the source of truth for the service contract. With the backend
dependencies and environment configured, export the OpenAPI document with:

```bash
python scripts/export_openapi.py --output docs/openapi.json
```

The contract tests verify the paths and schemas consumed by the email agent. Generated client
code is checked into `services/email-agent/app/diarisation/generated_client` and can be
regenerated with:

```bash
openapi-python-client generate \
   --path docs/openapi.json \
   --output-path services/email-agent/app/diarisation/generated_client \
   --overwrite
```

The manual client remains the runtime compatibility layer until the generated operations have
been compared and adopted incrementally.

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

## Building Custom PyTorch/TorchAudio Wheels for GPU

If you need to build PyTorch or TorchAudio with support for your specific GPU, you can create a custom wheel (`.whl`) file. This allows you to install PyTorch locally or in Docker without downloading prebuilt binaries.

### Overview

1. **Determine your GPU architecture (compute capability)**
   - Each NVIDIA GPU has a compute capability (e.g., `sm_61` for GTX 1070). The newer GPUs will have support included with the latest Torch release, but you may need to build a custom wheel if you have an older card (like me!)
   - You can find the list of compute capabilities on NVIDIA's official documentation: [CUDA GPUs](https://developer.nvidia.com/cuda-gpus).

2. **Install prerequisites**
   - You will need a working Python environment, compiler toolchain, and CUDA toolkit compatible with your GPU.
   - For Linux, this usually means installing `cmake`, `ninja-build`, `gcc`, and Python development headers.
   - For Windows, Visual Studio Build Tools are required along with the CUDA toolkit.
   - See PyTorch’s official build guide: [https://github.com/pytorch/pytorch#from-source](https://github.com/pytorch/pytorch#from-source)

3. **Clone the repositories**
   - Clone PyTorch and TorchAudio (or any other libraries you need) from their official GitHub repositories with `--recursive` to include submodules.

4. **Set GPU architecture flags**
   - PyTorch allows you to specify which GPU architectures to build for. Setting the appropriate architecture ensures optimized performance on your hardware.
   - For guidance, refer to the official PyTorch documentation on building for CUDA: [https://pytorch.org/docs/stable/notes/windows.html#build-from-source](https://pytorch.org/docs/stable/notes/windows.html#build-from-source)

5. **Build the wheel**
   - Use Python’s standard build system to create a `.whl` file.  
   - Once built, you can install it locally or use it in Docker.

6. **Install locally or in Docker**
   - Install the wheel using `pip install <wheel-file>` on your local machine.  
   - In Docker, you can copy the wheel into your image and install it during the build process to avoid downloading from the internet.

### Additional Resources

- PyTorch From Source: [https://github.com/pytorch/pytorch#from-source](https://github.com/pytorch/pytorch#from-source)  
- TorchAudio From Source: [https://github.com/pytorch/audio#building-from-source](https://github.com/pytorch/audio#building-from-source)  
- NVIDIA CUDA Toolkit: [https://developer.nvidia.com/cuda-toolkit](https://developer.nvidia.com/cuda-toolkit)  

> Note: Building PyTorch from source can take a long time depending on your system. Make sure to include only the GPU architectures you need to reduce build time and wheel size.

## License
MIT License — feel free to use, modify and distribute.

## Contributors
Alun King -
[ResearchGate Profile](https://www.researchgate.net/profile/Alun-King?ev=hdr_xprf)