"""Sensors for the Eaton ePDU integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_EXPOSE_UNMAPPED, NOT_AVAILABLE
from .coordinator import EatonEpduConfigEntry, EatonEpduCoordinator
from .entity import EatonEpduEntity, async_add_discovered, base_id, entity_name
from .model import EpduData, convert, row_is_readable
from .oids import TABLES, Column, Table


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EatonEpduConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors, and keep setting them up as units are added."""
    coordinator = entry.runtime_data
    expose_unmapped = entry.options.get(CONF_EXPOSE_UNMAPPED, False)

    def _factory() -> Iterable[Entity]:
        data = coordinator.data
        if data is None:
            return []
        entities: list[Entity] = []

        for table in TABLES:
            for index in data.rows.get(table.key, {}):
                if data.is_redundant(table.key, index):
                    continue
                for column in table.columns:
                    if column.info_only or column.platform != "sensor":
                        continue
                    entities.append(EpduColumnSensor(coordinator, table, index, column))

        if expose_unmapped:
            for table in TABLES:
                for index, columns in data.extras.get(table.key, {}).items():
                    for number in columns:
                        entities.append(EpduUnmappedSensor(coordinator, table, index, number))

        for unit_index in data.units:
            entities.append(EpduEnvironmentSensor(coordinator, unit_index))

        host = next((u.index for u in data.units.values() if u.is_host), None)
        if host is not None:
            for description, value_fn in HOST_SENSORS:
                entities.append(EpduHostSensor(coordinator, host, description, value_fn))
        return entities

    entry.async_on_unload(async_add_discovered(coordinator, async_add_entities, _factory))


class EpduColumnSensor(EatonEpduEntity, SensorEntity):
    """One mapped column of one row."""

    def __init__(
        self,
        coordinator: EatonEpduCoordinator,
        table: Table,
        index: tuple[int, ...],
        column: Column,
    ) -> None:
        """Initialise the sensor."""
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
        self._attr_device_class = column.device_class
        self._attr_state_class = column.state_class
        self._attr_icon = column.icon
        self._attr_suggested_display_precision = column.precision

        if column.temperature:
            self._attr_native_unit_of_measurement = coordinator.temperature_unit_for(index[0])
        else:
            self._attr_native_unit_of_measurement = column.unit

        if column.device_class == SensorDeviceClass.ENERGY:
            self._attr_suggested_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        # A string state must not carry a unit or a state class.
        if column.enum is not None:
            self._attr_native_unit_of_measurement = None
            self._attr_state_class = None

    @property
    def name(self) -> str:
        """Row label plus column name."""
        label = ""
        if self._table.use_label_for_entities and self.coordinator.data is not None:
            label = self.coordinator.data.label(self._table.key, self._index)
        return entity_name(label, self._column.name)

    @property
    def native_value(self) -> Any:
        """Converted value, or N/A for a text column with nothing to report."""
        data: EpduData | None = self.coordinator.data
        raw = None
        if data is not None:
            row = data.rows.get(self._table.key, {}).get(self._index, {})
            if self._column.key == "probe_status" or row_is_readable(row):
                raw = row.get(self._column.key)
        value = convert(self._column, raw)
        if value is None and self._column.enum is not None:
            return NOT_AVAILABLE
        return value

    @property
    def available(self) -> bool:
        """Available while the row is still being reported."""
        if not super().available or self.coordinator.data is None:
            return False
        return self._index in self.coordinator.data.rows.get(self._table.key, {})


class EpduUnmappedSensor(EatonEpduEntity, SensorEntity):
    """A column this integration has no name for, exposed on request."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: EatonEpduCoordinator,
        table: Table,
        index: tuple[int, ...],
        number: int,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, index[0] if index else 0)
        self._table = table
        self._index = index
        self._number = number
        self._attr_unique_id = (
            f"{base_id(coordinator.entry)}_{table.key}_"
            f"{'_'.join(str(part) for part in index)}_col{number}"
        )

    @property
    def name(self) -> str:
        """Row label plus the raw column number."""
        label = ""
        if self.coordinator.data is not None and self._table.use_label_for_entities:
            label = self.coordinator.data.label(self._table.key, self._index)
        noun = (self._table.singular or self._table.key).strip()
        return entity_name(label, f"{noun} column {self._number}".strip())

    @property
    def native_value(self) -> Any:
        """Raw value straight from the walk."""
        if self.coordinator.data is None:
            return None
        value = (
            self.coordinator.data.extras.get(self._table.key, {})
            .get(self._index, {})
            .get(self._number)
        )
        if isinstance(value, str) and len(value) > 255:
            return value[:255]
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Point at the OID so it can be looked up in the MIB."""
        suffix = ".".join(str(part) for part in self._index)
        return {"oid": f"{self._table.oid}.{self._number}.{suffix}"}


class EpduEnvironmentSensor(EatonEpduEntity, SensorEntity):
    """Per-unit environment summary.

    Reports N/A when the unit has no environmental module, or when its probes
    are not connected, rather than silently dropping the readings.
    """

    _attr_icon = "mdi:thermometer-water"

    def __init__(self, coordinator: EatonEpduCoordinator, unit_index: int) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, unit_index)
        self._attr_unique_id = f"{base_id(coordinator.entry)}_environment_{unit_index}"
        self._attr_name = "Environment"

    @property
    def native_value(self) -> str:
        """Report `connected` when at least one probe reads, otherwise N/A."""
        if self.coordinator.data is None:
            return NOT_AVAILABLE
        summary = self.coordinator.data.environment.get(self._unit_index)
        return summary.state if summary else NOT_AVAILABLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Per-probe detail, with N/A for anything unreadable."""
        if self.coordinator.data is None:
            return {}
        summary = self.coordinator.data.environment.get(self._unit_index)
        return summary.attributes if summary else {}


class EpduHostSensor(EatonEpduEntity, SensorEntity):
    """A chain-wide value, reported on the host unit."""

    def __init__(
        self,
        coordinator: EatonEpduCoordinator,
        unit_index: int,
        description: SensorEntityDescription,
        value_fn: Callable[[EpduData], Any],
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, unit_index)
        self.entity_description = description
        self._value_fn = value_fn
        self._attr_unique_id = f"{base_id(coordinator.entry)}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Value derived from the whole model."""
        if self.coordinator.data is None:
            return None
        return self._value_fn(self.coordinator.data)


def _units_present(data: EpduData) -> str:
    if data.units_present:
        return data.units_present
    return ",".join(str(index) for index in sorted(data.units))


HOST_SENSORS: tuple[tuple[SensorEntityDescription, Callable[[EpduData], Any]], ...] = (
    (
        SensorEntityDescription(
            key="units_present",
            name="Units present",
            icon="mdi:link-variant",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        _units_present,
    ),
    (
        SensorEntityDescription(
            key="unit_count",
            name="Unit count",
            icon="mdi:counter",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        lambda data: len(data.units),
    ),
    (
        SensorEntityDescription(
            key="sys_name",
            name="System name",
            icon="mdi:tag",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        lambda data: data.sys.get("sys_name") or NOT_AVAILABLE,
    ),
    (
        SensorEntityDescription(
            key="sys_location",
            name="Location",
            icon="mdi:map-marker",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        lambda data: data.sys.get("sys_location") or NOT_AVAILABLE,
    ),
    (
        SensorEntityDescription(
            key="sys_uptime",
            name="SNMP agent uptime",
            native_unit_of_measurement=UnitOfTime.SECONDS,
            suggested_unit_of_measurement=UnitOfTime.DAYS,
            suggested_display_precision=1,
            device_class=SensorDeviceClass.DURATION,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        # sysUpTime is in hundredths of a second.
        lambda data: (
            round(data.sys["sys_uptime"] / 100)
            if isinstance(data.sys.get("sys_uptime"), int)
            else None
        ),
    ),
)
