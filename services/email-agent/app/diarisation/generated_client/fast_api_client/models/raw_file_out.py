from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.raw_file_type import RawFileType

T = TypeVar("T", bound="RawFileOut")


@_attrs_define
class RawFileOut:
    """
    Attributes:
        description (None | str):
        file_name (str):
        human_name (str):
        id (int):
        processed_date (datetime.datetime | None):
        type_ (RawFileType):
    """

    description: None | str
    file_name: str
    human_name: str
    id: int
    processed_date: datetime.datetime | None
    type_: RawFileType
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        description: None | str
        description = self.description

        file_name = self.file_name

        human_name = self.human_name

        id = self.id

        processed_date: None | str
        if isinstance(self.processed_date, datetime.datetime):
            processed_date = self.processed_date.isoformat()
        else:
            processed_date = self.processed_date

        type_ = self.type_.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "description": description,
                "file_name": file_name,
                "human_name": human_name,
                "id": id,
                "processed_date": processed_date,
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_description(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        description = _parse_description(d.pop("description"))

        file_name = d.pop("file_name")

        human_name = d.pop("human_name")

        id = d.pop("id")

        def _parse_processed_date(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                processed_date_type_0 = datetime.datetime.fromisoformat(data)

                return processed_date_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        processed_date = _parse_processed_date(d.pop("processed_date"))

        type_ = RawFileType(d.pop("type"))

        raw_file_out = cls(
            description=description,
            file_name=file_name,
            human_name=human_name,
            id=id,
            processed_date=processed_date,
            type_=type_,
        )

        raw_file_out.additional_properties = d
        return raw_file_out

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
