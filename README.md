# NWS Polygon Alerts

A Home Assistant integration that watches the National Weather Service for warnings whose **polygon actually contains your location**, not just your county. It's built for tornado and severe thunderstorm warnings, and you can add any other NWS alert type.

- Monitor as many locations as you want (home, work, the lake house…). Each one is its own entry with its own settings.
- Checks api.weather.gov every 60 seconds by default (adjustable from 30 to 900).
- Turn tornado and severe thunderstorm warnings on or off, and add any other NWS event type.
- Write your own title and message templates for tornado, thunderstorm, other alerts and "all clear".
- Choose which phones and tablets get alerts for each location, plus any other `notify.*` service. Mobile app alerts can be marked **critical** so they break through Do Not Disturb.
- Updates to a warning are recognized, so an extended warning doesn't set off your phone a second time.
- Remembers what it already alerted on across restarts and reloads.

## Install (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/zeroClearAmerican/ha-nws-polygon-alerts`, category **Integration**.
2. Install **NWS Polygon Alerts** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → NWS Polygon Alerts**.
4. Name the location and drop the pin. Repeat for each location.

Open **Configure** on an entry to set:

| Menu | What's there |
|---|---|
| Alert types & polling | Tornado / severe thunderstorm switches, other alert types, match zone-only alerts (watches), poll interval |
| Notifications | Which mobile devices get this location's alerts, other notify services, which events are sent as critical, an alert inside Home Assistant, notify on update, notify on clear |
| Message text | Title and message templates for each category |

To move a location, use **⋮ → Reconfigure** on the entry.

## Entities (per location)

| Entity | Notes |
|---|---|
| `binary_sensor.<name>_tornado_warning` | `safety` class. Attributes: headline, description, instruction, expires, alerts list. Only exists if tornado monitoring is on |
| `binary_sensor.<name>_severe_thunderstorm_warning` | Same, for severe thunderstorm warnings |
| `binary_sensor.<name>_active_alert` | On if *any* monitored alert covers the location |
| `sensor.<name>_active_alerts` | Count of matching alerts |
| `binary_sensor.<name>_api_problem` | Diagnostic. Turns on after 3 failed checks in a row (one-off 502s from the NWS API are normal) |
| `sensor.<name>_last_successful_check` | Diagnostic timestamp |
| `button.<name>_send_test_alert` | Sends a test through all configured notification channels |

If the API goes down, sensors keep their last known state instead of going `unavailable`, and any alert past its end time still clears.

## Events

Fired on every change, whatever your notification settings are:

- `nws_polygon_alerts_new_alert`
- `nws_polygon_alerts_alert_updated`
- `nws_polygon_alerts_alert_cleared`
- `nws_polygon_alerts_test_alert`

Event data includes `config_entry_id`, `location`, `event`, `headline`, `description`, `instruction`, `severity`, `expires`, `url`, … and the rendered `title` and `message`.

## Message templates

Templates are standard Home Assistant Jinja and can use these variables:

`location`, `event`, `headline`, `description`, `instruction`, `area`, `severity`, `certainty`, `urgency`, `sender`, `sent`, `effective`, `expires`, `ends`, `url`, `latitude`, `longitude`

Example:

```jinja
🚨 {{ event | upper }} for {{ location }} until {{ as_timestamp(expires) | timestamp_custom('%-I:%M %p') }}
```

## Example automations

Weekly test, replacing the old "Wednesday at noon" check:

```yaml
automation:
  - alias: Weekly tornado alert test
    triggers:
      - trigger: time
        at: "12:00:00"
    conditions:
      - condition: time
        weekday: wed
      - condition: state
        entity_id: binary_sensor.home_active_alert
        state: "off"
    actions:
      - action: button.press
        target:
          entity_id: button.home_send_test_alert
```

Lights and siren on a tornado warning:

```yaml
automation:
  - alias: Tornado warning – lights on
    triggers:
      - trigger: event
        event_type: nws_polygon_alerts_new_alert
        event_data:
          event: Tornado Warning
    actions:
      - action: light.turn_on
        target:
          area_id: house
        data:
          brightness_pct: 100
          color_name: red
```

## How matching works

1. Each check calls `GET /alerts/active?point=<lat>,<lon>&status=actual`, so the API only returns alerts for your area. You don't need to pick a state or county.
2. Alerts with a polygon only count if your point is inside it (ray casting with support for holes and multipolygons; verified to match turf.js).
3. Alerts with no polygon (watches, most advisories) only count if **Also match alerts without a polygon** is on.
4. Cancellations, test messages and alerts past their end time are ignored.

## Development

`custom_components/nws_polygon_alerts/alerts.py` has no Home Assistant imports. Test it with:

```sh
python3 -m unittest discover tests
```

To release: bump `version` in `manifest.json`, then tag and publish a GitHub release (`v0.1.1`, …). HACS will offer the update.
