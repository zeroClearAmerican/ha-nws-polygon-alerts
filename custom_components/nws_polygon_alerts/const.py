"""Constants for NWS Polygon Alerts."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "nws_polygon_alerts"

API_BASE: Final = "https://api.weather.gov"
USER_AGENT: Final = (
    "(HomeAssistant nws_polygon_alerts, "
    "https://github.com/zeroClearAmerican/ha-nws-polygon-alerts)"
)

TORNADO_WARNING: Final = "Tornado Warning"
SEVERE_TSTORM_WARNING: Final = "Severe Thunderstorm Warning"

# ---- config entry data ----
CONF_LOCATION: Final = "location"

# ---- options: monitoring ----
CONF_TORNADO: Final = "monitor_tornado"
CONF_TSTORM: Final = "monitor_severe_thunderstorm"
CONF_OTHER_EVENTS: Final = "other_events"
CONF_INCLUDE_ZONE_ALERTS: Final = "include_zone_alerts"
CONF_SCAN_INTERVAL: Final = "scan_interval"

# ---- options: notifications ----
CONF_NOTIFY_SERVICES: Final = "notify_services"
CONF_CRITICAL_EVENTS: Final = "critical_events"
CONF_PERSISTENT: Final = "persistent_notification"
CONF_NOTIFY_ON_UPDATE: Final = "notify_on_update"
CONF_NOTIFY_ON_CLEAR: Final = "notify_on_clear"

# ---- options: message templates ----
CONF_TORNADO_TITLE: Final = "tornado_title"
CONF_TORNADO_MESSAGE: Final = "tornado_message"
CONF_TSTORM_TITLE: Final = "tstorm_title"
CONF_TSTORM_MESSAGE: Final = "tstorm_message"
CONF_OTHER_TITLE: Final = "other_title"
CONF_OTHER_MESSAGE: Final = "other_message"
CONF_CLEAR_TITLE: Final = "clear_title"
CONF_CLEAR_MESSAGE: Final = "clear_message"

DEFAULT_SCAN_INTERVAL: Final = 60  # seconds
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 900

# Number of consecutive failed polls before the "API problem" sensor turns on.
# Single 502/503/504s from api.weather.gov are common and not worth alarming on.
FAILURE_THRESHOLD: Final = 3

DEFAULT_TEMPLATES: Final = {
    CONF_TORNADO_TITLE: "🚨 TORNADO WARNING – {{ location }} 🚨",
    CONF_TORNADO_MESSAGE: "{{ instruction or description or headline }}",
    CONF_TSTORM_TITLE: "⛈️ Severe Thunderstorm Warning – {{ location }}",
    CONF_TSTORM_MESSAGE: "{{ headline }}\n\n{{ instruction or description }}",
    CONF_OTHER_TITLE: "⚠️ {{ event }} – {{ location }}",
    CONF_OTHER_MESSAGE: "{{ headline }}",
    CONF_CLEAR_TITLE: "✅ {{ event }} cleared – {{ location }}",
    CONF_CLEAR_MESSAGE: "The {{ event }} for {{ location }} has expired or been cancelled.",
}

DEFAULT_OPTIONS: Final = {
    CONF_TORNADO: True,
    CONF_TSTORM: True,
    CONF_OTHER_EVENTS: [],
    CONF_INCLUDE_ZONE_ALERTS: False,
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    CONF_NOTIFY_SERVICES: [],
    CONF_CRITICAL_EVENTS: [TORNADO_WARNING],
    CONF_PERSISTENT: True,
    CONF_NOTIFY_ON_UPDATE: False,
    CONF_NOTIFY_ON_CLEAR: True,
    **DEFAULT_TEMPLATES,
}

# Polygon-based ("storm-based") products, offered first in the event picker.
COMMON_EVENTS: Final = [
    "Flash Flood Warning",
    "Flood Warning",
    "Flood Advisory",
    "Special Weather Statement",
    "Extreme Wind Warning",
    "Snow Squall Warning",
    "Dust Storm Warning",
    "Special Marine Warning",
    "Tornado Watch",
    "Severe Thunderstorm Watch",
    "Flash Flood Watch",
    "Winter Storm Warning",
    "Blizzard Warning",
    "Ice Storm Warning",
    "High Wind Warning",
    "Excessive Heat Warning",
    "Hurricane Warning",
    "Tropical Storm Warning",
    "Storm Surge Warning",
]

# Fired on the HA event bus.
EVENT_NEW_ALERT: Final = f"{DOMAIN}_new_alert"
EVENT_UPDATED_ALERT: Final = f"{DOMAIN}_alert_updated"
EVENT_CLEARED_ALERT: Final = f"{DOMAIN}_alert_cleared"
EVENT_TEST_ALERT: Final = f"{DOMAIN}_test_alert"

# Mobile-app payload that makes a notification critical / break through DND.
# iOS reads "push"; Android reads ttl/priority/channel. Each ignores the other's keys.
CRITICAL_NOTIFY_DATA: Final = {
    "push": {"sound": {"name": "default", "critical": 1, "volume": 1.0}},
    "ttl": 0,
    "priority": "high",
    "channel": "alarm_stream",
}
