"""Outlet and group switches for the Eaton ePDU integration."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import voluptuous as vol
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_DELAY,
    SERVICE_OUTLET_CYCLE,
    SERVICE_OUTLET_OFF,
    SERVICE_OUTLET_ON,
)
from .coordinator import EatonEpduConfigEntry, EatonEpduCoordinator
from .entity import EatonEpduEntity, async_add_discovered, base_id
from .oids import GROUP_CONTROL_TABLE, OUTLET_CONTROL_TABLE, Table

#: Status values that mean the outlet is (about to be) energised.
_ON_STATES = (1, 3)
_OFF_STATES = (0, 2)

DELAY_SCHEMA = {
    vol.Optional(ATTR_DELAY, default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=7200))
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EatonEpduConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a switch for every controllable outlet and group."""
    coordinator = entry.runtime_data

    def _factory() -> Iterable[Entity]:
        data = coordinator.data
        if data is None:
            return []
        entities: list[Entity] = []
        for table, enabled in ((OUTLET_CONTROL_TABLE, True), (GROUP_CONTROL_TABLE, False)):
            for index, row in data.rows.get(table.key, {}).items():
                # Only rows that actually expose the command columns can be
                # switched; a metered-only PDU has none.
                if "on_cmd" not in row or "off_cmd" not in row:
                    continue
                entities.append(EpduControlSwitch(coordinator, table, index, enabled))
        return entities

    entry.async_on_unload(async_add_discovered(coordinator, async_add_entities, _factory))

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(SERVICE_OUTLET_ON, DELAY_SCHEMA, "async_service_on")
    platform.async_register_entity_service(SERVICE_OUTLET_OFF, DELAY_SCHEMA, "async_service_off")
    platform.async_register_entity_service(
        SERVICE_OUTLET_CYCLE, DELAY_SCHEMA, "async_service_cycle"
    )


class EpduControlSwitch(EatonEpduEntity, SwitchEntity):
    """Switches one outlet (or one outlet group) of a unit."""

    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(
        self,
        coordinator: EatonEpduCoordinator,
        table: Table,
        index: tuple[int, ...],
        enabled_default: bool,
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, index[0])
        self._table = table
        self._index = index
        self._attr_unique_id = (
            f"{base_id(coordinator.entry)}_{table.key}_"
            f"{'_'.join(str(part) for part in index)}_switch"
        )
        self._attr_entity_registry_enabled_default = enabled_default

    @property
    def name(self) -> str:
        """Named after the outlet or group, as named on the PDU."""
        label = ""
        if self.coordinator.data is not None:
            label = self.coordinator.data.label(self._table.key, self._index)
        return label or f"{self._table.singular} {self._index[-1]}"

    @property
    def is_on(self) -> bool | None:
        """True while the outlet is on; None when the status is unknown."""
        if self.coordinator.data is None:
            return None
        status = self.coordinator.data.value(self._table.key, self._index, "status")
        if status in _ON_STATES:
            return True
        if status in _OFF_STATES:
            return False
        return None

    @property
    def available(self) -> bool:
        """Available while the control row is still being reported."""
        if not super().available or self.coordinator.data is None:
            return False
        return self._index in self.coordinator.data.rows.get(self._table.key, {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose what the PDU says about this outlet's switching."""
        if self.coordinator.data is None:
            return {}
        row = self.coordinator.data.rows.get(self._table.key, {}).get(self._index, {})
        attributes: dict[str, Any] = {"unit": self._index[0], "index": self._index[-1]}
        for key in ("switchable", "power_on_state", "sequence_delay", "reboot_off_time"):
            if key in row:
                attributes[key] = row[key]
        return attributes

    # -- commands ------------------------------------------------------------
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the outlet on."""
        await self.coordinator.async_send_command(self._table.key, self._index, "on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the outlet off."""
        await self.coordinator.async_send_command(self._table.key, self._index, "off")

    async def async_service_on(self, delay: int = 0) -> None:
        """Turn on after a delay, in seconds."""
        await self.coordinator.async_send_command(self._table.key, self._index, "on", delay)

    async def async_service_off(self, delay: int = 0) -> None:
        """Turn off after a delay, in seconds."""
        await self.coordinator.async_send_command(self._table.key, self._index, "off", delay)

    async def async_service_cycle(self, delay: int = 0) -> None:
        """Power cycle after a delay, in seconds."""
        await self.coordinator.async_send_command(self._table.key, self._index, "cycle", delay)
