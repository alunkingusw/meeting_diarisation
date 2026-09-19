# Roadmap

Planned work beyond the current MVP. Nothing here is scheduled or committed to a version — it's
a backlog of known next steps, ordered roughly by dependency.

## 1. ~~Real source clients for `assess_query`~~ — done

`assess_query` now queries all three sources for real (see README "Design decisions"):
meeting_diarisation's transcript search (chunked/indexed by a vendored copy of VTT-RAGinator,
synthesised into a cited answer via Ollama) and GitHub-RAGinator's `/query` for GitHub/Trello
(GitHub-RAGinator's own repo registration is kept in sync with meeting_diarisation's
`Group.github_repo_url`/`trello_board_id` via `GitHub-RAGinator/scripts/sync_repos_from_diarisation.py`).
Per-group repo/board configuration lives on meeting_diarisation's `Group` row, not in this
project's `config.yaml`.

## 2. ~~Scheduled weekly per-group update~~ — first vertical slice done

A proactive report, generated automatically overnight once a week per group, rather than
triggered by an inbound email. Requires:

- **A third background thread/loop** (alongside the existing mail-poll and job-worker loops in
  `app/main.py`) on a weekly schedule, or an external cron invoking a one-shot command — either
  fits the existing SQLite-backed, thread-per-concern architecture.
- **Iterating known groups** — `authorisation.group_owners` (or a dedicated groups config) as the
  list to run the update for.
- **Reusing the source clients from item 1** to compile each group's update (recent transcripts,
  GitHub activity, Trello board state) rather than routing a single ad-hoc question.
- **Delivery**: who receives it (group owner(s) only, or a wider list?) and what happens on a
  partial failure (e.g. GitHub reachable but Trello down for one group) — should the update still
  send with a "couldn't reach X" note, matching the "be conservative, never guess" pattern used
  elsewhere, rather than silently omitting a section.
- **Idempotency/retry**: what happens if the process restarts mid-run — needs the same
  crash-safe, resumable design as the existing job store/outbox, not a fire-and-forget loop.

Implemented in `app/reports/` and exposed as `weekly-project-update`. The workflow uses LangGraph,
SQLite report/evidence snapshots, the existing outbox/message-link model, and deterministic
source adapters. Remaining work is to replace the current bounded GitHub-RAGinator queries with
structured date-bounded GitHub and Trello activity endpoints when those APIs are available.
