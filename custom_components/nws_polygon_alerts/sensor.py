"""Sensors: active alert count and last successful check."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import NWSAlertsCoordinator, NWSConfigEntry
from .entity import NWSAlertsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NWSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([AlertCountSensor(coordinator), LastCheckSensor(coordinator)])


class AlertCountSensor(NWSAlertsEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: NWSAlertsCoordinator) -> None:
        super().__init__(coordinator, "active_alerts")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.alerts)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        alerts = self.coordinator.data.alerts.values()
        return {
            "events": sorted({a.event for a in alerts}),
            "monitored_events": sorted(self.coordinator.monitored_events),
        }


class LastCheckSensor(NWSAlertsEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: NWSAlertsCoordinator) -> None:
        super().__init__(coordinator, "last_check")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.data.last_success
