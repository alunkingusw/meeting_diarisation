"""
Smoke tests for the root/status/gpu-status endpoints. The real model-loading
checks inside `check_model_status()` (whisper/pyannote actually loading) are
covered separately under `backend/tests/integration/`, since they need the
full ML stack and a working Hugging Face token.
"""


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Diarisation API is running."}


def test_status_reports_database_connected(client):
    response = client.get("/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert "models" in body


def test_gpu_status_reports_shape(client):
    response = client.get("/gpu-status")
    assert response.status_code == 200
    body = response.json()
    # Response shape differs depending on CUDA availability - see
    # backend/routes/status.py:get_gpu_status.
    if "torch_version" in body:
        assert "is_compatible" in body
    else:
        assert body.get("cuda_available") is False
        assert "message" in body
