from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar(
    "T", bound="ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost"
)


@_attrs_define
class ResolveAliasesGroupsGroupIdAliasesResolvePostResponseResolveAliasesGroupsGroupIdAliasesResolvePost:
    additional_properties: dict[str, int | None] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        resolve_aliases_groups_group_id_aliases_resolve_post_response_resolve_aliases_groups_group_id_aliases_resolve_post = cls()

        additional_properties = {}
        for prop_name, prop_dict in d.items():

            def _parse_additional_property(data: object) -> int | None:
                if data is None:
                    return data
                return cast(int | None, data)

            additional_property = _parse_additional_property(prop_dict)

            additional_properties[prop_name] = additional_property

        resolve_aliases_groups_group_id_aliases_resolve_post_response_resolve_aliases_groups_group_id_aliases_resolve_post.additional_properties = additional_properties
        return resolve_aliases_groups_group_id_aliases_resolve_post_response_resolve_aliases_groups_group_id_aliases_resolve_post

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> int | None:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: int | None) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
