"""Group-scoped matching between source names and canonical member records."""

from collections import defaultdict
from collections.abc import Iterable, Mapping

from backend.models import GroupMember


def build_member_identity_map(members: Iterable[GroupMember]) -> dict[str, GroupMember]:
    members = list(members)
    canonical: dict[str, GroupMember | None] = {}
    for member in members:
        name = (member.name or "").strip()
        if not name:
            continue
        key = name.casefold()
        existing = canonical.get(key)
        if existing is not None and existing.id != member.id:
            canonical[key] = None
        elif key not in canonical:
            canonical[key] = member

    alias_candidates: dict[str, dict[int, GroupMember]] = defaultdict(dict)
    for member in members:
        for alias in member.aliases or []:
            key = alias.strip().casefold()
            if key and key not in canonical:
                alias_candidates[key][member.id] = member

    identities = {key: member for key, member in canonical.items() if member is not None}
    identities.update(
        (key, candidates.popitem()[1])
        for key, candidates in alias_candidates.items()
        if len(candidates) == 1 and key not in canonical
    )
    return identities


def canonical_member_name(name: str | None, identities: Mapping[str, GroupMember]) -> str | None:
    if name is None:
        return None
    member = identities.get(name.strip().casefold())
    return member.name.strip() if member and member.name else name