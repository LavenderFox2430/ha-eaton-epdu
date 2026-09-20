"""Constants for the Eaton ePDU G3 integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "eaton_epdu"
MANUFACTURER: Final = "Eaton"

# Value shown for anything the PDU cannot report (missing module, probe not
# connected, unsupported table on this model, ...).
NOT_AVAILABLE: Final = "N/A"

# --- Config entry keys -------------------------------------------------------
CONF_SNMP_VERSION: Final = "snmp_version"
CONF_COMMUNITY: Final = "community"
CONF_WRITE_COMMUNITY: Final = "write_community"
CONF_AUTH_PROTOCOL: Final = "auth_protocol"
CONF_AUTH_KEY: Final = "auth_key"
CONF_PRIV_PROTOCOL: Final = "priv_protocol"
CONF_PRIV_KEY: Final = "priv_key"

# --- Option keys -------------------------------------------------------------
CONF_TIMEOUT: Final = "timeout"
CONF_RETRIES: Final = "retries"
CONF_MAX_REPETITIONS: Final = "max_repetitions"
CONF_EXPOSE_UNMAPPED: Final = "expose_unmapped"
CONF_COMMAND_DELAY: Final = "command_delay"
CONF_TEMPERATURE_UNIT: Final = "temperature_unit"
#: Auto-detected scale, remembered so it stays stable once every probe is
#: connected and the absolute-zero sentinel is no longer visible.
CONF_DETECTED_TEMPERATURE_UNIT: Final = "detected_temperature_unit"

TEMPERATURE_UNIT_AUTO: Final = "auto"
TEMPERATURE_UNIT_CELSIUS: Final = "celsius"
TEMPERATURE_UNIT_FAHRENHEIT: Final = "fahrenheit"
TEMPERATURE_UNIT_CHOICES: Final = [
    TEMPERATURE_UNIT_AUTO,
    TEMPERATURE_UNIT_CELSIUS,
    TEMPERATURE_UNIT_FAHRENHEIT,
]

# --- SNMP versions -----------------------------------------------------------
VERSION_V1: Final = "v1"
VERSION_V2C: Final = "v2c"
VERSION_V3: Final = "v3"
SNMP_VERSIONS: Final = [VERSION_V1, VERSION_V2C, VERSION_V3]

AUTH_PROTOCOLS: Final = [
    "none",
    "md5",
    "sha",
    "sha224",
    "sha256",
    "sha384",
    "sha512",
]
PRIV_PROTOCOLS: Final = ["none", "des", "3des", "aes128", "aes192", "aes256"]

# --- Defaults ----------------------------------------------------------------
DEFAULT_PORT: Final = 161
DEFAULT_COMMUNITY: Final = "public"
# G3 firmware only speaks SNMPv1 and SNMPv3 out of the box; v1 is the safe
# default for an EMAT/EMAB/EMAH unit.
DEFAULT_SNMP_VERSION: Final = VERSION_V1
DEFAULT_SCAN_INTERVAL: Final = 30
DEFAULT_TIMEOUT: Final = 5
DEFAULT_RETRIES: Final = 2
DEFAULT_MAX_REPETITIONS: Final = 25
# Seconds to wait after writing an outlet command before re-reading state.
DEFAULT_COMMAND_DELAY: Final = 3.0

MIN_SCAN_INTERVAL: Final = 5

# --- Services ----------------------------------------------------------------
SERVICE_OUTLET_ON: Final = "outlet_on"
SERVICE_OUTLET_OFF: Final = "outlet_off"
SERVICE_OUTLET_CYCLE: Final = "outlet_cycle"
SERVICE_DUMP_OIDS: Final = "dump_oids"
ATTR_DELAY: Final = "delay"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
