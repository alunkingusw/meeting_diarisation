# Manager Graph Design

This document summarises the tool set and graph composition pattern that has already been validated for the email-agent project.

## Principle

The graph is not a replacement for the deterministic validation boundary. The application continues to validate email commands and ownership before any graph-backed execution is invoked. The graph is an execution layer for the trusted manager client.

The graph is intentionally narrow and compositional:

- each tool wraps one explicit manager operation
- graph nodes call those tools in a predictable sequence
- the existing pipeline remains the fallback until parity is proven
- audit events are recorded around every tool call

## Tool inventory

### Manager client tools

These currently exist as LangChain tools in `app/llm/manager_tools.py`:

1. `list_groups(token: str)`
   - Lists the groups available to the authenticated caller.

2. `get_group(token: str, group_id: int)`
   - Returns one group's detail and member list.

3. `list_meetings(token: str, group_id: int, from_date: str | None = None, to_date: str | None = None)`
   - Lists meetings in a group, optionally filtered by date range.

4. `get_meeting(token: str, group_id: int, meeting_id: int)`
   - Fetches one meeting's details.

5. `add_comment(token: str, group_id: int, meeting_id: int, comment: str)`
   - Adds a textual comment to an existing meeting.

6. `resolve_aliases(token: str, group_id: int, names: list[str], source: str | None = "transcript_name")`
   - Resolves transcript speaker names to group member IDs.

7. `search_transcripts(token: str, group_id: int, query: str, meeting_id: int | None = None)`
   - Retrieves semantically relevant transcript chunks.

8. `login_for_email(email: str)`
   - Exchanges a verified sender email for a JWT via the service-authenticated backend route.

## Proven command graphs

### 1. `add_comment` graph

Implemented in `app/llm/comment_graph.py`.

Flow:

- `login_for_email`
  - uses sender email to acquire a JWT
- `add_comment`
  - calls the manager API to create the meeting comment

This path is the first graph-backed production execution route and is already used by the add-comment handler.

### 2. `status` and `results` dispatcher paths

Implemented in `app/llm/command_dispatcher.py`.

These do not use the manager tools directly; instead they mirror the same deterministic output contract as the existing handler logic:

- `execute_status`: fetches the job, renders the status email, enqueues it
- `execute_results`: fetches the job, renders the results email, enqueues it

This keeps the graph path safe and comparable while preserving the trusted job-store semantics.

## Recommended composition pattern

Use this pattern when moving a new command to the graph-backed path:

1. Start from the trusted deterministic handler contract.
   - job creation
   - ownership validation
   - outbox enqueueing
   - reply rendering
2. Identify which manager tools are required.
   - usually a small, explicit set
3. Build a minimal graph node for each required tool call.
   - keep each node single-purpose
4. Maintain the output contract exactly.
   - same result shape or same side-effect contract as the handler
5. Record audit events on every node transition.
   - `tool_start`
   - `tool_result`
   - command-level step markers
6. Keep the old path as fallback until parity is proven on the relevant fixture set.

## Recommended next graph expansions

These are the next best candidates, in rough order:

1. `help`
   - no backend call; pure template response
   - very low risk

2. `cancel`
   - job-store only; deterministic and read/write but still local
   - safe next step after help

3. `submit_transcript`
   - more complex; involves upload + job creation + transcript processing
   - should be done only after lower-risk command graphs are stable

4. `assess_query`
   - most complex; requires transcript/GitHub/Trello tooling and LLM orchestration
   - should be last

5. `submit_transcript`
   - see `documentation/submit_transcript_graph_design.md`
   - requires explicit handling for partial backend side effects and retry/idempotency

## Current status

The following are already proven working:

- manager tool layer for the backend operations
- graph-backed `add_comment` path
- graph-backed `status` execution
- graph-backed `results` execution
- audit events recorded during graph execution

## Design caution

Do not convert the whole system to a generic tool-call graph too early. The current architecture intentionally avoids a fully dynamic operation lookup. The graph should remain narrow and explicit, matching the same finite command set already enforced by `Operation` in `app/commands/schema.py`.

That keeps the security model and deterministic validation path intact while letting the execution layer become more structured and inspectable.
