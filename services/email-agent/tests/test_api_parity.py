"""Every email command must map onto routes in the backend's published API contract.

If you add an Operation, add it here: either list the routes it uses or mark it local-only.
"""
import json
from pathlib import Path

import pytest

from app.commands.schema import Operation

OPENAPI = Path(__file__).resolve().parents[3] / "docs" / "openapi.json"

# Routes each command uses, so a Postman user can do exactly what the email does.
OPERATION_ROUTES = {
    Operation.SUBMIT_TRANSCRIPT: [
        ("POST", "/admin/user-token"),
        ("GET", "/groups/"),
        ("POST", "/groups/{group_id}/meetings/"),
        ("POST", "/groups/{group_id}/meetings/{meeting_id}/upload/"),
        ("POST", "/groups/{group_id}/aliases/resolve"),
        ("POST", "/groups/{group_id}/meetings/{meeting_id}/attendees"),
    ],
    Operation.ASSESS_QUERY: [
        ("POST", "/groups/{group_id}/conversation/query"),
        ("POST", "/groups/{group_id}/github/query"),
        ("POST", "/groups/{group_id}/trello/query"),
        ("POST", "/groups/{group_id}/query"),
    ],
    Operation.ADD_COMMENT: [("POST", "/groups/{group_id}/meetings/{meeting_id}/comments")],
    # Job state for a request comes from the backend's jobs API.
    Operation.STATUS: [("GET", "/jobs/{job_id}"), ("GET", "/jobs/")],
    Operation.RESULTS: [("GET", "/jobs/{job_id}"), ("GET", "/jobs/")],
    Operation.CANCEL: [("POST", "/jobs/{job_id}/cancel")],
    Operation.LOG_MEETING: [
        ("POST", "/groups/{group_id}/meetings/"),
        ("POST", "/groups/{group_id}/meetings/{meeting_id}/comments"),
    ],
}

# Weekly update (scheduled, not a command) and its follow-up replies.
REPORT_ROUTES = [
    ("POST", "/groups/{group_id}/reports/weekly"),
    ("POST", "/groups/{group_id}/reports/answer"),
]

LOCAL_ONLY = {Operation.HELP}


def _contract() -> set[tuple[str, str]]:
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    return {(method.upper(), path) for path, ops in spec["paths"].items() for method in ops}


def test_every_operation_is_mapped_or_explicitly_local():
    assert set(Operation) == set(OPERATION_ROUTES) | LOCAL_ONLY


@pytest.mark.skipif(not OPENAPI.exists(), reason="docs/openapi.json not available")
def test_every_mapped_route_exists_in_the_api_contract():
    contract = _contract()
    mapped = {route for routes in OPERATION_ROUTES.values() for route in routes} | set(REPORT_ROUTES)
    assert mapped - contract == set()
