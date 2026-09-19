from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="GroupMemberOut")


@_attrs_define
class GroupMemberOut:
    """
    Attributes:
        created (datetime.datetime):
        embedding_audio_path (None | str):
        id (int):
        name (str):
    """

    created: datetime.datetime
    embedding_audio_path: None | str
    id: int
    name: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        created = self.created.isoformat()

        embedding_audio_path: None | str
        embedding_audio_path = self.embedding_audio_path

        id = self.id

        name = self.name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "created": created,
                "embedding_audio_path": embedding_audio_path,
                "id": id,
                "name": name,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created = datetime.datetime.fromisoformat(d.pop("created"))

        def _parse_embedding_audio_path(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        embedding_audio_path = _parse_embedding_audio_path(d.pop("embedding_audio_path"))

        id = d.pop("id")

        name = d.pop("name")

        group_member_out = cls(
            created=created,
            embedding_audio_path=embedding_audio_path,
            id=id,
            name=name,
        )

        group_member_out.additional_properties = d
        return group_member_out

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
