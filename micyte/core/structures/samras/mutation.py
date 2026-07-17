from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .codec import encode_canonical_structure_from_addresses
from .structure import SamrasStructure, address_sort_key, as_text
from .structure import parent_address as parent_of_address
from .validation import InvalidSamrasStructure, validate_address_set


def _child_map(addresses: list[str] | tuple[str, ...]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for address in sorted([str(item) for item in addresses], key=address_sort_key):
        parent = parent_of_address(address)
        out.setdefault(parent, []).append(address)
    return out


def _normalize_address_mapping(addresses: list[str] | tuple[str, ...]) -> dict[str, str]:
    items = sorted([str(item) for item in addresses if as_text(item)], key=address_sort_key)
    children = _child_map(items)
    mapping: dict[str, str] = {}

    def _assign(old_address: str, new_address: str) -> None:
        mapping[old_address] = new_address
        for index, child in enumerate(children.get(old_address, ()), start=1):
            _assign(child, f"{new_address}-{index}")

    for index, root in enumerate(children.get("", ()), start=1):
        _assign(root, str(index))
    return mapping


def _subtree_addresses(addresses: list[str] | tuple[str, ...], root_address: str) -> tuple[str, ...]:
    token = as_text(root_address)
    return tuple(
        str(item)
        for item in addresses
        if str(item) == token or str(item).startswith(f"{token}-")
    )


def _remap_relative(branch_addresses: list[str] | tuple[str, ...], *, old_root: str, new_root: str) -> list[str]:
    remapped: list[str] = []
    old_root_token = as_text(old_root)
    new_root_token = as_text(new_root)
    for address in sorted([str(item) for item in branch_addresses], key=address_sort_key):
        if address == old_root_token:
            remapped.append(new_root_token)
            continue
        suffix = address[len(old_root_token) :]
        remapped.append(f"{new_root_token}{suffix}")
    return remapped


@dataclass(frozen=True)
class SamrasMutationResult:
    structure: SamrasStructure
    action: str
    address_mapping: dict[str, str]
    created_addresses: tuple[str, ...] = ()
    removed_addresses: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "samras_structure": self.structure.to_dict(),
            "canonical_magnitude": self.structure.bitstream,
            "address_mapping": {str(key): str(value) for key, value in self.address_mapping.items()},
            "created_addresses": [str(item) for item in self.created_addresses],
            "removed_addresses": [str(item) for item in self.removed_addresses],
        }


def rebuild_structure_from_addresses(
    addresses: list[str] | tuple[str, ...],
    *,
    root_ref: str = "0-0-5",
    warnings: list[str] | tuple[str, ...] = (),
) -> SamrasStructure:
    normalized = validate_address_set(addresses)
    return encode_canonical_structure_from_addresses(
        normalized,
        root_ref=root_ref,
        warnings=warnings,
    )


def add_root(structure: SamrasStructure) -> SamrasMutationResult:
    addresses = [str(item) for item in structure.addresses]
    next_root = str(len([item for item in addresses if "-" not in item]) + 1)
    updated = rebuild_structure_from_addresses(
        [*addresses, next_root],
        root_ref=structure.root_ref,
        warnings=structure.warnings,
    )
    mapping = {str(item): str(item) for item in structure.addresses}
    mapping[next_root] = next_root
    return SamrasMutationResult(
        structure=updated,
        action="add_root",
        address_mapping=mapping,
        created_addresses=(next_root,),
        removed_addresses=(),
    )


def add_child(structure: SamrasStructure, *, parent_address: str) -> SamrasMutationResult:
    parent = as_text(parent_address)
    if parent not in structure.address_map:
        raise InvalidSamrasStructure(f"parent address not found: {parent}")
    children = [address for address in structure.addresses if parent_of_address(address) == parent]
    next_child = f"{parent}-{len(children) + 1}"
    updated = rebuild_structure_from_addresses(
        [*list(structure.addresses), next_child],
        root_ref=structure.root_ref,
        warnings=structure.warnings,
    )
    mapping = {str(item): str(item) for item in structure.addresses}
    mapping[next_child] = next_child
    return SamrasMutationResult(
        structure=updated,
        action="add_child",
        address_mapping=mapping,
        created_addresses=(next_child,),
        removed_addresses=(),
    )


def remove_branch(structure: SamrasStructure, *, address_id: str) -> SamrasMutationResult:
    token = as_text(address_id)
    if token not in structure.address_map:
        raise InvalidSamrasStructure(f"address not found: {token}")
    removed = _subtree_addresses(structure.addresses, token)
    remaining = [address for address in structure.addresses if address not in removed]
    mapping = _normalize_address_mapping(remaining)
    normalized_remaining = [mapping[address] for address in sorted(remaining, key=address_sort_key)]
    updated = rebuild_structure_from_addresses(
        normalized_remaining,
        root_ref=structure.root_ref,
        warnings=structure.warnings,
    )
    return SamrasMutationResult(
        structure=updated,
        action="remove_branch",
        address_mapping=mapping,
        created_addresses=(),
        removed_addresses=removed,
    )


def move_branch(
    structure: SamrasStructure,
    *,
    from_address: str,
    to_parent_address: str,
) -> SamrasMutationResult:
    source = as_text(from_address)
    target_parent = as_text(to_parent_address)
    if source not in structure.address_map:
        raise InvalidSamrasStructure(f"address not found: {source}")
    if target_parent not in structure.address_map:
        raise InvalidSamrasStructure(f"target parent not found: {target_parent}")
    if target_parent == source or target_parent.startswith(f"{source}-"):
        raise InvalidSamrasStructure("cannot move a branch into itself")

    removed_branch = list(_subtree_addresses(structure.addresses, source))
    remaining = [address for address in structure.addresses if address not in removed_branch]
    remaining_mapping = _normalize_address_mapping(remaining)
    normalized_remaining = [remaining_mapping[address] for address in sorted(remaining, key=address_sort_key)]
    normalized_target_parent = remaining_mapping.get(target_parent, target_parent)
    existing_children = [
        address for address in normalized_remaining
        if parent_of_address(address) == normalized_target_parent
    ]
    new_root = f"{normalized_target_parent}-{len(existing_children) + 1}"
    remapped_branch = _remap_relative(removed_branch, old_root=source, new_root=new_root)
    updated = rebuild_structure_from_addresses(
        list(normalized_remaining) + list(remapped_branch),
        root_ref=structure.root_ref,
        warnings=structure.warnings,
    )
    branch_mapping = dict(remaining_mapping)
    for old_address, new_address in zip(
        sorted(removed_branch, key=address_sort_key),
        sorted(remapped_branch, key=address_sort_key), strict=False,
    ):
        branch_mapping[old_address] = new_address
    return SamrasMutationResult(
        structure=updated,
        action="move_branch",
        address_mapping=branch_mapping,
        created_addresses=(new_root,),
        removed_addresses=(),
    )


def set_child_count(
    structure: SamrasStructure,
    *,
    address_id: str,
    child_count: int,
) -> SamrasMutationResult:
    token = as_text(address_id)
    if token not in structure.address_map:
        raise InvalidSamrasStructure(f"address not found: {token}")
    target_count = int(child_count)
    if target_count < 0:
        raise InvalidSamrasStructure("child_count may not be negative")
    current_children = [address for address in structure.addresses if parent_of_address(address) == token]
    current_count = len(current_children)
    if target_count == current_count:
        return SamrasMutationResult(
            structure=structure,
            action="set_child_count",
            address_mapping={str(item): str(item) for item in structure.addresses},
            created_addresses=(),
            removed_addresses=(),
        )
    if target_count > current_count:
        created: list[str] = []
        addresses = list(structure.addresses)
        for ordinal in range(current_count + 1, target_count + 1):
            child = f"{token}-{ordinal}"
            created.append(child)
            addresses.append(child)
        updated = rebuild_structure_from_addresses(
            addresses,
            root_ref=structure.root_ref,
            warnings=structure.warnings,
        )
        mapping = {str(item): str(item) for item in structure.addresses}
        for address in created:
            mapping[address] = address
        return SamrasMutationResult(
            structure=updated,
            action="set_child_count",
            address_mapping=mapping,
            created_addresses=tuple(created),
            removed_addresses=(),
        )
    updated_structure = structure
    removed: list[str] = []
    while len([address for address in updated_structure.addresses if parent_of_address(address) == token]) > target_count:
        latest_child = sorted(
            [address for address in updated_structure.addresses if parent_of_address(address) == token],
            key=address_sort_key,
        )[-1]
        removed_result = remove_branch(updated_structure, address_id=latest_child)
        updated_structure = removed_result.structure
        removed.extend(list(removed_result.removed_addresses))
    return SamrasMutationResult(
        structure=updated_structure,
        action="set_child_count",
        address_mapping={str(item): str(item) for item in updated_structure.addresses},
        created_addresses=(),
        removed_addresses=tuple(removed),
    )
