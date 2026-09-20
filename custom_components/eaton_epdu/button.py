"""Buttons for the Eaton ePDU integration: power cycle and energy reset."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EatonEpduConfigEntry, EatonEpduCoordinator
from .entity import EatonEpduEntity, async_add_discovered, base_id, entity_name
from .oids import (
    GROUP_CONTROL_TABLE,
    OUTLET_CONTROL_TABLE,
    RESETTABLE,
    Column,
    Table,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EatonEpduConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up power-cycle and energy-reset buttons."""
    coordinator = entry.runtime_data

    def _factory() -> Iterable[Entity]:
        data = coordinator.data
        if data is None:
            return []
        entities: list[Entity] = []

        for table, enabled in ((OUTLET_CONTROL_TABLE, True), (GROUP_CONTROL_TABLE, False)):
            for index, row in data.rows.get(table.key, {}).items():
                if "reboot_cmd" in row:
                    entities.append(EpduCycleButton(coordinator, table, index, enabled))

        # One reset per Wh counter the PDU actually reports...
        for table, column in RESETTABLE:
            for index, row in data.rows.get(table.key, {}).items():
                if column.key in row:
                    entities.append(EpduEnergyResetButton(coordinator, table, index, column))

        # ...plus one per unit that clears every counter on that PDU.
        for unit_index in data.units:
            if _resets_for_unit(coordinator, unit_index):
                entities.append(EpduEnergyResetAllButton(coordinator, unit_index))
        return entities

    entry.async_on_unload(async_add_discovered(coordinator, async_add_entities, _factory))


def _resets_for_unit(
    coordinator: EatonEpduCoordinator, unit_index: int
) -> list[tuple[str, tuple[int, ...], str]]:
    """Every (table, row, column) holding a Wh counter on one unit."""
    data = coordinator.data
    if data is None:
        return []
    return [
        (table.key, index, column.key)
        for table, column in RESETTABLE
        for index, row in data.rows.get(table.key, {}).items()
        if index and index[0] == unit_index and column.key in row
    ]


class EpduCycleButton(EatonEpduEntity, ButtonEntity):
    """Power cycles one outlet or group.

    The PDU keeps the outlet off for its own configured reboot-off time, which
    is exposed as the "Reboot off time" diagnostic sensor.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:restart"

    def __init__(
        self,
        coordinator: EatonEpduCoordinator,
        table: Table,
        index: tuple[int, ...],
        enabled_default: bool,
    ) -> None:
        """Initialise the button."""
        super().__init__(coordinator, index[0])
        self._table = table
        self._index = index
        self._attr_unique_id = (
            f"{base_id(coordinator.entry)}_{table.key}_"
            f"{'_'.join(str(part) for part in index)}_cycle"
        )
        self._attr_entity_registry_enabled_default = enabled_default

    @property
    def name(self) -> str:
        """Named after the outlet or group, as named on the PDU."""
        label = ""
        if self.coordinator.data is not None:
            label = self.coordinator.data.label(self._table.key, self._index)
        return entity_name(label, "Power cycle")

    @property
    def available(self) -> bool:
        """Available while the control row is still being reported."""
        if not super().available or self.coordinator.data is None:
            return False
        return self._index in self.coordinator.data.rows.get(self._table.key, {})

    async def async_press(self) -> None:
        """Power cycle the outlet."""
        await self.coordinator.async_send_command(self._table.key, self._index, "cycle")


class EpduEnergyResetButton(EatonEpduEntity, ButtonEntity):
    """Resets one Wh counter on the PDU itself.

    This is a trip meter, not a Home Assistant helper: the counter is zeroed
    on the hardware, exactly as the PDU's own web UI does it, and the reading
    restarts from 0 for every consumer of that OID. It cannot be undone.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:counter"

    def __init__(
        self,
        coordinator: EatonEpduCoordinator,
        table: Table,
        index: tuple[int, ...],
        column: Column,
    ) -> None:
        """Initialise the button."""
        super().__init__(coordinator, index[0])
        self._table = table
        self._index = index
        self._column = column
        self._attr_unique_id = (
            f"{base_id(coordinator.entry)}_{table.key}_"
            f"{'_'.join(str(part) for part in index)}_{column.key}_reset"
        )

    @property
    def name(self) -> str:
        """e.g. "Outlet A1 Reset energy"."""
        label = ""
        if self._table.use_label_for_entities and self.coordinator.data is not None:
            label = self.coordinator.data.label(self._table.key, self._index)
        return entity_name(label, f"Reset {self._column.name.lower()}")

    @property
    def available(self) -> bool:
        """Available while the counter is still being reported."""
        if not super().available or self.coordinator.data is None:
            return False
        row = self.coordinator.data.rows.get(self._table.key, {}).get(self._index, {})
        return self._column.key in row

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Show what will be cleared, and when it was last cleared."""
        attributes: dict[str, Any] = {
            "mib_object": self._column.mib,
            "oid": self.coordinator.command_oid(self._table, self._index, self._column.key),
        }
        if self.coordinator.data is not None:
            row = self.coordinator.data.rows.get(self._table.key, {}).get(self._index, {})
            attributes["current_wh"] = row.get(self._column.key)
        return attributes

    async def async_press(self) -> None:
        """Zero the counter on the PDU."""
        await self.coordinator.async_reset_energy(
            [(self._table.key, self._index, self._column.key)]
        )


class EpduEnergyResetAllButton(EatonEpduEntity, ButtonEntity):
    """Resets every Wh counter on one unit -- inputs, groups and outlets."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: EatonEpduCoordinator, unit_index: int) -> None:
        """Initialise the button."""
        super().__init__(coordinator, unit_index)
        self._attr_unique_id = f"{base_id(coordinator.entry)}_reset_all_energy_{unit_index}"
        self._attr_name = "Reset all energy counters"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """How many counters the press would clear."""
        return {"counters": len(_resets_for_unit(self.coordinator, self._unit_index))}

    async def async_press(self) -> None:
        """Zero every counter on this unit."""
        await self.coordinator.async_reset_energy(
            _resets_for_unit(self.coordinator, self._unit_index)
        )
