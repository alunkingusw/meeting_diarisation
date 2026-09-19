from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.diarisation.client import DiarisationApiError, DiarisationClient, GroupSummary
from app.github_raginator.client import GithubRaginatorApiError, GithubRaginatorClient
from app.reports.models import ReportEvidence


@dataclass
class SourceCollection:
    evidence: list[ReportEvidence] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)


class ReportTextGenerator(Protocol):
    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.0,
                 json_mode: bool = True) -> str: ...


class WeeklySourceCollector:
    """Collects bounded, citeable evidence through the existing finite API clients.

    The current backend exposes transcript search and a GitHub-RAGinator query endpoint,
    rather than raw activity feeds. The report records that limitation in the citation and
    keeps the adapter replaceable when structured activity endpoints become available.
    """

    def __init__(self, diarisation: DiarisationClient, github: GithubRaginatorClient):
        self._diarisation = diarisation
        self._github = github

    def collect(
        self, token: str, group: GroupSummary, period_start: date, period_end: date
    ) -> SourceCollection:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="weekly-source") as executor:
            meetings = executor.submit(
                self._collect_meetings, token, group, period_start, period_end
            )
            project_tools = executor.submit(
                self._collect_github_and_trello, group, period_start, period_end
            )
            result = meetings.result()
            other = project_tools.result()
        result.evidence.extend(other.evidence)
        result.unavailable.extend(other.unavailable)
        return result

    def _collect_meetings(
        self, token: str, group: GroupSummary,
        period_start: date, period_end: date,
    ) -> SourceCollection:
        result = SourceCollection()
        query = f"meetings and decisions between {period_start.isoformat()} and {period_end.isoformat()}"
        try:
            chunks = self._diarisation.search_transcripts(token, group.id, query)
        except DiarisationApiError as exc:
            result.unavailable.append(f"meetings ({exc})")
            return result

        for chunk in chunks:
            try:
                chunk_date = date.fromisoformat(chunk.meeting_date[:10])
            except ValueError:
                continue
            if not (period_start <= chunk_date < period_end):
                continue
            result.evidence.append(
                ReportEvidence(
                    source="meetings",
                    evidence_id=chunk.chunk_id,
                    title=chunk.meeting_title,
                    event_date=chunk.meeting_date,
                    content=chunk.text,
                    citation=chunk.citation(),
                    raw_json=json.dumps(chunk.__dict__, sort_keys=True),
                )
            )
        return result

    def _collect_github_and_trello(
        self, group: GroupSummary,
        period_start: date, period_end: date,
    ) -> SourceCollection:
        result = SourceCollection()
        try:
            repo = self._github.find_repo_by_group_name(group.name)
        except GithubRaginatorApiError as exc:
            result.unavailable.append(f"GitHub/Trello ({exc})")
            return result
        if repo is None:
            result.unavailable.append("GitHub/Trello (no linked repository)")
            return result

        window = f"between {period_start.isoformat()} and {period_end.isoformat()}"
        self._collect_query(
            result, "github", repo.id,
            f"Summarise GitHub commits, pull requests, issues, and releases {window}. "
            "Return only activity in that period with identifiers and dates.",
            repo.github_url,
        )
        self._collect_query(
            result, "trello", repo.id,
            f"Summarise Trello card movement, completed work, blockers, and due dates {window}. "
            "Return only activity in that period with card names and dates.",
            repo.github_url,
        )
        return result

    def _collect_query(
        self, result: SourceCollection, source: str, repo_id: int,
        question: str, citation: str,
    ) -> None:
        try:
            answer = self._github.query(repo_id, question).answer.strip()
        except GithubRaginatorApiError as exc:
            result.unavailable.append(f"{source} ({exc})")
            return
        if not answer:
            return
        result.evidence.append(
            ReportEvidence(
                source=source,
                evidence_id=f"repo-{repo_id}-{source}",
                title=f"{source.title()} activity query",
                event_date=None,
                content=answer,
                citation=f"{citation} ({source} activity query)",
                raw_json=json.dumps({"repo_id": repo_id, "question": question, "answer": answer}, sort_keys=True),
            )
        )
