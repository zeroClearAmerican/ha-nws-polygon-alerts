"""Button: send a test notification."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import NWSAlertsCoordinator, NWSConfigEntry
from .entity import NWSAlertsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NWSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([TestAlertButton(entry.runtime_data)])


class TestAlertButton(NWSAlertsEntity, ButtonEntity):
    def __init__(self, coordinator: NWSAlertsCoordinator) -> None:
        super().__init__(coordinator, "send_test_alert")

    async def async_press(self) -> None:
        await self.coordinator.async_send_test()
