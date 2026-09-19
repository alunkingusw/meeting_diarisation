from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="TranscriptSearchRequest")


@_attrs_define
class TranscriptSearchRequest:
    """
    Attributes:
        query (str):
        meeting_id (int | None | Unset):
    """

    query: str
    meeting_id: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        query = self.query

        meeting_id: int | None | Unset
        if isinstance(self.meeting_id, Unset):
            meeting_id = UNSET
        else:
            meeting_id = self.meeting_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "query": query,
            }
        )
        if meeting_id is not UNSET:
            field_dict["meeting_id"] = meeting_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        query = d.pop("query")

        def _parse_meeting_id(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        meeting_id = _parse_meeting_id(d.pop("meeting_id", UNSET))

        transcript_search_request = cls(
            query=query,
            meeting_id=meeting_id,
        )

        transcript_search_request.additional_properties = d
        return transcript_search_request

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
