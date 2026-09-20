"""Binary sensors (dry contacts) for the Eaton ePDU integration."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import NOT_AVAILABLE
from .coordinator import EatonEpduConfigEntry, EatonEpduCoordinator
from .entity import EatonEpduEntity, async_add_discovered, base_id, entity_name
from .oids import PROBE_OK_STATES, TABLES, Column, Table


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EatonEpduConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors for every contact the PDU reports."""
    coordinator = entry.runtime_data

    def _factory() -> Iterable[Entity]:
        data = coordinator.data
        if data is None:
            return []
        return [
            EpduBinarySensor(coordinator, table, index, column)
            for table in TABLES
            for column in table.columns
            if column.platform == "binary_sensor"
            for index in data.rows.get(table.key, {})
        ]

    entry.async_on_unload(async_add_discovered(coordinator, async_add_entities, _factory))


class EpduBinarySensor(EatonEpduEntity, BinarySensorEntity):
    """A dry contact input.

    A contact on a unit with no environmental module reports unknown, and its
    attributes say N/A, rather than defaulting to "open".
    """

    def __init__(
        self,
        coordinator: EatonEpduCoordinator,
        table: Table,
        index: tuple[int, ...],
        column: Column,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, index[0])
        self._table = table
        self._index = index
        self._column = column
        self._attr_unique_id = (
            f"{base_id(coordinator.entry)}_{table.key}_"
            f"{'_'.join(str(part) for part in index)}_{column.key}"
        )
        self._attr_entity_category = (
            EntityCategory(column.entity_category) if column.entity_category else None
        )
        self._attr_entity_registry_enabled_default = column.enabled_default

    @property
    def name(self) -> str:
        """Named after the contact, as named on the PDU."""
        label = ""
        if self.coordinator.data is not None:
            label = self.coordinator.data.label(self._table.key, self._index)
        return entity_name(label, self._column.name)

    @property
    def _row(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        return self.coordinator.data.rows.get(self._table.key, {}).get(self._index, {})

    @property
    def is_on(self) -> bool | None:
        """True when the contact is closed; None when it cannot be read."""
        row = self._row
        if "probe_status" in row and row["probe_status"] not in PROBE_OK_STATES:
            return None
        value = row.get(self._column.key)
        if not isinstance(value, int) or self._column.on_states is None:
            return None
        if value in self._column.na_values:
            return None
        if value in self._column.on_states:
            return True
        if self._column.enum and value in self._column.enum:
            return False
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Raw state and probe status, as N/A when unreadable."""
        row = self._row
        value = row.get(self._column.key)
        enum = self._column.enum or {}
        status = row.get("probe_status")
        status_column = self._table.column_by_key("probe_status")
        status_enum = status_column.enum if status_column else None
        return {
            "state": enum.get(value, NOT_AVAILABLE) if isinstance(value, int) else NOT_AVAILABLE,
            "probe_status": (
                (status_enum or {}).get(status, NOT_AVAILABLE)
                if isinstance(status, int)
                else NOT_AVAILABLE
            ),
        }

    @property
    def available(self) -> bool:
        """Available while the row is still being reported."""
        if not super().available or self.coordinator.data is None:
            return False
        return self._index in self.coordinator.data.rows.get(self._table.key, {})
