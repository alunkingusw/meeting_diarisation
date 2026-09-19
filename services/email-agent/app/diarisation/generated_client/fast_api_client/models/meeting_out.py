from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.meeting_attendee_out import MeetingAttendeeOut
    from ..models.raw_file_out import RawFileOut


T = TypeVar("T", bound="MeetingOut")


@_attrs_define
class MeetingOut:
    """
    Attributes:
        attendees (list[MeetingAttendeeOut]):
        created (datetime.datetime):
        date (datetime.datetime):
        group_id (int):
        id (int):
        media_files (list[RawFileOut]):
        summary (None | str | Unset):
        summary_generated_at (datetime.datetime | None | Unset):
    """

    attendees: list[MeetingAttendeeOut]
    created: datetime.datetime
    date: datetime.datetime
    group_id: int
    id: int
    media_files: list[RawFileOut]
    summary: None | str | Unset = UNSET
    summary_generated_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        attendees = []
        for attendees_item_data in self.attendees:
            attendees_item = attendees_item_data.to_dict()
            attendees.append(attendees_item)

        created = self.created.isoformat()

        date = self.date.isoformat()

        group_id = self.group_id

        id = self.id

        media_files = []
        for media_files_item_data in self.media_files:
            media_files_item = media_files_item_data.to_dict()
            media_files.append(media_files_item)

        summary: None | str | Unset
        if isinstance(self.summary, Unset):
            summary = UNSET
        else:
            summary = self.summary

        summary_generated_at: None | str | Unset
        if isinstance(self.summary_generated_at, Unset):
            summary_generated_at = UNSET
        elif isinstance(self.summary_generated_at, datetime.datetime):
            summary_generated_at = self.summary_generated_at.isoformat()
        else:
            summary_generated_at = self.summary_generated_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "attendees": attendees,
                "created": created,
                "date": date,
                "group_id": group_id,
                "id": id,
                "media_files": media_files,
            }
        )
        if summary is not UNSET:
            field_dict["summary"] = summary
        if summary_generated_at is not UNSET:
            field_dict["summary_generated_at"] = summary_generated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.meeting_attendee_out import MeetingAttendeeOut  # noqa: PLC0415
        from ..models.raw_file_out import RawFileOut  # noqa: PLC0415

        d = dict(src_dict)
        attendees = []
        _attendees = d.pop("attendees")
        for attendees_item_data in _attendees:
            attendees_item = MeetingAttendeeOut.from_dict(attendees_item_data)

            attendees.append(attendees_item)

        created = datetime.datetime.fromisoformat(d.pop("created"))

        date = datetime.datetime.fromisoformat(d.pop("date"))

        group_id = d.pop("group_id")

        id = d.pop("id")

        media_files = []
        _media_files = d.pop("media_files")
        for media_files_item_data in _media_files:
            media_files_item = RawFileOut.from_dict(media_files_item_data)

            media_files.append(media_files_item)

        def _parse_summary(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        summary = _parse_summary(d.pop("summary", UNSET))

        def _parse_summary_generated_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                summary_generated_at_type_0 = datetime.datetime.fromisoformat(data)

                return summary_generated_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        summary_generated_at = _parse_summary_generated_at(d.pop("summary_generated_at", UNSET))

        meeting_out = cls(
            attendees=attendees,
            created=created,
            date=date,
            group_id=group_id,
            id=id,
            media_files=media_files,
            summary=summary,
            summary_generated_at=summary_generated_at,
        )

        meeting_out.additional_properties = d
        return meeting_out

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
