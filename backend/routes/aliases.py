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

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, Optional
from backend.db_dependency import get_db, get_group_or_404
from backend.auth import is_email_workflow_group_member
from backend.validation import AliasResolveRequest
from backend.member_aliases import build_member_identity_map

router = APIRouter(prefix="/groups/{group_id}/aliases", tags=["aliases"])


@router.post("/resolve", response_model=Dict[str, Optional[int]])
def resolve_aliases(
        group_id: int,
        payload: AliasResolveRequest,
        db: Session = Depends(get_db),
        _principal = Depends(is_email_workflow_group_member),
    ):
    """Match each given name against this group's members by exact,
    case-insensitive name comparison. `source` is accepted but not
    currently used to vary matching behaviour."""
    group = get_group_or_404(db, group_id)
    members_by_name = build_member_identity_map(group.members)
    return {
        name: (member.id if (member := members_by_name.get(name.strip().casefold())) else None)
        for name in payload.names
    }
