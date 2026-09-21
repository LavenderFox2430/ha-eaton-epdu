"""Shared entity plumbing for the Eaton ePDU integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import EatonEpduCoordinator
from .model import UnitInfo


def base_id(entry: ConfigEntry) -> str:
    """Prefix for all unique IDs of this entry.

    The config entry's unique ID is the host unit's serial number, so entities
    survive removing and re-adding the integration.
    """
    return entry.unique_id or entry.entry_id


def device_id(entry: ConfigEntry, unit_index: int) -> str:
    """Stable device identifier for one unit on the chain."""
    return f"{base_id(entry)}_unit_{unit_index}"


def entity_name(label: str, column_name: str) -> str:
    """Join a row label and a column name without repeating a word.

    The column name is dropped only when the label already *starts* with it,
    which is the case the rule exists for: a contact the PDU calls
    "Contact 1" should not become "Contact 1 Contact". A label that merely
    contains the word keeps both parts -- an input named "Office Power" still
    needs "Office Power Power" for its wattage, or it would be
    indistinguishable from its apparent power.
    """
    label = (label or "").strip()
    if not label:
        return column_name
    if label.lower().startswith(column_name.lower()):
        return label
    return f"{label} {column_name}"


class EatonEpduEntity(CoordinatorEntity[EatonEpduCoordinator]):
    """Base entity bound to one unit of the chain."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EatonEpduCoordinator, unit_index: int) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._unit_index = unit_index
        self._entry = coordinator.entry

    @property
    def unit(self) -> UnitInfo | None:
        """The unit this entity belongs to, if it is still on the chain."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.units.get(self._unit_index)

    @property
    def device_info(self) -> DeviceInfo:
        """Describe the PDU this entity lives on."""
        unit = self.unit
        info = DeviceInfo(
            identifiers={(DOMAIN, device_id(self._entry, self._unit_index))},
            manufacturer=MANUFACTURER,
            name=unit.name if unit else f"ePDU unit {self._unit_index}",
        )
        if unit is None:
            return info
        if unit.part_number:
            info["model"] = unit.part_number
        if unit.firmware_version:
            info["sw_version"] = unit.firmware_version
        if unit.serial_number:
            info["serial_number"] = unit.serial_number
        if unit.is_host:
            info["configuration_url"] = f"http://{self.coordinator.host}"
        else:
            # Downstream units hang off the host in the device tree.
            host = next(
                (u.index for u in self.coordinator.data.units.values() if u.is_host),
                None,
            )
            if host is not None:
                info["via_device"] = (DOMAIN, device_id(self._entry, host))
        return info

    @property
    def available(self) -> bool:
        """A unit that dropped off the chain reports unavailable."""
        return super().available and self.unit is not None


@callback
def async_add_discovered(
    coordinator: EatonEpduCoordinator,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[], Iterable[Entity]],
) -> Callable[[], None]:
    """Add entities now and again whenever new rows appear.

    This is what makes a second PDU work without touching Home Assistant:
    when a unit is daisy-chained on, its rows show up in the next poll and its
    entities are created on the spot.
    """
    known: set[str] = set()
    signature: Any = object()

    @callback
    def _discover() -> None:
        nonlocal signature
        current = _rows_signature(coordinator)
        if current == signature:
            # Same rows as last poll: nothing can be new.
            return
        signature = current

        new: list[Entity] = []
        for entity in factory():
            unique_id: Any = getattr(entity, "unique_id", None)
            if unique_id is None or unique_id in known:
                continue
            known.add(unique_id)
            new.append(entity)
        if new:
            async_add_entities(new)

    _discover()
    return coordinator.async_add_listener(_discover)


def _rows_signature(coordinator: EatonEpduCoordinator) -> Any:
    """Cheap fingerprint of which rows exist, ignoring their values."""
    data = coordinator.data
    if data is None:
        return None
    return (
        tuple(sorted(data.units)),
        tuple(sorted((key, index) for key, rows in data.rows.items() for index in rows)),
        tuple(
            sorted(
                (key, index, column)
                for key, rows in data.extras.items()
                for index, columns in rows.items()
                for column in columns
            )
        ),
    )
