from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.group_member_out import GroupMemberOut


T = TypeVar("T", bound="GroupOut")


@_attrs_define
class GroupOut:
    """
    Attributes:
        created (datetime.datetime):
        id (int):
        members (list[GroupMemberOut]):
        name (str):
        github_repo_url (None | str | Unset):
        notify (bool | Unset):  Default: False.
        trello_board_id (None | str | Unset):
    """

    created: datetime.datetime
    id: int
    members: list[GroupMemberOut]
    name: str
    github_repo_url: None | str | Unset = UNSET
    notify: bool | Unset = False
    trello_board_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        created = self.created.isoformat()

        id = self.id

        members = []
        for members_item_data in self.members:
            members_item = members_item_data.to_dict()
            members.append(members_item)

        name = self.name

        github_repo_url: None | str | Unset
        if isinstance(self.github_repo_url, Unset):
            github_repo_url = UNSET
        else:
            github_repo_url = self.github_repo_url

        notify = self.notify

        trello_board_id: None | str | Unset
        if isinstance(self.trello_board_id, Unset):
            trello_board_id = UNSET
        else:
            trello_board_id = self.trello_board_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "created": created,
                "id": id,
                "members": members,
                "name": name,
            }
        )
        if github_repo_url is not UNSET:
            field_dict["github_repo_url"] = github_repo_url
        if notify is not UNSET:
            field_dict["notify"] = notify
        if trello_board_id is not UNSET:
            field_dict["trello_board_id"] = trello_board_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.group_member_out import GroupMemberOut  # noqa: PLC0415

        d = dict(src_dict)
        created = datetime.datetime.fromisoformat(d.pop("created"))

        id = d.pop("id")

        members = []
        _members = d.pop("members")
        for members_item_data in _members:
            members_item = GroupMemberOut.from_dict(members_item_data)

            members.append(members_item)

        name = d.pop("name")

        def _parse_github_repo_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        github_repo_url = _parse_github_repo_url(d.pop("github_repo_url", UNSET))

        notify = d.pop("notify", UNSET)

        def _parse_trello_board_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        trello_board_id = _parse_trello_board_id(d.pop("trello_board_id", UNSET))

        group_out = cls(
            created=created,
            id=id,
            members=members,
            name=name,
            github_repo_url=github_repo_url,
            notify=notify,
            trello_board_id=trello_board_id,
        )

        group_out.additional_properties = d
        return group_out

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
