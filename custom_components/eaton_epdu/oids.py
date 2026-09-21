"""OID map for the EATON-EPDU-MIB (ePDU G3 / "Marlin" family).

Everything the integration knows about the hardware lives in this file. The
coordinator does *not* GET individual OIDs: it walks the whole
``1.3.6.1.4.1.534.6.6.7`` subtree once per poll and classifies every returned
OID against the tables below. Consequences worth knowing:

* Everything the PDU exposes is fetched, mapped or not. Unmapped columns are
  always in the diagnostics download and can be turned into ``*_col<N>``
  sensors with the "expose unmapped columns" option.
* A wrong column number here can only cost a nice name or unit -- it can never
  stop data from being read.
* Daisy-chained units need no configuration. Every Eaton table is indexed by
  ``unitIndex`` first, so an added unit simply appears as new index tuples and
  the integration creates a new Home Assistant device for it.

Index note: a stand-alone G3 is unit ``0``; on a daisy chain the host stays
``0`` and downstream units are ``1..N``. Indices are read off the wire, never
assumed.

Every column below was checked against the published EATON-EPDU-MIB
(revision 202303311500Z) and against a live pair of EMAT08-10 units running
firmware 06.00.0003. ``mib`` records which MIB object a column is, so any
reading can be traced back to its definition. See ``docs/OID_MAP.md``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactivePower,
    UnitOfTime,
)

BASE_OID = "1.3.6.1.4.1.534.6.6.7"

#: Standard MIB-II scalars: connectivity check and naming fallback.
SYS_OIDS: dict[str, str] = {
    "sys_descr": "1.3.6.1.2.1.1.1.0",
    "sys_object_id": "1.3.6.1.2.1.1.2.0",
    "sys_uptime": "1.3.6.1.2.1.1.3.0",
    "sys_contact": "1.3.6.1.2.1.1.4.0",
    "sys_name": "1.3.6.1.2.1.1.5.0",
    "sys_location": "1.3.6.1.2.1.1.6.0",
}

#: unitsPresent: comma separated list of units on the chain, e.g. "0,1".
OID_UNITS_PRESENT = f"{BASE_OID}.1.1.0"

# --- enumerations (from the MIB) ---------------------------------------------
# Unknown values render as "unknown (<raw>)" rather than being dropped.
OUTLET_STATUS: Mapping[int, str] = {
    0: "off",
    1: "on",
    2: "pending_off",
    3: "pending_on",
}
GROUP_CONTROL_STATUS: Mapping[int, str] = {
    0: "off",
    1: "on",
    2: "rebooting",
    3: "mixed",
}
SWITCHABLE: Mapping[int, str] = {1: "switchable", 2: "not_switchable"}
POWER_ON_STATE: Mapping[int, str] = {0: "off", 1: "on", 2: "last_state"}
AUTOMATIC_SHUTOFF: Mapping[int, str] = {
    0: "not_applicable",
    1: "keep_the_current_position",
    2: "shutoff_the_outlets",
}
THRESHOLD_STATUS: Mapping[int, str] = {
    0: "good",
    1: "low_warning",
    2: "low_critical",
    3: "high_warning",
    4: "high_critical",
}
FREQUENCY_STATUS: Mapping[int, str] = {0: "good", 1: "out_of_range"}
PROBE_STATUS: Mapping[int, str] = {-1: "bad", 0: "disconnected", 1: "connected"}
#: A probe is only trusted when its status column is one of these.
PROBE_OK_STATES: tuple[int, ...] = (1,)
CONTACT_STATE: Mapping[int, str] = {-1: "bad", 0: "open", 1: "closed"}
CONTACT_ON_STATES: tuple[int, ...] = (1,)
INPUT_TYPE: Mapping[int, str] = {
    1: "single_phase",
    2: "split_phase",
    3: "three_phase_delta",
    4: "three_phase_wye",
}
INPUT_VOLTAGE_MEAS_TYPE: Mapping[int, str] = {
    1: "single_phase",
    2: "phase1_to_n",
    3: "phase2_to_n",
    4: "phase3_to_n",
    5: "phase1_to_2",
    6: "phase2_to_3",
    7: "phase3_to_1",
}
INPUT_CURRENT_MEAS_TYPE: Mapping[int, str] = {
    1: "single_phase",
    2: "neutral",
    3: "phase1",
    4: "phase2",
    5: "phase3",
}
INPUT_POWER_MEAS_TYPE: Mapping[int, str] = {
    0: "unknown",
    1: "phase1",
    2: "phase2",
    3: "phase3",
    4: "total",
}
GROUP_VOLTAGE_MEAS_TYPE: Mapping[int, str] = {0: "unknown", **INPUT_VOLTAGE_MEAS_TYPE}
GROUP_TYPE: Mapping[int, str] = {
    0: "unknown",
    1: "breaker_1_pole",
    2: "breaker_2_pole",
    3: "breaker_3_pole",
    4: "outlet_section",
    5: "user_defined",
}
BREAKER_STATUS: Mapping[int, str] = {
    0: "not_applicable",
    1: "breaker_on",
    2: "breaker_off",
}
UNIT_TYPE: Mapping[int, str] = {
    0: "unknown",
    1: "switched",
    2: "advanced_monitored",
    3: "managed",
    4: "monitored",
    5: "basic",
    6: "inline_monitored",
}
SYSTEM_TYPE: Mapping[int, str] = {0: "unknown", 1: "g3_epdu", 2: "g3_hd_epdu"}
LCD_CONTROL: Mapping[int, str] = {
    0: "not_applicable",
    1: "lcd_screen_off",
    2: "lcd_key_lock",
    3: "lcd_screen_off_and_key_lock",
}
TEMPERATURE_SCALE: Mapping[int, str] = {0: "celsius", 1: "fahrenheit"}
COMMUNICATION_STATUS: Mapping[int, str] = {0: "good", 1: "communication_lost"}
INTERNAL_STATUS: Mapping[int, str] = {0: "good", 1: "internal_failure"}
OUTLET_PHASE_ID: Mapping[int, str] = {
    1: "single_phase",
    2: "phase1_to_n",
    3: "phase2_to_n",
    4: "phase3_to_n",
    5: "phase1_to_2",
    6: "phase2_to_3",
    7: "phase3_to_1",
    8: "phase12n",
    9: "phase23n",
    10: "phase31n",
    11: "phase123",
    12: "phase123n",
}
#: Receptacle/plug types keep their MIB spelling -- "nema515" reads better than
#: any snake_case mangling of it.
# fmt: off
OUTLET_RECEPTACLE_TYPE: Mapping[int, str] = {
    0: "unknown", 1: "iecC13", 2: "iecC19", 3: "comboC39", 10: "uk", 11: "french",
    12: "schuko", 20: "nema515", 21: "nema51520", 22: "nema520", 23: "nemaL520",
    24: "nemaL530", 25: "nema615", 26: "nema620", 27: "nemaL620", 28: "nemaL630",
    29: "nemaL715", 30: "rf203p277", 31: "sdg300", 32: "sdg400",
}
INPUT_PLUG_TYPE: Mapping[int, str] = {
    100: "other1Phase", 101: "iecC14Inlet", 102: "iecC20Inlet", 103: "iec316P6",
    104: "iec332P6", 105: "iec363P6", 106: "iecC14Plug", 107: "iecC20Plug",
    120: "nema515", 121: "nemaL515", 122: "nema520", 123: "nemaL520", 124: "nema615",
    125: "nemaL615", 126: "nemaL530", 127: "nema620", 128: "nemaL620",
    129: "nemaL630", 130: "cs8265", 131: "nemaL2530", 140: "other208V2P3W",
    141: "other230V1P3W", 150: "french", 151: "schuko", 152: "uk",
    160: "field208V2P3W", 161: "field230V1P3W", 200: "other2Phase",
    201: "nemaL1420", 202: "nemaL1430", 300: "other3Phase", 301: "iec516P6",
    302: "iec460P9", 303: "iec560P9", 304: "iec532P6", 306: "iec563P6",
    307: "iec4100P9", 320: "nemaL1520", 321: "nemaL2120", 322: "nemaL1530",
    323: "nemaL2130", 324: "cs8365", 325: "nemaL2220", 326: "nemaL2230",
    327: "nemaL2630", 340: "other208V3P4W", 341: "other208V3P5W",
    342: "other400V3P5W", 343: "other480V3P5W", 350: "bladeUps208V",
    351: "bladeUps400V", 360: "field208V3P4W", 361: "field400V3P5W",
    400: "universalUTP8pin",
}
# fmt: on

#: Eaton uses -1 for a disabled threshold, an absent measurement and an idle
#: command column.
NA_MINUS_ONE: tuple[int, ...] = (-1,)


@dataclass(frozen=True, kw_only=True)
class Column:
    """One column of an Eaton table."""

    key: str
    name: str
    column: int
    #: the EATON-EPDU-MIB object this column is
    mib: str = ""
    #: sensor | binary_sensor | none
    platform: str = "sensor"
    unit: str | None = None
    scale: float = 1.0
    precision: int | None = None
    device_class: str | None = None
    state_class: str | None = None
    enum: Mapping[int, str] | None = None
    on_states: tuple[int, ...] | None = None
    entity_category: str | None = None
    enabled_default: bool = True
    icon: str | None = None
    #: raw values that mean "not available"
    na_values: tuple[int, ...] = ()
    #: raw values at or below this mean "not available" (probe sentinels)
    na_below: float | None = None
    #: "epoch" (UnixTimeStamp) or "dateandtime" (SNMPv2-TC DateAndTime)
    transform: str | None = None
    #: unit is whatever scale the PDU reports temperatures in
    temperature: bool = False
    #: writable Wh counter: writing 0 resets it and its timer
    resettable: bool = False
    #: ASN.1 type an SNMP SET must use for this column. Eaton's command
    #: columns are Integer32 but the Wh counters are Unsigned32, and agents
    #: reject the wrong one with "wrongType".
    write_syntax: str = "Integer32"
    #: used for device info / row labels only, never becomes an entity
    info_only: bool = False


@dataclass(frozen=True)
class IndexPart:
    """One component of a table index."""

    name: str
    #: keep in the label even when the device only has one of them
    always: bool = False


@dataclass(frozen=True, kw_only=True)
class Table:
    """An Eaton SNMP table."""

    key: str
    #: noun used when the compacted index leaves no label at all
    singular: str
    #: OID of the table *entry* (the table OID with ".1" appended)
    oid: str
    index: tuple[IndexPart, ...]
    columns: tuple[Column, ...]
    #: column key holding the label the PDU itself shows for the row
    label_column: str | None = None
    #: column key holding the physical position (an outlet's "A1"). When set,
    #: the position leads the label and a user-set name follows in brackets.
    position_column: str | None = None
    #: table whose row label this table inherits (its index is a prefix of ours)
    parent: str | None = None
    #: False when the row label duplicates the Home Assistant device name
    use_label_for_entities: bool = True
    _by_number: dict[int, Column] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        """Index the columns by their SNMP column number."""
        object.__setattr__(self, "_by_number", {c.column: c for c in self.columns})

    def column_for(self, number: int) -> Column | None:
        """Return the column definition for an SNMP column number."""
        return self._by_number.get(number)

    def column_by_key(self, key: str) -> Column | None:
        """Return the column definition for an integration key."""
        return next((c for c in self.columns if c.key == key), None)


# --- column shorthands -------------------------------------------------------
def _volts(column: int, mib: str, name: str = "Voltage", key: str = "voltage") -> Column:
    """Eaton reports millivolts."""
    return Column(
        key=key,
        name=name,
        column=column,
        mib=mib,
        unit=UnitOfElectricPotential.VOLT,
        scale=0.001,
        precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        na_values=NA_MINUS_ONE,
    )


def _amps(column: int, mib: str, name: str = "Current", key: str = "current") -> Column:
    """Eaton reports milliamps."""
    return Column(
        key=key,
        name=name,
        column=column,
        mib=mib,
        unit=UnitOfElectricCurrent.AMPERE,
        scale=0.001,
        precision=2,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        na_values=NA_MINUS_ONE,
    )


def _watts(column: int, mib: str, name: str = "Power", key: str = "power") -> Column:
    return Column(
        key=key,
        name=name,
        column=column,
        mib=mib,
        unit=UnitOfPower.WATT,
        precision=1,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        na_values=NA_MINUS_ONE,
    )


def _va(column: int, mib: str, name: str = "Apparent power", key: str = "apparent_power") -> Column:
    return Column(
        key=key,
        name=name,
        column=column,
        mib=mib,
        unit=UnitOfApparentPower.VOLT_AMPERE,
        precision=1,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        na_values=NA_MINUS_ONE,
    )


def _var(
    column: int,
    mib: str,
    name: str = "Reactive power",
    key: str = "reactive_power",
) -> Column:
    return Column(
        key=key,
        name=name,
        column=column,
        mib=mib,
        unit=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        precision=1,
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
    )


def _wh(column: int, mib: str, name: str = "Energy Total", key: str = "energy") -> Column:
    """Build a Wh counter column.

    These are read-write: writing 0 resets the counter and its timer.
    """
    return Column(
        key=key,
        name=name,
        column=column,
        mib=mib,
        unit=UnitOfEnergy.WATT_HOUR,
        precision=0,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        resettable=True,
        # Eaton declares the Wh counters Unsigned32; sending Integer32 gets a
        # "wrongType" refusal from the agent.
        write_syntax="Unsigned32",
    )


def _wh_timer(
    column: int,
    mib: str,
    name: str = "Energy counter start",
    key: str = "energy_reset_time",
) -> Column:
    return Column(
        key=key,
        name=name,
        column=column,
        mib=mib,
        transform="epoch",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
    )


def _power_factor(
    column: int,
    mib: str,
    name: str = "Power factor",
    key: str = "power_factor",
) -> Column:
    """Build a power-factor column, reported in 1/1000; negative means leading."""
    return Column(
        key=key,
        name=name,
        column=column,
        mib=mib,
        unit=PERCENTAGE,
        scale=0.1,
        precision=1,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
    )


def _percent_load(column: int, mib: str, enabled: bool = True) -> Column:
    return Column(
        key="percent_load",
        name="Load",
        column=column,
        mib=mib,
        unit=PERCENTAGE,
        precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        na_values=NA_MINUS_ONE,
        enabled_default=enabled,
    )


def _crest_factor(column: int, mib: str) -> Column:
    return Column(
        key="crest_factor",
        name="Crest factor",
        column=column,
        mib=mib,
        scale=0.001,
        precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
        na_values=NA_MINUS_ONE,
    )


def _th_status(
    column: int,
    mib: str,
    key: str = "threshold_status",
    name: str = "Threshold status",
) -> Column:
    return Column(
        key=key,
        name=name,
        column=column,
        mib=mib,
        enum=THRESHOLD_STATUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:alert-outline",
    )


def _limits(
    key_prefix: str,
    name_prefix: str,
    first: int,
    mib_prefix: str,
    unit: str | None,
    scale: float = 1.0,
    temperature: bool = False,
) -> tuple[Column, ...]:
    """Build the four configured threshold limits, in MIB order from `first`."""
    parts = (
        ("low_warning", "low warning", "ThLowerWarning"),
        ("low_critical", "low critical", "ThLowerCritical"),
        ("high_warning", "high warning", "ThUpperWarning"),
        ("high_critical", "high critical", "ThUpperCritical"),
    )
    return tuple(
        Column(
            key=f"{key_prefix}{key}",
            name=f"{name_prefix}{label}".strip().capitalize(),
            column=first + offset,
            mib=f"{mib_prefix}{suffix}",
            unit=unit,
            scale=scale,
            precision=2,
            temperature=temperature,
            entity_category=EntityCategory.DIAGNOSTIC,
            enabled_default=False,
            na_values=NA_MINUS_ONE,
        )
        for offset, (key, label, suffix) in enumerate(parts)
    )


def _info(key: str, name: str, column: int, mib: str) -> Column:
    return Column(key=key, name=name, column=column, mib=mib, info_only=True)


def _diag(
    key: str,
    name: str,
    column: int,
    mib: str,
    enum: Mapping[int, str] | None = None,
    unit: str | None = None,
    enabled: bool = False,
    **kwargs: object,
) -> Column:
    return Column(
        key=key,
        name=name,
        column=column,
        mib=mib,
        enum=enum,
        unit=unit,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=enabled,
        **kwargs,  # type: ignore[arg-type]
    )


def _cmd(key: str, name: str, column: int, mib: str) -> Column:
    """Build a command column: never an entity, used by switch/button."""
    return Column(key=key, name=name, column=column, mib=mib, platform="none")


UNIT = IndexPart("Unit")
AMP = UnitOfElectricCurrent.AMPERE
VOLT = UnitOfElectricPotential.VOLT

# =============================================================================
# units -- .1
# =============================================================================
UNIT_TABLE = Table(
    key="unit",
    singular="Unit",
    oid=f"{BASE_OID}.1.2.1",
    index=(UNIT,),
    columns=(
        _info("product_name", "Product", 2, "productName"),
        _info("part_number", "Part number", 3, "partNumber"),
        _info("serial_number", "Serial number", 4, "serialNumber"),
        _info("firmware_version", "Firmware", 5, "firmwareVersion"),
        _info("name", "Name", 6, "unitName"),
        _diag("lcd_control", "LCD control", 7, "lcdControl", enum=LCD_CONTROL),
        _diag(
            "device_time",
            "Device time",
            8,
            "clockValue",
            transform="dateandtime",
            device_class=SensorDeviceClass.TIMESTAMP,
            enabled=True,
        ),
        _diag(
            "temperature_scale",
            "Temperature scale",
            9,
            "temperatureScale",
            enum=TEMPERATURE_SCALE,
        ),
        _diag("unit_type", "Unit type", 10, "unitType", enum=UNIT_TYPE),
        _diag("system_type", "System type", 11, "systemType", enum=SYSTEM_TYPE),
        _diag("input_count", "Input count", 20, "inputCount"),
        _diag("group_count", "Group count", 21, "groupCount"),
        _diag("outlet_count", "Outlet count", 22, "outletCount"),
        _diag("temperature_count", "Temperature probe count", 23, "temperatureCount"),
        _diag("humidity_count", "Humidity probe count", 24, "humidityCount"),
        _diag("contact_count", "Contact count", 25, "contactCount"),
        # Chain health: worth having on by default once units are daisy-chained.
        _diag(
            "communication_status",
            "Communication status",
            30,
            "communicationStatus",
            enum=COMMUNICATION_STATUS,
            enabled=True,
            icon="mdi:lan-connect",
        ),
        _diag(
            "internal_status",
            "Internal status",
            31,
            "internalStatus",
            enum=INTERNAL_STATUS,
            enabled=True,
            icon="mdi:chip",
        ),
        _diag(
            "strapping_status",
            "Strapping status",
            32,
            "strappingStatus",
            enum=COMMUNICATION_STATUS,
            enabled=True,
            icon="mdi:link-variant",
        ),
    ),
    label_column="name",
    use_label_for_entities=False,
)

# unitControlTable (.1.3.1: unitControlOffCmd/OnCmd) is deliberately not mapped:
# writing to it powers down a whole PDU.

# =============================================================================
# inputs -- .3
# =============================================================================
INPUT_TABLE = Table(
    key="input",
    singular="Input",
    oid=f"{BASE_OID}.3.1.1",
    index=(UNIT, IndexPart("Input")),
    columns=(
        _diag("input_type", "Input type", 2, "inputType", enum=INPUT_TYPE),
        Column(
            key="frequency",
            name="Frequency",
            column=3,
            mib="inputFrequency",
            unit=UnitOfFrequency.HERTZ,
            scale=0.1,
            precision=1,
            device_class=SensorDeviceClass.FREQUENCY,
            state_class=SensorStateClass.MEASUREMENT,
            na_values=NA_MINUS_ONE,
        ),
        Column(
            key="frequency_status",
            name="Frequency status",
            column=4,
            mib="inputFrequencyStatus",
            enum=FREQUENCY_STATUS,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:alert-outline",
        ),
        _diag("voltage_count", "Voltage measurement count", 5, "inputVoltageCount"),
        _diag("current_count", "Current measurement count", 6, "inputCurrentCount"),
        _diag("power_count", "Power measurement count", 7, "inputPowerCount"),
        _diag("plug_type", "Plug type", 8, "inputPlugType", enum=INPUT_PLUG_TYPE),
        _diag("feed_color", "Feed colour", 9, "inputFeedColor"),
        _info("name", "Name", 10, "inputFeedName"),
    ),
    label_column="name",
)

INPUT_VOLTAGE_TABLE = Table(
    key="input_voltage",
    singular="Input",
    oid=f"{BASE_OID}.3.2.1",
    index=(UNIT, IndexPart("Input"), IndexPart("Phase")),
    parent="input",
    columns=(
        _diag(
            "measurement_type",
            "Voltage measurement type",
            2,
            "inputVoltageMeasType",
            enum=INPUT_VOLTAGE_MEAS_TYPE,
        ),
        _volts(3, "inputVoltage"),
        _th_status(
            4,
            "inputVoltageThStatus",
            key="voltage_threshold_status",
            name="Voltage threshold status",
        ),
        *_limits("voltage_", "Voltage ", 5, "inputVoltage", VOLT, 0.001),
    ),
)

INPUT_CURRENT_TABLE = Table(
    key="input_current",
    singular="Input",
    oid=f"{BASE_OID}.3.3.1",
    index=(UNIT, IndexPart("Input"), IndexPart("Phase")),
    parent="input",
    columns=(
        _diag(
            "measurement_type",
            "Current measurement type",
            2,
            "inputCurrentMeasType",
            enum=INPUT_CURRENT_MEAS_TYPE,
        ),
        _diag(
            "current_capacity",
            "Current capacity",
            3,
            "inputCurrentCapacity",
            unit=AMP,
            scale=0.001,
            precision=2,
        ),
        _amps(4, "inputCurrent"),
        _th_status(
            5,
            "inputCurrentThStatus",
            key="current_threshold_status",
            name="Current threshold status",
        ),
        *_limits("current_", "Current ", 6, "inputCurrent", AMP, 0.001),
        _crest_factor(10, "inputCurrentCrestFactor"),
        _percent_load(11, "inputCurrentPercentLoad"),
        _info("name", "Name", 12, "inputPhaseDesignator"),
    ),
)

INPUT_POWER_TABLE = Table(
    key="input_power",
    singular="Input",
    oid=f"{BASE_OID}.3.4.1",
    index=(UNIT, IndexPart("Input"), IndexPart("Phase")),
    parent="input",
    columns=(
        _diag(
            "measurement_type",
            "Power measurement type",
            2,
            "inputPowerMeasType",
            enum=INPUT_POWER_MEAS_TYPE,
        ),
        _va(3, "inputVA"),
        _watts(4, "inputWatts"),
        _wh(5, "inputWh"),
        _wh_timer(6, "inputWhTimer"),
        _power_factor(7, "inputPowerFactor"),
        _var(8, "inputVAR"),
    ),
)

#: Per-input totals, with their own resettable counter.
INPUT_TOTAL_TABLE = Table(
    key="input_total",
    singular="Input",
    oid=f"{BASE_OID}.3.5.1",
    index=(UNIT, IndexPart("Input")),
    parent="input",
    columns=(
        _va(3, "inputTotalVA", key="total_apparent_power"),
        _watts(4, "inputTotalWatts", key="total_power"),
        _wh(5, "inputTotalWh", name="Energy Total", key="total_energy"),
        _wh_timer(
            6,
            "inputTotalWhTimer",
            name="Energy Total counter start",
            key="total_energy_reset_time",
        ),
        _power_factor(
            7,
            "inputTotalPowerFactor",
            name="Power factor",
            key="total_power_factor",
        ),
        _var(
            8,
            "inputTotalVAR",
            name="Reactive power",
            key="total_reactive_power",
        ),
        _diag(
            "power_capacity",
            "Power capacity",
            9,
            "inputPowerCapacity",
            unit=UnitOfApparentPower.VOLT_AMPERE,
        ),
    ),
)

# =============================================================================
# groups (sections / breakers) -- .5
# =============================================================================
GROUP_TABLE = Table(
    key="group",
    singular="Group",
    oid=f"{BASE_OID}.5.1.1",
    index=(UNIT, IndexPart("Group", always=True)),
    columns=(
        _diag("group_id", "Group ID", 2, "groupID"),
        _info("name", "Name", 3, "groupName"),
        _diag("group_type", "Group type", 4, "groupType", enum=GROUP_TYPE),
        _diag(
            "breaker_status",
            "Breaker status",
            5,
            "groupBreakerStatus",
            enum=BREAKER_STATUS,
            icon="mdi:fuse",
        ),
        _diag("child_count", "Outlet count", 6, "groupChildCount"),
        _diag("color", "Colour", 7, "groupColor"),
        _diag("designator", "Designator", 8, "groupDesignator"),
        _diag("input_index", "Input index", 9, "groupInputIndex"),
    ),
    label_column="name",
)

GROUP_VOLTAGE_TABLE = Table(
    key="group_voltage",
    singular="Group",
    oid=f"{BASE_OID}.5.3.1",
    index=(UNIT, IndexPart("Group", always=True)),
    parent="group",
    columns=(
        _diag(
            "measurement_type",
            "Voltage measurement type",
            2,
            "groupVoltageMeasType",
            enum=GROUP_VOLTAGE_MEAS_TYPE,
        ),
        _volts(3, "groupVoltage"),
        _th_status(
            4,
            "groupVoltageThStatus",
            key="voltage_threshold_status",
            name="Voltage threshold status",
        ),
        *_limits("voltage_", "Voltage ", 5, "groupVoltage", VOLT, 0.001),
    ),
)

GROUP_CURRENT_TABLE = Table(
    key="group_current",
    singular="Group",
    oid=f"{BASE_OID}.5.4.1",
    index=(UNIT, IndexPart("Group", always=True)),
    parent="group",
    columns=(
        _diag(
            "current_capacity",
            "Current capacity",
            2,
            "groupCurrentCapacity",
            unit=AMP,
            scale=0.001,
            precision=2,
        ),
        _amps(3, "groupCurrent"),
        _th_status(
            4,
            "groupCurrentThStatus",
            key="current_threshold_status",
            name="Current threshold status",
        ),
        *_limits("current_", "Current ", 5, "groupCurrent", AMP, 0.001),
        _crest_factor(9, "groupCurrentCrestFactor"),
        _percent_load(10, "groupCurrentPercentLoad"),
    ),
)

GROUP_POWER_TABLE = Table(
    key="group_power",
    singular="Group",
    oid=f"{BASE_OID}.5.5.1",
    index=(UNIT, IndexPart("Group", always=True)),
    parent="group",
    columns=(
        _va(2, "groupVA"),
        _watts(3, "groupWatts"),
        _wh(4, "groupWh"),
        _wh_timer(5, "groupWhTimer"),
        _power_factor(6, "groupPowerFactor"),
        _var(7, "groupVAR"),
    ),
)

GROUP_CONTROL_TABLE = Table(
    key="group_control",
    singular="Group",
    oid=f"{BASE_OID}.5.6.1",
    index=(UNIT, IndexPart("Group", always=True)),
    parent="group",
    columns=(
        Column(
            key="status",
            name="Status",
            column=2,
            mib="groupControlStatus",
            enum=GROUP_CONTROL_STATUS,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:power-plug",
        ),
        _cmd("off_cmd", "Off command", 3, "groupControlOffCmd"),
        _cmd("on_cmd", "On command", 4, "groupControlOnCmd"),
        _cmd("reboot_cmd", "Reboot command", 5, "groupControlRebootCmd"),
    ),
)

# =============================================================================
# outlets -- .6
# =============================================================================
OUTLET_TABLE = Table(
    key="outlet",
    singular="Outlet",
    oid=f"{BASE_OID}.6.1.1",
    index=(UNIT, IndexPart("Outlet", always=True)),
    columns=(
        _diag("outlet_id", "Outlet ID", 2, "outletID"),
        _info("name", "Name", 3, "outletName"),
        _diag("parent_count", "Parent count", 4, "outletParentCount"),
        _diag(
            "outlet_type",
            "Receptacle type",
            5,
            "outletType",
            enum=OUTLET_RECEPTACLE_TYPE,
        ),
        _diag("designator", "Designator", 6, "outletDesignator"),
        _diag("phase_id", "Phase", 7, "outletPhaseID", enum=OUTLET_PHASE_ID),
    ),
    label_column="name",
    position_column="designator",
)

OUTLET_VOLTAGE_TABLE = Table(
    key="outlet_voltage",
    singular="Outlet",
    oid=f"{BASE_OID}.6.3.1",
    index=(UNIT, IndexPart("Outlet", always=True)),
    parent="outlet",
    columns=(
        _volts(2, "outletVoltage"),
        _th_status(
            3,
            "outletVoltageThStatus",
            key="voltage_threshold_status",
            name="Voltage threshold status",
        ),
        *_limits("voltage_", "Voltage ", 4, "outletVoltage", VOLT, 0.001),
    ),
)

OUTLET_CURRENT_TABLE = Table(
    key="outlet_current",
    singular="Outlet",
    oid=f"{BASE_OID}.6.4.1",
    index=(UNIT, IndexPart("Outlet", always=True)),
    parent="outlet",
    columns=(
        _diag(
            "current_capacity",
            "Current capacity",
            2,
            "outletCurrentCapacity",
            unit=AMP,
            scale=0.001,
            precision=2,
        ),
        _amps(3, "outletCurrent"),
        _th_status(
            4,
            "outletCurrentThStatus",
            key="current_threshold_status",
            name="Current threshold status",
        ),
        *_limits("current_", "Current ", 5, "outletCurrent", AMP, 0.001),
        _crest_factor(9, "outletCurrentCrestFactor"),
        _percent_load(10, "outletCurrentPercentLoad", enabled=False),
    ),
)

OUTLET_POWER_TABLE = Table(
    key="outlet_power",
    singular="Outlet",
    oid=f"{BASE_OID}.6.5.1",
    index=(UNIT, IndexPart("Outlet", always=True)),
    parent="outlet",
    columns=(
        _va(2, "outletVA"),
        _watts(3, "outletWatts"),
        _wh(4, "outletWh"),
        _wh_timer(5, "outletWhTimer"),
        _power_factor(6, "outletPowerFactor"),
        _var(7, "outletVAR"),
    ),
)

OUTLET_CONTROL_TABLE = Table(
    key="outlet_control",
    singular="Outlet",
    oid=f"{BASE_OID}.6.6.1",
    index=(UNIT, IndexPart("Outlet", always=True)),
    parent="outlet",
    columns=(
        Column(
            key="status",
            name="Status",
            column=2,
            mib="outletControlStatus",
            enum=OUTLET_STATUS,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:power-socket-us",
        ),
        _cmd("off_cmd", "Off command", 3, "outletControlOffCmd"),
        _cmd("on_cmd", "On command", 4, "outletControlOnCmd"),
        _cmd("reboot_cmd", "Reboot command", 5, "outletControlRebootCmd"),
        _diag(
            "power_on_state",
            "Power-on state",
            6,
            "outletControlPowerOnState",
            enum=POWER_ON_STATE,
        ),
        _diag(
            "sequence_delay",
            "Sequence delay",
            7,
            "outletControlSequenceDelay",
            unit=UnitOfTime.SECONDS,
        ),
        _diag(
            "reboot_off_time",
            "Reboot off time",
            8,
            "outletControlRebootOffTime",
            unit=UnitOfTime.SECONDS,
        ),
        _diag(
            "switchable",
            "Switchable",
            9,
            "outletControlSwitchable",
            enum=SWITCHABLE,
        ),
        _diag(
            "shutoff_delay",
            "Shutoff delay",
            10,
            "outletControlShutoffDelay",
            unit=UnitOfTime.SECONDS,
        ),
    ),
)

OUTLET_SHUTOFF_TABLE = Table(
    key="outlet_shutoff",
    singular="Outlets",
    oid=f"{BASE_OID}.6.7.1",
    index=(UNIT,),
    use_label_for_entities=False,
    columns=(
        _diag(
            "automatic_shutoff",
            "Automatic shutoff",
            2,
            "outletAutomaticShutoff",
            enum=AUTOMATIC_SHUTOFF,
        ),
    ),
)

# =============================================================================
# environment -- .7
# Temperatures are in tenths of the scale the unit is set to (unitTable column
# 9, temperatureScale). A probe that is not connected reports absolute zero in
# that scale: -4595 (-459.5 degF) or -2731 (-273.1 degC).
# =============================================================================
TEMPERATURE_TABLE = Table(
    key="temperature",
    singular="",
    oid=f"{BASE_OID}.7.1.1",
    index=(UNIT, IndexPart("Probe")),
    columns=(
        _info("name", "Name", 2, "temperatureName"),
        Column(
            key="probe_status",
            name="Temperature probe status",
            column=3,
            mib="temperatureProbeStatus",
            enum=PROBE_STATUS,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        Column(
            key="value",
            name="Temperature",
            column=4,
            mib="temperatureValue",
            scale=0.1,
            precision=1,
            temperature=True,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            na_below=-2000,
        ),
        _th_status(5, "temperatureThStatus", name="Temperature threshold status"),
        *_limits("", "Temperature ", 6, "temperature", None, 0.1, temperature=True),
    ),
    label_column="name",
)

HUMIDITY_TABLE = Table(
    key="humidity",
    singular="",
    oid=f"{BASE_OID}.7.2.1",
    index=(UNIT, IndexPart("Probe")),
    columns=(
        _info("name", "Name", 2, "humidityName"),
        Column(
            key="probe_status",
            name="Humidity probe status",
            column=3,
            mib="humidityProbeStatus",
            enum=PROBE_STATUS,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        Column(
            key="value",
            name="Humidity",
            column=4,
            mib="humidityValue",
            unit=PERCENTAGE,
            scale=0.1,
            precision=1,
            device_class=SensorDeviceClass.HUMIDITY,
            state_class=SensorStateClass.MEASUREMENT,
            na_values=NA_MINUS_ONE,
        ),
        _th_status(5, "humidityThStatus", name="Humidity threshold status"),
        *_limits("", "Humidity ", 6, "humidity", PERCENTAGE, 0.1),
    ),
    label_column="name",
)

CONTACT_TABLE = Table(
    key="contact",
    singular="Contact",
    oid=f"{BASE_OID}.7.3.1",
    index=(UNIT, IndexPart("Contact")),
    columns=(
        _info("name", "Name", 2, "contactName"),
        Column(
            key="probe_status",
            name="Status",
            column=3,
            mib="contactProbeStatus",
            enum=PROBE_STATUS,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        Column(
            key="state",
            name="Contact",
            column=4,
            mib="contactState",
            platform="binary_sensor",
            enum=CONTACT_STATE,
            on_states=CONTACT_ON_STATES,
            na_values=NA_MINUS_ONE,
        ),
    ),
    label_column="name",
)

#: Tables the per-unit environment summary is built from, with the unitTable
#: column that says how many of them the unit should have.
ENVIRONMENT_TABLES: tuple[tuple[str, str], ...] = (
    ("temperature", "temperature_count"),
    ("humidity", "humidity_count"),
    ("contact", "contact_count"),
)

TABLES: tuple[Table, ...] = (
    UNIT_TABLE,
    INPUT_TABLE,
    INPUT_VOLTAGE_TABLE,
    INPUT_CURRENT_TABLE,
    INPUT_POWER_TABLE,
    INPUT_TOTAL_TABLE,
    GROUP_TABLE,
    GROUP_VOLTAGE_TABLE,
    GROUP_CURRENT_TABLE,
    GROUP_POWER_TABLE,
    GROUP_CONTROL_TABLE,
    OUTLET_TABLE,
    OUTLET_VOLTAGE_TABLE,
    OUTLET_CURRENT_TABLE,
    OUTLET_POWER_TABLE,
    OUTLET_CONTROL_TABLE,
    OUTLET_SHUTOFF_TABLE,
    TEMPERATURE_TABLE,
    HUMIDITY_TABLE,
    CONTACT_TABLE,
)

TABLES_BY_KEY: dict[str, Table] = {table.key: table for table in TABLES}

#: Longest prefix first so overlapping OIDs can never be misfiled.
TABLES_BY_PREFIX: tuple[tuple[str, Table], ...] = tuple(
    sorted(((f"{t.oid}.", t) for t in TABLES), key=lambda item: -len(item[0]))
)

#: Every resettable Wh counter, as (table, column).
RESETTABLE: tuple[tuple[Table, Column], ...] = tuple(
    (table, column) for table in TABLES for column in table.columns if column.resettable
)
