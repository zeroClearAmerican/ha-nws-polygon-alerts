"""Polling coordinator: fetch, match, diff and notify."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .alerts import Alert, AlertChanges, AlertTracker, match_alerts
from .api import NWSApiError, NWSClient
from .const import (
    CONF_CLEAR_MESSAGE,
    CONF_CLEAR_TITLE,
    CONF_CRITICAL_EVENTS,
    CONF_INCLUDE_ZONE_ALERTS,
    CONF_LOCATION,
    CONF_NOTIFY_ON_CLEAR,
    CONF_NOTIFY_ON_UPDATE,
    CONF_NOTIFY_SERVICES,
    CONF_OTHER_EVENTS,
    CONF_OTHER_MESSAGE,
    CONF_OTHER_TITLE,
    CONF_PERSISTENT,
    CONF_SCAN_INTERVAL,
    CONF_TORNADO,
    CONF_TORNADO_MESSAGE,
    CONF_TORNADO_TITLE,
    CONF_TSTORM,
    CONF_TSTORM_MESSAGE,
    CONF_TSTORM_TITLE,
    CRITICAL_NOTIFY_DATA,
    DEFAULT_OPTIONS,
    DEFAULT_TEMPLATES,
    DOMAIN,
    EVENT_CLEARED_ALERT,
    EVENT_NEW_ALERT,
    EVENT_TEST_ALERT,
    EVENT_UPDATED_ALERT,
    FAILURE_THRESHOLD,
    SEVERE_TSTORM_WARNING,
    TORNADO_WARNING,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

type NWSConfigEntry = ConfigEntry[NWSAlertsCoordinator]


@dataclass
class AlertsData:
    alerts: dict[str, Alert] = field(default_factory=dict)
    last_success: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0

    @property
    def problem(self) -> bool:
        return self.consecutive_failures >= FAILURE_THRESHOLD

    def has_event(self, event: str) -> bool:
        return any(a.event == event for a in self.alerts.values())


class NWSAlertsCoordinator(DataUpdateCoordinator[AlertsData]):
    config_entry: NWSConfigEntry

    def __init__(self, hass: HomeAssistant, entry: NWSConfigEntry) -> None:
        self.options: dict[str, Any] = {**DEFAULT_OPTIONS, **entry.options}
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(seconds=self.options[CONF_SCAN_INTERVAL]),
        )
        loc = entry.data[CONF_LOCATION]
        self.lat: float = float(loc[CONF_LATITUDE])
        self.lon: float = float(loc[CONF_LONGITUDE])
        self.location_name: str = entry.title
        self.client = NWSClient(async_get_clientsession(hass))
        self.tracker = AlertTracker()
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )

    async def async_restore(self) -> None:
        """Reload alerts we already notified about, so a restart/reload doesn't re-alert."""
        stored = await self._store.async_load() or {}
        now = dt_util.utcnow()
        for raw in stored.get("active", []):
            try:
                alert = Alert.from_dict(raw)
            except (KeyError, TypeError):
                continue
            if not alert.is_expired(now):
                self.tracker.active[alert.id] = alert

    async def _async_save(self) -> None:
        await self._store.async_save(
            {"active": [a.as_dict() for a in self.tracker.active.values()]}
        )

    # ------------------------------------------------------------ config

    @property
    def monitored_events(self) -> set[str]:
        events = set(self.options[CONF_OTHER_EVENTS])
        if self.options[CONF_TORNADO]:
            events.add(TORNADO_WARNING)
        else:
            events.discard(TORNADO_WARNING)
        if self.options[CONF_TSTORM]:
            events.add(SEVERE_TSTORM_WARNING)
        else:
            events.discard(SEVERE_TSTORM_WARNING)
        return events

    # ------------------------------------------------------------ polling

    async def _async_update_data(self) -> AlertsData:
        previous = self.data
        now = dt_util.utcnow()
        try:
            features = await self.client.active_alerts(self.lat, self.lon)
        except NWSApiError as err:
            if previous is None:
                # First refresh: let HA retry setup later.
                raise UpdateFailed(str(err)) from err
            failures = previous.consecutive_failures + 1
            log = _LOGGER.warning if failures >= FAILURE_THRESHOLD else _LOGGER.debug
            log("%s: alert fetch failed (%d in a row): %s", self.location_name, failures, err)
            # Keep last known alerts, minus any that have since expired.
            current = {
                k: a for k, a in previous.alerts.items() if not a.is_expired(now)
            }
            data = AlertsData(
                alerts=current,
                last_success=previous.last_success,
                last_error=str(err),
                consecutive_failures=failures,
            )
        else:
            current = match_alerts(
                features,
                self.lat,
                self.lon,
                self.monitored_events,
                self.options[CONF_INCLUDE_ZONE_ALERTS],
                now,
            )
            data = AlertsData(alerts=current, last_success=now)

        changes = self.tracker.update(current)
        if changes.new or changes.updated or changes.cleared:
            await self._async_save()
            await self._handle_changes(changes)
        return data

    # ------------------------------------------------------------ notifications

    async def _handle_changes(self, changes: AlertChanges) -> None:
        for alert in changes.new:
            _LOGGER.info("%s: new %s (%s)", self.location_name, alert.event, alert.id)
            title, message = self._render_alert(alert)
            self._fire(EVENT_NEW_ALERT, alert, title, message)
            await self._notify(alert, title, message)

        for alert in changes.updated:
            _LOGGER.info("%s: updated %s (%s)", self.location_name, alert.event, alert.id)
            title, message = self._render_alert(alert)
            self._fire(EVENT_UPDATED_ALERT, alert, title, message)
            if self.options[CONF_NOTIFY_ON_UPDATE]:
                await self._notify(alert, title, message)
            elif self.options[CONF_PERSISTENT]:
                # Refresh the on-screen card text without pinging phones.
                self._persistent(alert, title, message)

        for alert in changes.cleared:
            _LOGGER.info("%s: cleared %s (%s)", self.location_name, alert.event, alert.id)
            title = self._render(CONF_CLEAR_TITLE, alert)
            message = self._render(CONF_CLEAR_MESSAGE, alert)
            self._fire(EVENT_CLEARED_ALERT, alert, title, message)
            persistent_notification.async_dismiss(self.hass, self._notification_id(alert))
            if self.options[CONF_NOTIFY_ON_CLEAR]:
                await self._send(title, message, critical=False)

    def _template_keys(self, alert: Alert) -> tuple[str, str]:
        if alert.event == TORNADO_WARNING:
            return CONF_TORNADO_TITLE, CONF_TORNADO_MESSAGE
        if alert.event == SEVERE_TSTORM_WARNING:
            return CONF_TSTORM_TITLE, CONF_TSTORM_MESSAGE
        return CONF_OTHER_TITLE, CONF_OTHER_MESSAGE

    def _render_alert(self, alert: Alert) -> tuple[str, str]:
        title_key, message_key = self._template_keys(alert)
        return self._render(title_key, alert), self._render(message_key, alert)

    def _variables(self, alert: Alert) -> dict[str, Any]:
        return {
            **alert.as_dict(),
            "location": self.location_name,
            "latitude": self.lat,
            "longitude": self.lon,
        }

    def _render(self, key: str, alert: Alert) -> str:
        variables = self._variables(alert)
        for source in (self.options.get(key), DEFAULT_TEMPLATES[key]):
            if not source:
                continue
            try:
                return str(
                    Template(source, self.hass).async_render(variables, parse_result=False)
                ).strip()
            except TemplateError as err:
                _LOGGER.error("Template %s failed, using default: %s", key, err)
        return alert.headline or alert.event

    def _fire(self, event_type: str, alert: Alert, title: str, message: str) -> None:
        self.hass.bus.async_fire(
            event_type,
            {
                "config_entry_id": self.config_entry.entry_id,
                **self._variables(alert),
                "title": title,
                "message": message,
            },
        )

    def _notification_id(self, alert: Alert) -> str:
        # Keyed on event type so updates replace the existing card.
        slug = alert.event.lower().replace(" ", "_")
        return f"{DOMAIN}_{self.config_entry.entry_id}_{slug}"

    def _persistent(self, alert: Alert, title: str, message: str) -> None:
        persistent_notification.async_create(
            self.hass, message, title, self._notification_id(alert)
        )

    async def _notify(self, alert: Alert, title: str, message: str) -> None:
        if self.options[CONF_PERSISTENT]:
            self._persistent(alert, title, message)
        await self._send(
            title, message, critical=alert.event in self.options[CONF_CRITICAL_EVENTS]
        )

    async def _send(self, title: str, message: str, critical: bool) -> None:
        for target in self.options[CONF_NOTIFY_SERVICES]:
            service = target.removeprefix("notify.")
            payload: dict[str, Any] = {"title": title, "message": message}
            # Only the mobile app understands this payload; other notify
            # platforms may reject unknown data keys.
            if critical and service.startswith("mobile_app_"):
                payload["data"] = CRITICAL_NOTIFY_DATA
            try:
                await self.hass.services.async_call("notify", service, payload)
            except Exception:  # noqa: BLE001 - one bad target shouldn't block the rest
                _LOGGER.exception("Failed to send notification via notify.%s", service)

    async def async_send_test(self) -> None:
        """Send a test notification through every configured channel."""
        title = f"Test alert – {self.location_name}"
        message = (
            f"This is a test of the NWS alert system for {self.location_name}. "
            "No action is needed."
        )
        self.hass.bus.async_fire(
            EVENT_TEST_ALERT,
            {
                "config_entry_id": self.config_entry.entry_id,
                "location": self.location_name,
                "title": title,
                "message": message,
            },
        )
        if self.options[CONF_PERSISTENT]:
            persistent_notification.async_create(
                self.hass, message, title, f"{DOMAIN}_{self.config_entry.entry_id}_test"
            )
        await self._send(title, message, critical=False)
