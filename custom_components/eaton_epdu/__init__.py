"""The Eaton ePDU G3 integration."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import ATTR_CONFIG_ENTRY_ID, DOMAIN, SERVICE_DUMP_OIDS
from .coordinator import EatonEpduConfigEntry, EatonEpduCoordinator
from .oids import BASE_OID, SYS_OIDS
from .snmp import SnmpError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

DUMP_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: EatonEpduConfigEntry) -> bool:
    """Set up an ePDU from a config entry."""
    coordinator = EatonEpduCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EatonEpduConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: EatonEpduConfigEntry) -> None:
    """Reload when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: EatonEpduConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow deleting a unit that is no longer on the daisy chain."""
    coordinator = entry.runtime_data
    known = {
        f"{entry.unique_id or entry.entry_id}_unit_{index}"
        for index in (coordinator.data.units if coordinator.data else {})
    }
    return not any(identifier[1] in known for identifier in device.identifiers)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the integration-wide services once."""
    if hass.services.has_service(DOMAIN, SERVICE_DUMP_OIDS):
        return

    async def _dump_oids(call: ServiceCall) -> ServiceResponse:
        """Walk the PDU and write every OID it returns to a file.

        This is the troubleshooting tool: it shows exactly what your firmware
        exposes, including anything this integration does not map yet.
        """
        entries = [
            entry
            for entry in hass.config_entries.async_loaded_entries(DOMAIN)
            if ATTR_CONFIG_ENTRY_ID not in call.data
            or entry.entry_id == call.data[ATTR_CONFIG_ENTRY_ID]
        ]
        if not entries:
            raise ServiceValidationError("No loaded Eaton ePDU config entry found")

        result: dict[str, Any] = {}
        for entry in entries:
            coordinator: EatonEpduCoordinator = entry.runtime_data
            try:
                walk = await coordinator.client.walk(BASE_OID)
                system = await coordinator.client.get(list(SYS_OIDS.values()))
            except SnmpError as err:
                raise HomeAssistantError(f"SNMP dump failed: {err}") from err

            payload = {
                "host": coordinator.host,
                "system": {key: system.get(oid) for key, oid in SYS_OIDS.items()},
                "eaton": dict(sorted(walk.items())),
            }
            path = hass.config.path(f"eaton_epdu_dump_{coordinator.host}.json")
            await hass.async_add_executor_job(_write_json, path, payload)
            result[coordinator.host] = {"file": path, "oid_count": len(walk)}
            _LOGGER.info("Wrote %s OIDs from %s to %s", len(walk), coordinator.host, path)

        return {"dumps": result}

    hass.services.async_register(
        DOMAIN,
        SERVICE_DUMP_OIDS,
        _dump_oids,
        schema=DUMP_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _write_json(path: str, payload: dict[str, Any]) -> None:
    """Write the dump to disk."""
    Path(path).write_text(
        json.dumps(payload, indent=1, sort_keys=True, default=str), encoding="utf-8"
    )
