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
from backend.db import Base, engine, SessionLocal
from backend.config import settings
from werkzeug.security import generate_password_hash

import logging

logging.basicConfig(level=logging.INFO)
logging.info("Starting application...")

# Record start time for uptime
START_TIME = datetime.now().astimezone()
logging.info(f"App start time: {START_TIME}")


settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def bootstrap_initial_admin() -> int | None:
	username = (settings.initial_admin_username or "").strip().lower()
	password = settings.initial_admin_password
	if not username and not password:
		return None
	if not username or not password:
		raise RuntimeError("INITIAL_ADMIN_USERNAME and INITIAL_ADMIN_PASSWORD must be set together")
	if len(password) < 12:
		raise RuntimeError("INITIAL_ADMIN_PASSWORD must be at least 12 characters")

	session = SessionLocal()
	try:
		if session.query(models.User.id).filter(models.User.is_admin.is_(True)).first():
			logging.info("Initial admin bootstrap skipped; an administrator already exists.")
			return None

		user = models.User(
			username=username,
			email=(settings.initial_admin_email or "").strip() or None,
			password_hash=generate_password_hash(password),
			is_admin=True,
		)
		session.add(user)
		session.commit()
		session.refresh(user)
		logging.info("Created initial administrator '%s' (id=%s).", username, user.id)
		return user.id
	except Exception:
		session.rollback()
		raise
	finally:
		session.close()
