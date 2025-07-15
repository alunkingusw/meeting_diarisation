# 🧠 Transcription Flow Overview

This diagram illustrates the backend process for handling meeting audio file uploads and triggering transcription.

```mermaid
flowchart TD
    subgraph User Interaction
        A[1. User uploads file] --> B[/POST /groups/{group_id}/meetings/{meeting_id}/upload/]
        E[6. User calls transcribe endpoint] --> F[/POST /groups/{group_id}/meetings/{meeting_id}/transcribe/]
    end

    subgraph Backend Upload Handler
        B --> C{Is file type valid?}
        C -->|Yes| D[Save file to disk]
        D --> DB1[Create RawFile entry in DB]
        C -->|No| ERR1[400: Invalid file type]
    end

    subgraph Transcription Trigger
        F --> G{Is audio file uploaded?}
        G -->|No| ERR2[400: No audio file found]
        G -->|Yes| H{Already processed?}
        H -->|Yes + no reprocess| ERR3[409: Already processed]
        H -->|No or reprocess=true| I[Queue transcription job]
        I --> WORKER[Background job handler]
    end

    subgraph Background Processing
        WORKER --> J[Load audio file]
        J --> K[Run transcription engine]
        K --> L[Save transcript to disk or DB]
        L --> DB2[Update RawFile.processed_date]
    end

    subgraph Status Checking
        M[7. User polls status] --> N[/GET /groups/{group_id}/meetings/{meeting_id}/transcription/status]
        N --> DB3[Query RawFile.processed_date]
        DB3 --> O{Processed?}
        O -->|Yes| P[Return transcript or download URL]
        O -->|No| Q[Return "processing" status]
    end
