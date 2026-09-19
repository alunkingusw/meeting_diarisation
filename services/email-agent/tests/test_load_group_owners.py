import httpx
import respx

from app.main import load_group_owners
from app.settings import AuthorisationSettings, BackendSettings, Settings

BASE_URL = "http://backend.test"


def _settings(*, group_owners=None, service_api_key=None) -> Settings:
    settings = Settings(
        authorisation=AuthorisationSettings(group_owners=group_owners or {}),
        backend=BackendSettings(base_url=BASE_URL, request_timeout_seconds=1.0),
    )
    settings.diarisation_service_api_key = service_api_key
    return settings


def test_static_override_wins_without_calling_backend():
    settings = _settings(group_owners={"alice@example.com": 12}, service_api_key="key")
    # No respx mock registered at all - a call to the backend would raise, proving the
    # static override short-circuits before any HTTP request is made.
    assert load_group_owners(settings) == {"alice@example.com": 12}


def test_no_service_key_and_no_override_returns_empty():
    settings = _settings(service_api_key=None)
    assert load_group_owners(settings) == {}


@respx.mock
def test_live_fetch_success():
    respx.get(f"{BASE_URL}/admin/group-owners").mock(
        return_value=httpx.Response(200, json={"alice@example.com": 12})
    )
    settings = _settings(service_api_key="key")
    assert load_group_owners(settings) == {"alice@example.com": 12}


@respx.mock
def test_live_fetch_failure_fails_closed_to_empty():
    respx.get(f"{BASE_URL}/admin/group-owners").mock(return_value=httpx.Response(500))
    settings = _settings(service_api_key="key")
    assert load_group_owners(settings) == {}
