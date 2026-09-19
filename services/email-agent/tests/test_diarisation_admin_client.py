import httpx
import pytest
import respx

from app.diarisation.admin_client import AdminDiarisationApiError, AdminDiarisationClient

BASE_URL = "http://backend.test"
SERVICE_KEY = "test-service-key"


@pytest.fixture
def client():
    c = AdminDiarisationClient(BASE_URL, SERVICE_KEY, timeout=1.0)
    yield c
    c.close()


@respx.mock
def test_get_group_owners_returns_mapping(client):
    route = respx.get(f"{BASE_URL}/admin/group-owners").mock(
        return_value=httpx.Response(200, json={"alice@example.com": 12, "bob@example.com": 7})
    )
    owners = client.get_group_owners()
    assert owners == {"alice@example.com": 12, "bob@example.com": 7}
    assert route.calls.last.request.headers["X-Service-Key"] == SERVICE_KEY


@respx.mock
def test_get_group_owners_wrong_key_raises(client):
    respx.get(f"{BASE_URL}/admin/group-owners").mock(
        return_value=httpx.Response(401, json={"detail": "Missing or invalid service key"})
    )
    with pytest.raises(AdminDiarisationApiError):
        client.get_group_owners()


@respx.mock
def test_get_group_owners_network_error_raises(client):
    respx.get(f"{BASE_URL}/admin/group-owners").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(AdminDiarisationApiError):
        client.get_group_owners()
