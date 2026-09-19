from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MeetingAttendee")


@_attrs_define
class MeetingAttendee:
    """
    Attributes:
        guest (int | None | Unset):  Default: 0.
        member_id (int | None | Unset):
        name (None | str | Unset):
    """

    guest: int | None | Unset = 0
    member_id: int | None | Unset = UNSET
    name: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        guest: int | None | Unset
        if isinstance(self.guest, Unset):
            guest = UNSET
        else:
            guest = self.guest

        member_id: int | None | Unset
        if isinstance(self.member_id, Unset):
            member_id = UNSET
        else:
            member_id = self.member_id

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if guest is not UNSET:
            field_dict["guest"] = guest
        if member_id is not UNSET:
            field_dict["member_id"] = member_id
        if name is not UNSET:
            field_dict["name"] = name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_guest(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        guest = _parse_guest(d.pop("guest", UNSET))

        def _parse_member_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        member_id = _parse_member_id(d.pop("member_id", UNSET))

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        meeting_attendee = cls(
            guest=guest,
            member_id=member_id,
            name=name,
        )

        meeting_attendee.additional_properties = d
        return meeting_attendee

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
