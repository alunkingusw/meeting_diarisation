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

from datetime import datetime
from pathlib import Path
from backend import models
from backend.db import Base, engine
from backend.config import settings

import logging

logging.basicConfig(level=logging.INFO)
logging.info("Starting application...")

# Record start time for uptime
START_TIME = datetime.now().astimezone()
logging.info(f"App start time: {START_TIME}")


settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
