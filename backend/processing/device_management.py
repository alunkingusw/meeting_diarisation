# Copyright 2025 Alun King
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import torch

def get_safe_device():
    """Return a safe device (GPU if available and supported, else CPU)."""
    if torch.cuda.is_available():
        try:
            device_index = torch.cuda.current_device()
            device_name = torch.cuda.get_device_name(device_index)
            device_capability = torch.cuda.get_device_capability(device_index)  # e.g. (6,1)
            device_sm = f"sm_{device_capability[0]}{device_capability[1]}"
            supported_arches = torch.cuda.get_arch_list()

            if device_sm not in supported_arches:
                return "cpu", (
                    f"GPU {device_name} (compute capability {device_capability}) "
                    f"is too old for this PyTorch build. Using CPU instead. "
                    f"To fix this, install a PyTorch build with support for sm_{device_capability[0]}{device_capability[1]}."
                )
            return f"cuda:{device_index}", f"Using GPU {device_name} (compute capability {device_capability})"
        except Exception as e:
            return "cpu", f"Error accessing CUDA device, falling back to CPU: {e}"
    return "cpu", "CUDA not available, using CPU."


def safe_run_model(model_fn, *args, **kwargs):
    """
    Run a model with safe device handling.
    Falls back to CPU if CUDA OOM or compatibility errors occur.
    """
    device, msg = get_safe_device()
    print(f"[Device Management] {msg}")

    try:
        return model_fn(*args, **kwargs)
    except RuntimeError as e:
        if "CUDA out of memory" in str(e) or "not compatible" in str(e):
            print("[Device Management] CUDA error detected, retrying on CPU.")
            return model_fn(device="cpu", *args, **kwargs)
        raise