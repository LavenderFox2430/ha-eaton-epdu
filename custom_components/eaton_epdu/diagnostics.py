"""Diagnostics for the Eaton ePDU integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_AUTH_KEY, CONF_COMMUNITY, CONF_PRIV_KEY, CONF_WRITE_COMMUNITY
from .coordinator import EatonEpduConfigEntry

TO_REDACT = {
    CONF_AUTH_KEY,
    CONF_COMMUNITY,
    CONF_PRIV_KEY,
    CONF_WRITE_COMMUNITY,
    "password",
    "username",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EatonEpduConfigEntry
) -> dict[str, Any]:
    """Return the full picture: config, parsed model and the raw walk.

    The raw walk is the useful part when something is missing or mislabelled:
    it shows every OID the PDU returned, mapped or not.
    """
    coordinator = entry.runtime_data
    data = coordinator.data

    diagnostics: dict[str, Any] = {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "unique_id_set": entry.unique_id is not None,
        },
        "temperature_unit": coordinator.temperature_unit,
    }

    if data is None:
        diagnostics["error"] = "no data yet"
        return diagnostics

    diagnostics["system"] = data.sys
    diagnostics["units_present"] = data.units_present
    diagnostics["units"] = {str(k): asdict(v) for k, v in data.units.items()}
    diagnostics["environment"] = {
        str(unit): {"state": summary.state, "attributes": summary.attributes}
        for unit, summary in data.environment.items()
    }
    diagnostics["rows"] = {
        table: {".".join(map(str, index)): row for index, row in rows.items()}
        for table, rows in data.rows.items()
        if rows
    }
    diagnostics["unmapped_columns"] = {
        table: {
            ".".join(map(str, index)): {str(col): value for col, value in columns.items()}
            for index, columns in rows.items()
        }
        for table, rows in data.extras.items()
        if rows
    }
    diagnostics["labels"] = {
        table: {".".join(map(str, index)): label for index, label in labels.items()}
        for table, labels in data.labels.items()
        if labels
    }
    diagnostics["raw_walk"] = dict(sorted(data.raw.items()))
    return diagnostics
