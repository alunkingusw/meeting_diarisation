# Transcription Flow Overview

This diagram illustrates audio transcription and transcript ingestion. A provided VTT and a
server-generated VTT both reach the same chunking and persistent Chroma indexing path.

```mermaid
flowchart TD
    subgraph User Interaction
        A[User uploads file] --> B[POST /upload]
        E[User calls transcribe endpoint] --> F[POST /transcribe]
    end

    subgraph Backend Upload Handler
        B --> C{Is file type valid?}
        C -->|Yes| D[Save file to disk]
        D --> DB1[Create RawFile entry in DB]
        DB1 -->|Provided VTT| IQ[Queue transcript_processing job]
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
        L --> IDX[index_transcript]
        IQ --> IDX
        IDX --> VTT[Verify, parse, and chunk VTT]
        VTT --> EMB[Embed chunks with local model]
        EMB --> CH[(Persistent ChromaDB)]
        IDX --> DB2[Update transcript/job metadata]
    end

    subgraph Status Checking
        M[User polls status] --> N[GET transcriptions/status]
        N --> DB3[Query RawFile.processed_date]
        DB3 --> O{Processed?}
        O -->|Yes| P[Return transcript or download URL]
        O -->|No| Q[Return 'processing' status]
    end
