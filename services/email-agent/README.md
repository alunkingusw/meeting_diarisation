# GroupAssessmentAgent — Email Interface

An email-based interface for the group meeting transcription platform. Registered users and
group-member email addresses can send requests; users retain the existing workflow, while
group-member senders can submit `.vtt` transcripts and add comments only in their associated
groups. A local worker uses a locally-hosted LLM (via Ollama) to interpret requests into
strictly-validated commands, and deterministic application code performs the backend actions.

See [Specification.md](Specification.md) for the original design spec. This README documents
where the actual implementation adapted that spec to the real backend (see "Design decisions"
below) and how to configure and run it.

## Design decisions (vs. the original spec)

The backend has no generic "diarise this audio" endpoint, no job/status/cancel model, and no
per-user email field — it's a group/meeting/attendee system. After inspecting it, the scope was
adjusted as follows:

- **Audio is out of scope for email.** It's rejected outright with a message pointing the sender
  at the admin. Only `.vtt` transcripts are accepted.
- **`diarise` is replaced with `submit_transcript`.** No pyannote/transcription endpoint is ever
  called from this project — the email flow ingests an already-produced transcript, creates a
  `Meeting`, uploads the file, and resolves speaker labels to `GroupMember`s via the backend's
  existing alias-resolution endpoint (`POST /groups/{id}/aliases/resolve`).
- **Sender authorization is ordered by identity and permission.** After sender authentication,
  a registered `User` is checked first and receives the existing user workflow. If there is no
  matching user, associated `GroupMember` records are checked; these senders can submit
  transcripts and add comments only in their groups. A sender matching both is treated as the
  `User`. Backend-issued GroupMember tokens are group-scoped and cannot be used on user-only
  routes; member comments are attributed to the GroupMember record.
- **Unknown sender handling:** sender identity comes only from the backend database; there is no
  domain allow-list. An authenticated sender who matches neither a `User` nor a `GroupMember` is
  silently dropped, since replying to arbitrary internet senders would confirm a monitored
  mailbox exists. Failed SPF/DKIM/DMARC checks are dropped the same way and are never trusted,
  even for a registered address.
- **The admin is alerted** (rate-limited, `ADMIN_EMAIL`) on rejected senders, LLM parse failures,
  backend submission failures, and infrastructure outages (Ollama or the backend unreachable).
- **Mail access is provider-agnostic** via a `MailClient` interface (`app/mail/base.py`). The app
  supports Microsoft Graph and a generic IMAP/SMTP provider implementation (`app/mail/imap_client.py`)
  for dedicated project mailboxes such as `mailbox.org`.
- **`assess_query` answers real questions from three sources**: past meeting transcripts
  (meeting_diarisation's `/groups/{id}/transcripts/search`, synthesised into a cited prose answer
  via a second, narrowly-scoped Ollama call — see `app/llm/transcript_synthesis.py`), and the
  group's GitHub repo/Trello board (GitHub-RAGinator's `/query`, which returns its own
  LLM-synthesised answer). The LLM only ever decides *which* sources are relevant
  (`transcript_focus`/`github_focus`/`trello_focus`) — the queries themselves are deterministic
  API calls, same trust-boundary pattern as everything else in this codebase. Like
  `submit_transcript`, it's split into `accept()`/`execute()` so a slow or unreachable source
  never blocks mail polling; a source being unreachable degrades the reply with a note rather
  than failing the whole request, as long as at least one requested source answered. See the
  `RUN_OLLAMA_TESTS=1` corpus in `tests/test_command_parser_llm.py` for source-routing checks.

The full reasoning is in the approved implementation plan; the security boundary is unchanged
from the spec: the LLM only ever produces a `ParsedCommand` (`app/commands/schema.py`), which is
re-validated deterministically (`app/commands/validator.py`) before anything executes.

## Project layout

```
app/
  mail/          MailClient interface, Graph implementation, fake client for tests, thread matching
  auth/          Deterministic sender authorisation and permission precedence
  llm/           Ollama client, system prompt, retry-then-fail command parser
  commands/      The structured command schema and its validator (the trust boundary)
  vtt/           WEBVTT parser (Teams voice tags, speaker labels + NOTE meeting-date convention)
  diarisation/   HTTP client for the real backend (one method per endpoint used)
  jobs/          SQLite job store, inbound-message dedup, outbound mail queue, background worker
  reports/       LangGraph weekly reports, persisted source evidence, and report replies
  handlers/      One handler per operation (submit_transcript, status, results, cancel, help)
  email_templates/  Jinja2 templates for every outbound email
  admin/         Rate-limited admin alerting
  storage/       SQLite schema, attachment persistence
  pipeline.py    Orchestrates one poll cycle; the explicit command dispatch (spec S17)
  main.py        Wires everything together and runs the two background threads
config/          config.example.yaml - copy to config.yaml
tests/           pytest suite (see "Testing" below)
```

## Setup

### 1. Python environment

```bash
python -m venv .venv
.venv/Scripts/activate        # or source .venv/bin/activate on Linux/macOS
pip install -e ".[test]"
```

### 2. Ollama

```bash
ollama pull qwen2.5:14b
```

Confirm it's reachable: `curl http://localhost:11434/api/tags`.

### 3. Backend

Start the `group_meeting_transcripts` backend (see its own README — typically
`docker-compose up`). Create at least one `User` and `Group` via its API, and note the
`user_id` — this is what `authorisation.group_owners` maps each sender's email to.

### 4. Configuration

```bash
cp config/config.example.yaml config/config.yaml
cp .env.example .env
```

Edit `config/config.yaml`:
- `authorisation.group_owners`: map each authorised sender's email to their backend `user_id`.
- `backend.base_url`: where the backend is running (e.g. `http://localhost:8000`).
- `llm.model`: defaults to `qwen2.5:14b`.

Edit `.env`:
- `ADMIN_EMAIL`: who gets alerted on rejected senders, parse failures, backend failures,
  and infrastructure outages.
- `GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET`: see "Mailbox setup" below.

### 5. Mailbox setup

Choose one of the supported providers:

#### Option A: mailbox.org / other IMAP+SMTP provider

1. Create a dedicated project mailbox.
2. Enable IMAP and SMTP access in the provider dashboard.
3. Create an app password or use the provider's supported automation credentials.
4. Put the mailbox username and password into `.env` as `MAIL_USERNAME` and `MAIL_PASSWORD`.
5. Set `mail.provider: mail` and `mail.mailbox_upn` in `config/config.yaml` to the mailbox address.
6. Use TLS/STARTTLS-only outbound and inbound access, and keep the mailbox separate from personal or university accounts.

#### Option B: Microsoft Graph

1. In Azure AD / Entra ID, register a new application.
2. Under **API permissions**, add **Application** permissions (not delegated)
   `Mail.ReadWrite` and `Mail.Send` for Microsoft Graph, then **grant admin consent**.
3. Under **Certificates & secrets**, create a new client secret.
4. Put the tenant id, application (client) id, and client secret into `.env`.
5. Set `mail.mailbox_upn` in `config.yaml` to the mailbox's address (e.g.
   `diarisation@yourtenant.onmicrosoft.com`).
6. **Recommended**: scope the app's mail access to only this mailbox, rather than leaving it
   with tenant-wide access, using Exchange Online PowerShell:
   ```powershell
   New-ApplicationAccessPolicy -AppId <client-id> -PolicyScopeGroupId diarisation@yourtenant.onmicrosoft.com -AccessRight RestrictAccess -Description "GroupAssessmentAgent - restrict to one mailbox"
   ```

### 6. Run

#### Option A: directly with Python

```bash
python -m app.main
```

This starts two background threads: one polling the mailbox and parsing/validating requests,
and one draining the job queue (submitting accepted transcripts to the backend).

#### Option B: Docker

For a portable server deployment (`git clone` + `docker-compose up`, no Python environment to set
up on the host). Ollama and the backend are **not** included in the compose stack — they're
expected to already be reachable (e.g. running on the same host, or elsewhere on the network).

1. Complete steps 4 and 5 above (`config/config.yaml` and `.env`) as normal.
2. Since `localhost` inside a container refers to the container itself, not the host, point
   `llm.host` and `backend.base_url` in `config/config.yaml` at wherever Ollama/the backend
   actually are reachable from — if they're running directly on the same server, use
   `http://host.docker.internal:11434` and `http://host.docker.internal:8000` (the compose file
   maps this hostname to the host on Linux too, not just Docker Desktop).
3. `mkdir -p data` (so the bind-mounted volume exists before the container's non-root user needs
   to write to it).
4. `docker-compose up -d --build`
5. `docker-compose logs -f` to watch it start; `docker-compose down` to stop it.

`./data` is bind-mounted, so the SQLite job store, queued attachments, and logs persist across
restarts and rebuilds. The image intentionally excludes test dependencies and `tests/` — run the
test suite from the host venv (see "Testing" below), not inside the container.

### Internal email API

The container can optionally accept outbound email requests from another container. This is
disabled by default. Enable it in `config/config.yaml` and set a long random `EMAIL_API_TOKEN` in
`.env`:

```yaml
internal_api:
  enabled: true
  host: 0.0.0.0
  port: 8080
```

The API is available to containers on the shared Docker network at
`http://agent:8080/internal/email`. It only accepts one request shape and queues the message for
the normal provider/outbox retry loop:

```bash
curl -X POST http://agent:8080/internal/email \
  -H "Authorization: Bearer $EMAIL_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to":"person@example.com","subject":"Hello","body":"Message body"}'
```

Successful requests return `202` with an outbox ID; this means the message was queued, not that
the provider has already accepted it. The API deliberately does not accept attachments, provider
commands, or arbitrary extra fields. `GET /healthz` is available for a basic container health
check and does not require authentication.

To add a comment to an existing meeting, reply to its summary email and keep both identifiers in
the subject using the exact forms `group_id=7` and `meeting_id=42`. Put the comment in the reply
body. The request is queued as a background job, posted to the meeting manager, and followed by a
confirmation email containing the returned comment details.

To record an unrecorded meeting, email the meeting date and notes. The agent creates a meeting
without a transcript and saves the notes as a comment. Include the group name if your email is
associated with more than one group. If no usable meeting date is included, the agent asks you
for one before creating anything.

## Testing

```bash
pip install -e ".[test]"
pytest                          # full suite, no live Ollama or mailbox required
RUN_OLLAMA_TESTS=1 pytest -m integration   # also exercises a live local Ollama
```

Everything except the opt-in `RUN_OLLAMA_TESTS=1` integration tests runs against fakes/mocks —
`FakeMailClient` (`app/mail/fake_client.py`) for full pipeline tests with no live mailbox, and
`respx`-mocked HTTP for both the Graph client and the backend API client. The security-critical
property from spec S18/S22 — that an injected email can never cause the application to act
outside the finite command schema, even if the LLM is fully compromised by the injection — is
covered directly in `tests/test_prompt_injection.py` using a stubbed adversarial LLM, so it
doesn't depend on how a real model happens to behave on a given day.

## Known limitations (MVP scope, matching spec S23)

- No `status`/cancel endpoint exists on the backend, so `status`/`results` are answered entirely
  from this project's own job store, and `cancel` only works while a job is still queued locally
  (not yet dispatched to the backend) — there's nothing to safely roll back once a Meeting has
  been created.
- The app supports Microsoft Graph and a generic IMAP/SMTP provider implementation for dedicated
  project mailboxes such as `mailbox.org`; the provider is chosen via `mail.provider`.
- A speaker label in a transcript that can't be matched to a known `GroupMember` is reported to
  the sender, not auto-created as a new member (avoids roster pollution from typos).
- `assess_query`'s `results`/`status` commands don't show anything assess_query-specific if
  looked up afterward by job ID — those templates are still submit_transcript-shaped (group/
  meeting/attendees). Not a real gap in practice: the actual answer is always emailed
  automatically once the job completes, same as submit_transcript's completion email.

See [ROADMAP.md](ROADMAP.md) for planned follow-on work, including wiring up real source clients
and a scheduled weekly per-group update.

## Weekly project updates

The weekly update is a one-shot command intended to be invoked by cron or a system scheduler:

```bash
weekly-project-update --config config/config.yaml
```

For example, a Monday 08:00 cron entry is:

```cron
0 8 * * 1 /path/to/.venv/bin/weekly-project-update --config /path/to/config/config.yaml
```

Enable it with `weekly_update.enabled: true`. The command discovers each active group for every
authorised owner, creates one idempotent `WEEKLY-YYYY-MM-DD-GROUP` report per period, and runs a
LangGraph workflow that collects meeting, GitHub, and Trello evidence, persists that evidence in
SQLite, synthesises a cited plain-text report, and sends it through the existing outbox.

The current backend exposes transcript search and GitHub-RAGinator query endpoints rather than
raw activity feeds. The source adapter therefore records the bounded query and its answer as
evidence, while filtering transcript chunks by meeting date. When structured GitHub/Trello
activity endpoints become available, they can replace `app/reports/sources.py` without changing
the scheduler, report store, graph, or email workflow.

Replies to a weekly report are matched by `In-Reply-To`/`References` or the report ID in the
subject. They are answered from the persisted evidence snapshot and remain in the same outbound
message-link history; the normal command parser is not used for report questions.
