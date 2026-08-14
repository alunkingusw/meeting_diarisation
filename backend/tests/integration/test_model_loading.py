"""
Integration tier: actually loads whisper and pyannote models, rather than the
fast tier's import/version-only checks. Requires:

- The full ML stack installed (whisper, torch, torchaudio, pyannote.audio) -
  not just torch, which is all this host normally carries.
- A real `HUGGING_FACE_TOKEN` exported in the environment before running
  pytest, with the gated model terms accepted (see README.md's "Generate
  your HuggingFace token" step) for pyannote/speaker-diarization and
  pyannote/embedding.
- Network access to Hugging Face Hub.

Run explicitly with: pytest -m integration
Not run by default (see pytest.ini's addopts).
"""

import pytest

pytestmark = pytest.mark.integration


def test_status_endpoint_reports_real_models_available(client):
    response = client.get("/status")
    assert response.status_code == 200
    models = response.json()["models"]

    assert models["whisper_model"]["status"] == "available"
    assert models["pyannote_diarization"]["status"] == "available"
    assert models["pyannote_embedding"]["status"] == "available"
