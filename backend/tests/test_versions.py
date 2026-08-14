"""
Fast, no-DB checks that the pinned dependency versions are actually what's
installed, and that torch's view of CUDA is internally consistent.

Packages that aren't installed at all in the current environment (e.g.
whisper/pyannote on a host that only has the lightweight dev stack) are
reported as *skipped*, not failed - the point is to catch drift when a
package IS installed, not to force every dev machine to carry the full
CUDA/ML stack. Run this inside the built Docker image (which does carry the
full stack) for the strict version of this check.
"""

import importlib.metadata
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_PIN_RE = re.compile(r"^([A-Za-z0-9_.\-\[\]]+)\s*==\s*([A-Za-z0-9_.\-+]+)")


def _parse_pins(requirements_file: Path) -> dict[str, str]:
    pins = {}
    for line in requirements_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-e") or line.startswith("git+"):
            continue
        match = _PIN_RE.match(line)
        if not match:
            continue
        name, version = match.groups()
        # strip extras, e.g. python-jose[cryptography] -> python-jose
        name = name.split("[")[0]
        pins[name] = version
    return pins


def _all_pins() -> dict[str, str]:
    pins = _parse_pins(REPO_ROOT / "requirements.txt")
    pins.update(_parse_pins(REPO_ROOT / "torch-requirements.txt"))
    return pins


@pytest.mark.parametrize("package_name,pinned_version", sorted(_all_pins().items()))
def test_installed_version_matches_pin(package_name, pinned_version):
    try:
        installed_version = importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        pytest.skip(f"{package_name} is not installed in this environment")

    # torch/torchaudio CUDA builds report versions like "2.7.0+cu118"; the
    # local build metadata suffix is allowed to differ (e.g. a CPU-only dev
    # build), but the base version must still match.
    installed_base = installed_version.split("+")[0]
    pinned_base = pinned_version.split("+")[0]
    assert installed_base == pinned_base, (
        f"{package_name} pinned at {pinned_version} in requirements, "
        f"but {installed_version} is installed"
    )


def test_python_version_matches_dockerfile_pin():
    dockerfile = (REPO_ROOT / "dockerfile").read_text()
    match = re.search(r"FROM python:(\d+)\.(\d+)", dockerfile)
    assert match, "Could not find a 'FROM python:X.Y' pin in the dockerfile"
    pinned_major, pinned_minor = (int(match.group(1)), int(match.group(2)))

    import os

    if not os.environ.get("RUNNING_IN_DOCKER"):
        pytest.skip(
            "Not running inside the project's Docker image - host and "
            "container Python versions are expected to differ. Set "
            "RUNNING_IN_DOCKER=1 to enforce this inside the image."
        )

    assert (sys.version_info.major, sys.version_info.minor) == (pinned_major, pinned_minor), (
        f"Dockerfile pins python:{pinned_major}.{pinned_minor}, but this "
        f"interpreter is {sys.version_info.major}.{sys.version_info.minor}"
    )


def test_torch_cuda_device_capability_is_supported_if_available():
    torch = pytest.importorskip("torch")

    if not torch.cuda.is_available():
        pytest.skip("CUDA is not available in this environment")

    device_index = torch.cuda.current_device()
    capability = torch.cuda.get_device_capability(device_index)
    capability_str = f"sm_{capability[0]}{capability[1]}"
    supported = torch.cuda.get_arch_list()

    assert capability_str in supported, (
        f"GPU compute capability {capability_str} is not in the set of "
        f"architectures this torch build supports ({supported}); "
        f"backend/processing/device_management.py would fall back to CPU."
    )
