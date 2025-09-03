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

from fastapi import APIRouter
from .upload import router as upload_router
from .status import router as status_router
from .group_members import router as group_members_router
from .groups import router as groups_router
from .meetings import router as meetings_router
from .users import router as users_router

router = APIRouter()
router.include_router(upload_router)
router.include_router(status_router)
router.include_router(group_members_router)
router.include_router(groups_router)
router.include_router(meetings_router)
router.include_router(users_router)
