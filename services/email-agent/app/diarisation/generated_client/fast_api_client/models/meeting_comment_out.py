from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="MeetingCommentOut")


@_attrs_define
class MeetingCommentOut:
    """
    Attributes:
        comment (str):
        created (datetime.datetime):
        id (int):
        meeting_id (int):
        user_id (int):
    """

    comment: str
    created: datetime.datetime
    id: int
    meeting_id: int
    user_id: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        comment = self.comment

        created = self.created.isoformat()

        id = self.id

        meeting_id = self.meeting_id

        user_id = self.user_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "comment": comment,
                "created": created,
                "id": id,
                "meeting_id": meeting_id,
                "user_id": user_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        comment = d.pop("comment")

        created = datetime.datetime.fromisoformat(d.pop("created"))

        id = d.pop("id")

        meeting_id = d.pop("meeting_id")

        user_id = d.pop("user_id")

        meeting_comment_out = cls(
            comment=comment,
            created=created,
            id=id,
            meeting_id=meeting_id,
            user_id=user_id,
        )

        meeting_comment_out.additional_properties = d
        return meeting_comment_out

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
