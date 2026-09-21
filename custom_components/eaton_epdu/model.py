"""Turn a raw SNMP walk into the structure the entities are built from."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from homeassistant.const import UnitOfTemperature

from .const import NOT_AVAILABLE
from .oids import (
    BASE_OID,
    ENVIRONMENT_TABLES,
    OID_UNITS_PRESENT,
    PROBE_OK_STATES,
    TABLES,
    TABLES_BY_KEY,
    TABLES_BY_PREFIX,
    Column,
    Table,
)

#: A probe that is not connected reports absolute zero in the unit the PDU is
#: configured for: -459.5 degF or -273.1 degC, in tenths.
_SENTINEL_FAHRENHEIT = -4000
_SENTINEL_CELSIUS = -2000
#: Above this (in tenths) a live probe reading can only be Fahrenheit.
_LIVE_FAHRENHEIT_HINT = 600


@dataclass(frozen=True)
class UnitInfo:
    """One physical PDU on the daisy chain."""

    index: int
    name: str
    product_name: str | None = None
    part_number: str | None = None
    serial_number: str | None = None
    firmware_version: str | None = None
    is_host: bool = False


@dataclass
class EpduData:
    """Everything one poll produced."""

    #: table key -> full index tuple (unit first) -> column key -> value
    rows: dict[str, dict[tuple[int, ...], dict[str, Any]]] = field(default_factory=dict)
    #: table key -> index tuple -> SNMP column number -> value, for columns
    #: this integration does not map
    extras: dict[str, dict[tuple[int, ...], dict[int, Any]]] = field(default_factory=dict)
    #: table key -> index tuple -> display label
    labels: dict[str, dict[tuple[int, ...], str]] = field(default_factory=dict)
    units: dict[int, UnitInfo] = field(default_factory=dict)
    units_present: str | None = None
    #: unit index -> environment summary
    environment: dict[int, EnvironmentSummary] = field(default_factory=dict)
    sys: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    #: the host unit's temperature scale
    temperature_unit: str = UnitOfTemperature.CELSIUS
    #: unit index -> temperature scale; each unit has its own setting
    temperature_units: dict[int, str] = field(default_factory=dict)
    #: (table key, index) pairs that only restate another row, so they are
    #: read and kept in diagnostics but produce no entities
    redundant: set[tuple[str, tuple[int, ...]]] = field(default_factory=set)

    def is_redundant(self, table_key: str, index: tuple[int, ...]) -> bool:
        """Report whether a row duplicates one the integration already exposes."""
        return (table_key, index) in self.redundant

    def temperature_unit_for(self, unit_index: int) -> str:
        """Temperature scale of one unit."""
        return self.temperature_units.get(unit_index, self.temperature_unit)

    def value(self, table_key: str, index: tuple[int, ...], column_key: str) -> Any:
        """Return one raw value, or None if the row or column is absent."""
        return self.rows.get(table_key, {}).get(index, {}).get(column_key)

    def label(self, table_key: str, index: tuple[int, ...]) -> str:
        """Return the display label for a row."""
        return self.labels.get(table_key, {}).get(index, "")


@dataclass
class EnvironmentSummary:
    """State of the environmental module attached to one unit."""

    state: str
    attributes: dict[str, Any]


# --- parsing -----------------------------------------------------------------
def parse_walk(
    raw: dict[str, Any],
) -> tuple[
    dict[str, dict[tuple[int, ...], dict[str, Any]]],
    dict[str, dict[tuple[int, ...], dict[int, Any]]],
]:
    """Classify every walked OID into mapped rows and unmapped extras."""
    rows: dict[str, dict[tuple[int, ...], dict[str, Any]]] = {t.key: {} for t in TABLES}
    extras: dict[str, dict[tuple[int, ...], dict[int, Any]]] = {t.key: {} for t in TABLES}

    for oid, value in raw.items():
        for prefix, table in TABLES_BY_PREFIX:
            if not oid.startswith(prefix):
                continue
            parts = oid[len(prefix) :].split(".")
            try:
                numbers = [int(part) for part in parts]
            except ValueError:
                break
            if len(numbers) < 2:
                break
            column_number = numbers[0]
            index = tuple(numbers[1:])
            if len(index) != len(table.index):
                # Not a row of this table after all (an unknown sibling table
                # sharing the prefix); keep it as an extra so nothing is lost.
                extras[table.key].setdefault(index, {})[column_number] = value
                break
            column = table.column_for(column_number)
            if column is None:
                extras[table.key].setdefault(index, {})[column_number] = value
            else:
                rows[table.key].setdefault(index, {})[column.key] = value
            break

    return rows, extras


def _distinct_per_position(indexes: list[tuple[int, ...]], start: int, stop: int) -> list[int]:
    """Count distinct values at each index position in [start, stop)."""
    counts: list[set[int]] = [set() for _ in range(stop - start)]
    for index in indexes:
        for offset, position in enumerate(range(start, stop)):
            if position < len(index):
                counts[offset].add(index[position])
    return [len(values) for values in counts]


def _text(row: dict[str, Any], key: str | None) -> str | None:
    """Return a non-empty stripped string column, or None."""
    if key is None:
        return None
    value = row.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _looks_generic(name: str, position: str, singular: str, number: int) -> bool:
    """Report whether a name carries nothing the position does not already say.

    A factory-default outlet is called "Outlet A1", which would otherwise be
    rendered as "Outlet A1 (Outlet A1)".
    """

    def norm(value: str) -> str:
        return "".join(value.lower().split())

    return norm(name) in {
        norm(position),
        norm(f"{singular} {position}"),
        norm(f"{singular} {number}"),
        norm(str(number)),
    }


def _device_label(table: Table, row: dict[str, Any], index: tuple[int, ...]) -> str | None:
    """Label a row the way the PDU describes it.

    For a table with a position column the physical position leads, and any
    name set on the PDU -- in practice, whatever is plugged in -- follows in
    brackets: "Outlet A1 (Firewall)". A name that just repeats the position is
    dropped. Everywhere else the configured name is used on its own.
    """
    name = _text(row, table.label_column)
    if table.position_column is None:
        return name

    number = index[-1]
    position = _text(row, table.position_column) or str(number)
    base = f"{table.singular} {position}".strip()
    if name is None or _looks_generic(name, position, table.singular, number):
        return base
    return f"{base} ({name})"


def build_labels(
    rows: dict[str, dict[tuple[int, ...], dict[str, Any]]],
) -> dict[str, dict[tuple[int, ...], str]]:
    """Build a readable label for every row.

    Index positions the device only has one of (a single input, a single
    phase) are dropped, so a one-input unit gets "Input voltage" rather than
    "Input 1 Phase 1 voltage". Child tables inherit their parent's label, so
    an outlet's measurements, switch and buttons are all named after the
    outlet -- including whatever is plugged into it. See `_device_label`.
    """
    labels: dict[str, dict[tuple[int, ...], str]] = {}

    def label_for_table(table: Table) -> dict[tuple[int, ...], str]:
        table_rows = rows.get(table.key, {})
        indexes = list(table_rows)
        result: dict[tuple[int, ...], str] = {}
        if not indexes:
            return result

        parent = TABLES_BY_KEY.get(table.parent) if table.parent else None
        start = len(parent.index) if parent else 1
        distinct = _distinct_per_position(indexes, start, len(table.index))

        for index in indexes:
            # Index positions past the parent's (a phase, a probe number) are
            # only spelled out when the device actually has more than one.
            suffix = [
                f"{table.index[position].name} {index[position]}"
                for offset, position in enumerate(range(start, len(table.index)))
                if table.index[position].always or distinct[offset] > 1
            ]

            if parent is not None:
                base = labels.get(parent.key, {}).get(index[: len(parent.index)], "")
            else:
                # A name configured on the PDU replaces the generic index.
                base = _device_label(table, table_rows[index], index) or ""
                if base:
                    suffix = []

            parts = [part for part in [base, *suffix] if part]
            result[index] = " ".join(parts) if parts else table.singular
        return result

    # Parents first so children can inherit.
    for table in sorted(TABLES, key=lambda t: t.parent is not None):
        labels[table.key] = label_for_table(table)
    return labels


def build_units(rows: dict[str, dict[tuple[int, ...], dict[str, Any]]]) -> dict[int, UnitInfo]:
    """Describe every unit on the chain.

    Units are taken from unitTable when it is readable, and otherwise
    reconstructed from the unit component of any other table's index, so a
    firmware that names its columns differently still yields devices.
    """
    unit_rows = rows.get("unit", {})
    indexes: set[int] = {index[0] for index in unit_rows}
    for table_key, table_rows in rows.items():
        if table_key == "unit":
            continue
        indexes.update(index[0] for index in table_rows if index)

    if not indexes:
        return {}

    host = min(indexes)
    units: dict[int, UnitInfo] = {}
    for index in sorted(indexes):
        row = unit_rows.get((index,), {})
        name = row.get("name") or row.get("product_name")
        if not isinstance(name, str) or not name.strip():
            name = f"ePDU unit {index}"
        units[index] = UnitInfo(
            index=index,
            name=name.strip(),
            product_name=_clean(row.get("product_name")),
            part_number=_clean(row.get("part_number")),
            serial_number=_clean(row.get("serial_number")),
            firmware_version=_clean(row.get("firmware_version")),
            is_host=index == host,
        )
    return units


def _clean(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _scale_from_unit_row(
    rows: dict[str, dict[tuple[int, ...], dict[str, Any]]], unit_index: int
) -> str | None:
    """Read the unit's own temperatureScale setting (MIB: unitTable column 9)."""
    value = rows.get("unit", {}).get((unit_index,), {}).get("temperature_scale")
    if value == 0:
        return UnitOfTemperature.CELSIUS
    if value == 1:
        return UnitOfTemperature.FAHRENHEIT
    return None


def _scale_from_sentinel(
    rows: dict[str, dict[tuple[int, ...], dict[str, Any]]], unit_index: int
) -> str | None:
    """Infer the scale from what an unconnected probe reports.

    A probe that is not connected reads absolute zero, which differs between
    the scales and so is unambiguous. Failing that, a live reading above 60.0
    can only be Fahrenheit.
    """
    values = [
        value
        for index, row in rows.get("temperature", {}).items()
        if index and index[0] == unit_index
        for key, value in row.items()
        if key in ("value", "low_warning", "low_critical", "high_warning", "high_critical")
        and isinstance(value, int)
    ]
    if any(value <= _SENTINEL_FAHRENHEIT for value in values):
        return UnitOfTemperature.FAHRENHEIT
    if any(value <= _SENTINEL_CELSIUS for value in values):
        return UnitOfTemperature.CELSIUS

    live = [
        row["value"]
        for index, row in rows.get("temperature", {}).items()
        if index
        and index[0] == unit_index
        and isinstance(row.get("value"), int)
        and row["value"] > _SENTINEL_CELSIUS
    ]
    if live and max(live) > _LIVE_FAHRENHEIT_HINT:
        return UnitOfTemperature.FAHRENHEIT
    return None


def detect_temperature_unit(
    rows: dict[str, dict[tuple[int, ...], dict[str, Any]]],
    unit_index: int | None = None,
) -> str | None:
    """Work out which scale the PDU reports temperatures in.

    The unit's own temperatureScale object is authoritative; the absolute-zero
    sentinel is the fallback for firmware that does not expose it. Returns
    None when neither is available, in which case the caller keeps its current
    setting.
    """
    if unit_index is not None:
        candidates = [unit_index]
    else:
        candidates = sorted(
            {index[0] for index in rows.get("unit", {}) if index}
            | {index[0] for index in rows.get("temperature", {}) if index}
        )
    for candidate in candidates:
        found = _scale_from_unit_row(rows, candidate) or _scale_from_sentinel(rows, candidate)
        if found:
            return found
    return None


def build_environment(
    rows: dict[str, dict[tuple[int, ...], dict[str, Any]]],
    units: dict[int, UnitInfo],
    labels: dict[str, dict[tuple[int, ...], str]],
    temperature_units: dict[int, str],
) -> dict[int, EnvironmentSummary]:
    """Summarise the environmental module of every unit.

    A unit with no module, or one whose probes report "not connected", gets
    the N/A state instead of a missing or zeroed reading.
    """
    summaries: dict[int, EnvironmentSummary] = {}

    for unit_index in units:
        temperature_unit = temperature_units.get(unit_index, UnitOfTemperature.CELSIUS)
        attributes: dict[str, Any] = {}
        connected_total = 0
        expected_total = 0

        for table_key, count_key in ENVIRONMENT_TABLES:
            table_rows = {
                index: row
                for index, row in rows.get(table_key, {}).items()
                if index and index[0] == unit_index
            }
            expected = rows.get("unit", {}).get((unit_index,), {}).get(count_key)
            if isinstance(expected, int):
                expected_total += expected
            connected = [
                index
                for index, row in table_rows.items()
                if row.get("probe_status") in PROBE_OK_STATES
            ]
            connected_total += len(connected)

            detail: dict[str, Any] = {}
            for index, row in sorted(table_rows.items()):
                label = (
                    labels.get(table_key, {}).get(index)
                    or f"{table_key.capitalize()} probe {index[-1]}"
                )
                ok = row.get("probe_status") in PROBE_OK_STATES
                value = row.get("value") if table_key != "contact" else row.get("state")
                if not ok or value is None:
                    detail[label] = NOT_AVAILABLE
                elif table_key == "temperature":
                    detail[label] = f"{round(value * 0.1, 1)} {temperature_unit}"
                elif table_key == "humidity":
                    detail[label] = f"{round(value * 0.1, 1)} %"
                else:
                    detail[label] = {0: "open", 1: "closed"}.get(value, NOT_AVAILABLE)

            attributes[f"{table_key}_expected"] = (
                expected if isinstance(expected, int) else NOT_AVAILABLE
            )
            attributes[f"{table_key}_connected"] = len(connected)
            attributes[table_key] = detail or NOT_AVAILABLE

        if connected_total:
            state = "connected"
        elif expected_total:
            state = NOT_AVAILABLE
        else:
            state = NOT_AVAILABLE
        summaries[unit_index] = EnvironmentSummary(state=state, attributes=attributes)

    return summaries


def build_data(
    raw: dict[str, Any],
    sys_values: dict[str, Any],
    temperature_unit: str,
) -> EpduData:
    """Build the full model from one walk."""
    rows, extras = parse_walk(raw)
    labels = build_labels(rows)
    units = build_units(rows)
    temperature_units = {
        index: detect_temperature_unit(rows, index) or temperature_unit for index in units
    }
    host = next((u.index for u in units.values() if u.is_host), None)
    unit_of_temperature = (
        temperature_units.get(host, temperature_unit) if host is not None else temperature_unit
    )
    environment = build_environment(rows, units, labels, temperature_units)
    redundant = build_redundant(rows)

    units_present = raw.get(OID_UNITS_PRESENT)
    return EpduData(
        rows=rows,
        extras=extras,
        labels=labels,
        units=units,
        units_present=str(units_present) if units_present is not None else None,
        environment=environment,
        sys=sys_values,
        raw=raw,
        temperature_unit=unit_of_temperature,
        temperature_units=temperature_units,
        redundant=redundant,
    )


def build_redundant(
    rows: dict[str, dict[tuple[int, ...], dict[str, Any]]],
) -> set[tuple[str, tuple[int, ...]]]:
    """Find per-input totals that merely restate a single phase.

    On a single-phase input, inputTotalVA/Watts/PowerFactor/VAR carry exactly
    what the one inputPower row already carries, so exposing both produces
    pairs of identically named entities. On a multi-phase input the totals are
    a real sum and are kept.
    """
    phases: dict[tuple[int, ...], set[int]] = {}
    for index in rows.get("input_power", {}):
        if len(index) == 3:
            phases.setdefault(index[:2], set()).add(index[2])

    return {
        ("input_total", index)
        for index in rows.get("input_total", {})
        if len(phases.get(index, ())) == 1
    }


def row_is_readable(row: dict[str, Any]) -> bool:
    """Report whether a row's readings can be trusted.

    Eaton keeps reporting a humidity of 0 and a threshold status of "good" for
    a probe that is not there, so every value of such a row is suppressed.
    """
    status = row.get("probe_status")
    if status is None:
        return True
    return status in PROBE_OK_STATES


# --- value conversion --------------------------------------------------------
def convert(column: Column, value: Any) -> Any:
    """Apply a column's N/A rules, scaling and transforms."""
    if value is None:
        return None
    if isinstance(value, int):
        if value in column.na_values:
            return None
        if column.na_below is not None and value <= column.na_below:
            return None

    if column.transform == "epoch":
        return _from_epoch(value)
    if column.transform == "dateandtime":
        return _from_date_and_time(value)

    if column.enum is not None:
        if not isinstance(value, int):
            return NOT_AVAILABLE if value is None else str(value)
        return column.enum.get(value, f"unknown ({value})")

    if isinstance(value, (int, float)) and column.scale != 1.0:
        scaled = value * column.scale
        return round(scaled, column.precision if column.precision is not None else 3)
    return value


def _from_epoch(value: Any) -> datetime | None:
    if not isinstance(value, int) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _from_date_and_time(value: Any) -> datetime | None:
    """Decode an SNMPv2-TC DateAndTime octet string.

    Format: year(2) month day hour minute second deci-seconds, optionally
    followed by a direction character and the UTC offset.
    """
    if not isinstance(value, str):
        return None
    try:
        # snmp.py renders undecodable octets as hex; on the rare timestamp that
        # happens to be valid UTF-8 the original bytes are recovered instead.
        octets = bytes.fromhex(value[2:]) if value.startswith("0x") else value.encode("latin-1")
    except (ValueError, UnicodeEncodeError):
        return None
    if len(octets) < 8:
        return None
    try:
        year = (octets[0] << 8) | octets[1]
        stamp = datetime(
            year,
            octets[2],
            octets[3],
            octets[4],
            octets[5],
            min(octets[6], 59),
            (octets[7] % 10) * 100000,
            tzinfo=UTC,
        )
    except ValueError:
        return None

    tz = UTC
    if len(octets) >= 11:
        # Eaton encodes the offset hour as a signed byte; the direction
        # character is honoured when it is a real '+' or '-'.
        hours = octets[9] if octets[9] < 128 else octets[9] - 256
        minutes = octets[10] if octets[10] < 128 else octets[10] - 256
        direction = chr(octets[8]) if 32 <= octets[8] < 127 else "+"
        try:
            offset = timedelta(hours=abs(hours), minutes=abs(minutes))
            tz = timezone(-offset if direction == "-" else offset)
        except ValueError:
            tz = UTC
    return stamp.replace(tzinfo=tz)


__all__ = [
    "BASE_OID",
    "EnvironmentSummary",
    "EpduData",
    "UnitInfo",
    "build_data",
    "build_redundant",
    "convert",
    "detect_temperature_unit",
    "parse_walk",
    "row_is_readable",
]
