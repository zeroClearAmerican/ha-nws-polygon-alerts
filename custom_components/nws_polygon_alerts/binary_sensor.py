"""Binary sensors: per-warning-type, any-alert, and API problem."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_TORNADO,
    CONF_TSTORM,
    DOMAIN,
    FAILURE_THRESHOLD,
    SEVERE_TSTORM_WARNING,
    TORNADO_WARNING,
)
from .coordinator import NWSAlertsCoordinator, NWSConfigEntry
from .entity import NWSAlertsEntity

# (translation/unique key, NWS event name, option that enables it)
WARNING_SENSORS = (
    ("tornado_warning", TORNADO_WARNING, CONF_TORNADO),
    ("severe_thunderstorm_warning", SEVERE_TSTORM_WARNING, CONF_TSTORM),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NWSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    registry = er.async_get(hass)

    for key, event, option in WARNING_SENSORS:
        if coordinator.options[option]:
            entities.append(WarningBinarySensor(coordinator, key, event))
        elif entity_id := registry.async_get_entity_id(
            "binary_sensor", DOMAIN, f"{entry.entry_id}_{key}"
        ):
            # Monitoring was turned off; don't leave a sensor that's always "off".
            registry.async_remove(entity_id)

    entities.append(AnyAlertBinarySensor(coordinator))
    entities.append(ProblemBinarySensor(coordinator))
    async_add_entities(entities)


def _alerts_attr(alerts: list[Any]) -> dict[str, Any]:
    return {
        "alerts": [
            {
                "event": a.event,
                "headline": a.headline,
                "severity": a.severity,
                "expires": a.end_time.isoformat() if a.end_time else None,
                "id": a.id,
            }
            for a in alerts
        ]
    }


class WarningBinarySensor(NWSAlertsEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, coordinator: NWSAlertsCoordinator, key: str, event: str) -> None:
        super().__init__(coordinator, key)
        self._event = event

    def _matching(self) -> list[Any]:
        return [a for a in self.coordinator.data.alerts.values() if a.event == self._event]

    @property
    def is_on(self) -> bool:
        return bool(self._matching())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        matching = self._matching()
        attrs: dict[str, Any] = {}
        if matching:
            latest = max(matching, key=lambda a: a.sent.timestamp() if a.sent else 0)
            attrs.update(
                headline=latest.headline,
                description=latest.description,
                instruction=latest.instruction,
                expires=latest.end_time.isoformat() if latest.end_time else None,
                sender=latest.sender,
            )
        return attrs | _alerts_attr(matching)


class AnyAlertBinarySensor(NWSAlertsEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, coordinator: NWSAlertsCoordinator) -> None:
        super().__init__(coordinator, "any_alert")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.alerts)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return _alerts_attr(list(self.coordinator.data.alerts.values()))


class ProblemBinarySensor(NWSAlertsEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: NWSAlertsCoordinator) -> None:
        super().__init__(coordinator, "api_problem")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.problem

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data
        return {
            "consecutive_failures": d.consecutive_failures,
            "failure_threshold": FAILURE_THRESHOLD,
            "last_error": d.last_error,
            "last_success": d.last_success.isoformat() if d.last_success else None,
        }
