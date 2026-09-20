"""Config flow for the Eaton ePDU G3 integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    UnitOfTemperature,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    AUTH_PROTOCOLS,
    CONF_AUTH_KEY,
    CONF_AUTH_PROTOCOL,
    CONF_COMMAND_DELAY,
    CONF_COMMUNITY,
    CONF_DETECTED_TEMPERATURE_UNIT,
    CONF_EXPOSE_UNMAPPED,
    CONF_MAX_REPETITIONS,
    CONF_PRIV_KEY,
    CONF_PRIV_PROTOCOL,
    CONF_RETRIES,
    CONF_SNMP_VERSION,
    CONF_TEMPERATURE_UNIT,
    CONF_TIMEOUT,
    CONF_WRITE_COMMUNITY,
    DEFAULT_COMMAND_DELAY,
    DEFAULT_COMMUNITY,
    DEFAULT_MAX_REPETITIONS,
    DEFAULT_PORT,
    DEFAULT_RETRIES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SNMP_VERSION,
    DEFAULT_TIMEOUT,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    PRIV_PROTOCOLS,
    SNMP_VERSIONS,
    TEMPERATURE_UNIT_AUTO,
    TEMPERATURE_UNIT_CHOICES,
    TEMPERATURE_UNIT_FAHRENHEIT,
    VERSION_V3,
)
from .coordinator import client_from_entry
from .model import build_units, detect_temperature_unit, parse_walk
from .oids import BASE_OID
from .snmp import SnmpClient, SnmpError

_LOGGER = logging.getLogger(__name__)


def _select(options: list[str]) -> SelectSelector:
    return SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN))


STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
        vol.Required(CONF_SNMP_VERSION, default=DEFAULT_SNMP_VERSION): _select(SNMP_VERSIONS),
    }
)

STEP_COMMUNITY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_COMMUNITY, default=DEFAULT_COMMUNITY): str,
        vol.Optional(CONF_WRITE_COMMUNITY): str,
    }
)

STEP_V3_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_AUTH_PROTOCOL, default="sha"): _select(AUTH_PROTOCOLS),
        vol.Optional(CONF_AUTH_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_PRIV_PROTOCOL, default="none"): _select(PRIV_PROTOCOLS),
        vol.Optional(CONF_PRIV_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


async def validate_connection(data: dict[str, Any]) -> dict[str, Any]:
    """Talk to the PDU and describe what is on the other end.

    Raises SnmpError when the PDU cannot be reached or refuses the credentials.
    """
    client: SnmpClient = client_from_entry(data, {})
    try:
        walk = await client.walk(BASE_OID)
        system = await client.get(["1.3.6.1.2.1.1.1.0", "1.3.6.1.2.1.1.5.0"])
    finally:
        client.close()

    if not walk:
        raise SnmpError("no_epdu_data")

    rows, _ = parse_walk(walk)
    units = build_units(rows)
    host_unit = next((unit for unit in units.values() if unit.is_host), None)
    temperature_unit = detect_temperature_unit(rows)

    return {
        "units": units,
        "host_unit": host_unit,
        "serial": host_unit.serial_number if host_unit else None,
        "title": (
            host_unit.name
            if host_unit and host_unit.name
            else system.get("1.3.6.1.2.1.1.5.0") or f"ePDU {data[CONF_HOST]}"
        ),
        "description": system.get("1.3.6.1.2.1.1.1.0"),
        "temperature_unit": temperature_unit,
        "oid_count": len(walk),
    }


def _error_for(err: Exception) -> str:
    """Translate an SNMP failure into a form error key."""
    message = str(err).lower()
    if "no_epdu_data" in message:
        return "no_epdu_data"
    auth_hints = (
        "digest",
        "unknown usm",
        "unknownusername",
        "unsupported security",
        "authentication",
    )
    if any(hint in message for hint in auth_hints):
        return "invalid_auth"
    reach_hints = ("timeout", "unreachable", "cannot reach", "no snmp response")
    if any(hint in message for hint in reach_hints):
        return "cannot_connect"
    return "unknown"


class EatonEpduConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the address and SNMP version."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

        self._data.update(user_input)
        if user_input[CONF_SNMP_VERSION] == VERSION_V3:
            return await self.async_step_v3()
        return await self.async_step_community()

    async def async_step_community(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for SNMPv1/v2c communities."""
        if user_input is None:
            return self.async_show_form(step_id="community", data_schema=STEP_COMMUNITY_SCHEMA)
        self._data.update(user_input)
        return await self._async_finish()

    async def async_step_v3(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for SNMPv3 credentials."""
        if user_input is None:
            return self.async_show_form(step_id="v3", data_schema=STEP_V3_SCHEMA)
        self._data.update(user_input)
        return await self._async_finish()

    async def _async_finish(self) -> ConfigFlowResult:
        """Validate and create (or update) the entry."""
        try:
            info = await validate_connection(self._data)
        except SnmpError as err:
            error = _error_for(err)
            _LOGGER.debug("ePDU validation failed: %s", err)
            return self._async_retry_credentials(error)
        except Exception:
            _LOGGER.exception("Unexpected error connecting to the ePDU")
            return self._async_retry_credentials("unknown")

        await self.async_set_unique_id(info["serial"] or self._data[CONF_HOST])
        options: dict[str, Any] = {}
        if info["temperature_unit"]:
            options[CONF_DETECTED_TEMPERATURE_UNIT] = info["temperature_unit"]

        if self.source == SOURCE_RECONFIGURE:
            self._abort_if_unique_id_mismatch(reason="wrong_device")
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(), data=self._data
            )

        self._abort_if_unique_id_configured(updates={CONF_HOST: self._data[CONF_HOST]})
        return self.async_create_entry(title=info["title"], data=self._data, options=options)

    @callback
    def _async_retry_credentials(self, error: str) -> ConfigFlowResult:
        """Re-show the credentials step with an error."""
        if self._data.get(CONF_SNMP_VERSION) == VERSION_V3:
            return self.async_show_form(
                step_id="v3", data_schema=STEP_V3_SCHEMA, errors={"base": error}
            )
        return self.async_show_form(
            step_id="community", data_schema=STEP_COMMUNITY_SCHEMA, errors={"base": error}
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address or credentials of an existing PDU."""
        entry = self._get_reconfigure_entry()
        if user_input is None:
            self._data = dict(entry.data)
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self.add_suggested_values_to_schema(STEP_USER_SCHEMA, entry.data),
            )
        self._data = {**dict(entry.data), **user_input}
        if user_input[CONF_SNMP_VERSION] == VERSION_V3:
            return await self.async_step_v3()
        return await self.async_step_community()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> EatonEpduOptionsFlow:
        """Return the options flow."""
        return EatonEpduOptionsFlow()


class EatonEpduOptionsFlow(OptionsFlow):
    """Polling and presentation options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and store the options."""
        if user_input is not None:
            options = dict(self.config_entry.options)
            options.update(user_input)
            if user_input.get(CONF_TEMPERATURE_UNIT) != TEMPERATURE_UNIT_AUTO:
                options[CONF_DETECTED_TEMPERATURE_UNIT] = (
                    UnitOfTemperature.FAHRENHEIT
                    if user_input[CONF_TEMPERATURE_UNIT] == TEMPERATURE_UNIT_FAHRENHEIT
                    else UnitOfTemperature.CELSIUS
                )
            return self.async_create_entry(data=options)

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL, max=3600, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_TIMEOUT, default=current.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=60, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_RETRIES, default=current.get(CONF_RETRIES, DEFAULT_RETRIES)
                ): NumberSelector(
                    NumberSelectorConfig(min=0, max=10, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_MAX_REPETITIONS,
                    default=current.get(CONF_MAX_REPETITIONS, DEFAULT_MAX_REPETITIONS),
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=100, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_COMMAND_DELAY,
                    default=current.get(CONF_COMMAND_DELAY, DEFAULT_COMMAND_DELAY),
                ): NumberSelector(
                    NumberSelectorConfig(min=0, max=30, step=0.5, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_TEMPERATURE_UNIT,
                    default=current.get(CONF_TEMPERATURE_UNIT, TEMPERATURE_UNIT_AUTO),
                ): _select(TEMPERATURE_UNIT_CHOICES),
                vol.Required(
                    CONF_EXPOSE_UNMAPPED,
                    default=current.get(CONF_EXPOSE_UNMAPPED, False),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
