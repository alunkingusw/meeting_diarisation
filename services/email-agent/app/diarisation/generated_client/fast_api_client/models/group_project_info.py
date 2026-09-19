from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="GroupProjectInfo")


@_attrs_define
class GroupProjectInfo:
    """
    Attributes:
        github_repo_url (str):
        group_id (int):
        group_name (str):
        trello_board_id (None | str | Unset):
    """

    github_repo_url: str
    group_id: int
    group_name: str
    trello_board_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        github_repo_url = self.github_repo_url

        group_id = self.group_id

        group_name = self.group_name

        trello_board_id: None | str | Unset
        if isinstance(self.trello_board_id, Unset):
            trello_board_id = UNSET
        else:
            trello_board_id = self.trello_board_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "github_repo_url": github_repo_url,
                "group_id": group_id,
                "group_name": group_name,
            }
        )
        if trello_board_id is not UNSET:
            field_dict["trello_board_id"] = trello_board_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        github_repo_url = d.pop("github_repo_url")

        group_id = d.pop("group_id")

        group_name = d.pop("group_name")

        def _parse_trello_board_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        trello_board_id = _parse_trello_board_id(d.pop("trello_board_id", UNSET))

        group_project_info = cls(
            github_repo_url=github_repo_url,
            group_id=group_id,
            group_name=group_name,
            trello_board_id=trello_board_id,
        )

        group_project_info.additional_properties = d
        return group_project_info

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
