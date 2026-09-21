"""Polling coordinator for the Eaton ePDU integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AUTH_KEY,
    CONF_AUTH_PROTOCOL,
    CONF_COMMAND_DELAY,
    CONF_COMMUNITY,
    CONF_DETECTED_TEMPERATURE_UNIT,
    CONF_MAX_REPETITIONS,
    CONF_PRIV_KEY,
    CONF_PRIV_PROTOCOL,
    CONF_RETRIES,
    CONF_SNMP_VERSION,
    CONF_TEMPERATURE_UNIT,
    CONF_TIMEOUT,
    CONF_WRITE_COMMUNITY,
    DEFAULT_COMMAND_DELAY,
    DEFAULT_MAX_REPETITIONS,
    DEFAULT_PORT,
    DEFAULT_RETRIES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SNMP_VERSION,
    DEFAULT_TIMEOUT,
    DOMAIN,
    TEMPERATURE_UNIT_AUTO,
    TEMPERATURE_UNIT_FAHRENHEIT,
)
from .model import EpduData, build_data
from .oids import BASE_OID, SYS_OIDS, TABLES_BY_KEY, Table
from .snmp import SnmpClient, SnmpError

_LOGGER = logging.getLogger(__name__)

type EatonEpduConfigEntry = ConfigEntry[EatonEpduCoordinator]


def _write_hint(err: Exception) -> str:
    """Explain an SNMP SET failure without guessing at the cause."""
    message = str(err)
    lowered = message.lower()
    if "wrongtype" in lowered or "badvalue" in lowered:
        return (
            f"{message}. The agent rejected the value's type, which is a bug in "
            "this integration rather than a permission problem -- please report "
            "it with the OID above."
        )
    if any(hint in lowered for hint in ("noaccess", "notwritable", "authorizationerror")):
        return (
            f"{message}. The SNMP user is read-only: for SNMPv3 give it "
            "read/write rights on the PDU, for v1/v2c set a write community."
        )
    return message


def client_from_entry(entry_data: dict[str, Any], options: dict[str, Any]) -> SnmpClient:
    """Build an SNMP client from stored config entry data."""
    return SnmpClient(
        host=entry_data[CONF_HOST],
        port=entry_data.get(CONF_PORT, DEFAULT_PORT),
        version=entry_data.get(CONF_SNMP_VERSION, DEFAULT_SNMP_VERSION),
        community=entry_data.get(CONF_COMMUNITY),
        write_community=entry_data.get(CONF_WRITE_COMMUNITY),
        username=entry_data.get(CONF_USERNAME),
        auth_protocol=entry_data.get(CONF_AUTH_PROTOCOL, "none"),
        auth_key=entry_data.get(CONF_AUTH_KEY) or entry_data.get(CONF_PASSWORD),
        priv_protocol=entry_data.get(CONF_PRIV_PROTOCOL, "none"),
        priv_key=entry_data.get(CONF_PRIV_KEY),
        # Number selectors hand back floats.
        timeout=int(options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)),
        retries=int(options.get(CONF_RETRIES, DEFAULT_RETRIES)),
        max_repetitions=int(options.get(CONF_MAX_REPETITIONS, DEFAULT_MAX_REPETITIONS)),
    )


class EatonEpduCoordinator(DataUpdateCoordinator[EpduData]):
    """Walks the Eaton subtree on a schedule and hands out the parsed model."""

    config_entry: EatonEpduConfigEntry

    def __init__(self, hass: HomeAssistant, entry: EatonEpduConfigEntry) -> None:
        """Initialise the coordinator."""
        self.entry = entry
        self.client = client_from_entry(dict(entry.data), dict(entry.options))
        self.host: str = entry.data[CONF_HOST]
        self._command_lock = asyncio.Lock()

        configured = entry.options.get(CONF_TEMPERATURE_UNIT, TEMPERATURE_UNIT_AUTO)
        if configured == TEMPERATURE_UNIT_AUTO:
            self._temperature_unit = entry.options.get(
                CONF_DETECTED_TEMPERATURE_UNIT, UnitOfTemperature.CELSIUS
            )
            self._temperature_forced = False
        else:
            self._temperature_unit = (
                UnitOfTemperature.FAHRENHEIT
                if configured == TEMPERATURE_UNIT_FAHRENHEIT
                else UnitOfTemperature.CELSIUS
            )
            self._temperature_forced = True

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {self.host}",
            update_interval=timedelta(
                seconds=float(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            ),
        )

    @property
    def temperature_unit(self) -> str:
        """Scale the host unit reports temperatures in."""
        return self._temperature_unit

    def temperature_unit_for(self, unit_index: int) -> str:
        """Scale one unit reports temperatures in.

        Each unit on the chain has its own temperatureScale setting, so a
        mixed chain is handled per device.
        """
        if self._temperature_forced or self.data is None:
            return self._temperature_unit
        return self.data.temperature_unit_for(unit_index)

    async def _async_update_data(self) -> EpduData:
        """Walk the PDU and parse the result."""
        try:
            raw = await self.client.walk(BASE_OID)
            sys_raw = await self.client.get(list(SYS_OIDS.values()))
        except SnmpError as err:
            raise UpdateFailed(f"SNMP error talking to {self.host}: {err}") from err

        if not raw:
            raise UpdateFailed(
                f"{self.host} answered but returned no Eaton ePDU data "
                f"({BASE_OID}); check that the SNMP user has read access"
            )

        sys_values = {key: sys_raw.get(oid) for key, oid in SYS_OIDS.items()}
        data = build_data(raw, sys_values, self._temperature_unit)
        if self._temperature_forced:
            data.temperature_unit = self._temperature_unit
            data.temperature_units = dict.fromkeys(data.temperature_units, self._temperature_unit)
        else:
            self._temperature_unit = data.temperature_unit
        return data

    # -- control -------------------------------------------------------------
    def command_oid(self, table: Table, index: tuple[int, ...], column_key: str) -> str:
        """Build the OID of a command column for one row."""
        column = table.column_by_key(column_key)
        if column is None:
            raise HomeAssistantError(f"Unknown command column {column_key}")
        suffix = ".".join(str(part) for part in index)
        return f"{table.oid}.{column.column}.{suffix}"

    async def async_send_command(
        self,
        table_key: str,
        index: tuple[int, ...],
        command: str,
        delay: int = 0,
    ) -> None:
        """Write an outlet/group command and refresh once it has taken effect.

        Eaton command columns take a delay in seconds: 0 acts immediately and
        -1 cancels a pending action.
        """
        table = TABLES_BY_KEY[table_key]
        column_key = {"on": "on_cmd", "off": "off_cmd", "cycle": "reboot_cmd"}[command]
        oid = self.command_oid(table, index, column_key)
        column = table.column_by_key(column_key)
        syntax = column.write_syntax if column else "Integer32"

        async with self._command_lock:
            try:
                await self.client.set_value(oid, delay, syntax)
            except SnmpError as err:
                raise HomeAssistantError(
                    f"Failed to send '{command}' to {self.host} ({oid}): {_write_hint(err)}"
                ) from err

            settle = self.entry.options.get(CONF_COMMAND_DELAY, DEFAULT_COMMAND_DELAY)
            await asyncio.sleep(max(0.0, float(delay) + float(settle)))
        await self.async_request_refresh()

    async def async_reset_energy(self, resets: list[tuple[str, tuple[int, ...], str]]) -> None:
        """Zero one or more Wh counters on the PDU.

        The Eaton Wh objects are read-write: writing 0 clears the counter and
        restarts its timer, which is what the PDU web UI does too. There is no
        undo, and the cleared total is gone from the device.
        """
        async with self._command_lock:
            for table_key, index, column_key in resets:
                table = TABLES_BY_KEY[table_key]
                column = table.column_by_key(column_key)
                oid = self.command_oid(table, index, column_key)
                try:
                    await self.client.set_value(
                        oid, 0, column.write_syntax if column else "Unsigned32"
                    )
                except SnmpError as err:
                    raise HomeAssistantError(
                        f"Failed to reset the energy counter on {self.host} "
                        f"({oid}): {_write_hint(err)}"
                    ) from err
                _LOGGER.info("Reset %s %s on %s", table_key, index, self.host)
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Close the SNMP engine."""
        await super().async_shutdown()
        self.client.close()
