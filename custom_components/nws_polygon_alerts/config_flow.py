"""Config + options flow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TemplateSelector,
    TextSelector,
)

from .api import NWSApiError, NWSClient, NWSInvalidLocation
from .const import (
    COMMON_EVENTS,
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
    DEFAULT_OPTIONS,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SEVERE_TSTORM_WARNING,
    TORNADO_WARNING,
)

MESSAGE_SECTIONS = {
    "tornado": (CONF_TORNADO_TITLE, CONF_TORNADO_MESSAGE),
    "severe_thunderstorm": (CONF_TSTORM_TITLE, CONF_TSTORM_MESSAGE),
    "other": (CONF_OTHER_TITLE, CONF_OTHER_MESSAGE),
    "cleared": (CONF_CLEAR_TITLE, CONF_CLEAR_MESSAGE),
}


def _unique_id(lat: float, lon: float) -> str:
    return f"{lat:.4f},{lon:.4f}"


async def _validate_location(hass: HomeAssistant, lat: float, lon: float) -> str | None:
    """Return an error key, or None if the API accepts the point."""
    try:
        await NWSClient(async_get_clientsession(hass)).active_alerts(lat, lon)
    except NWSInvalidLocation:
        return "invalid_location"
    except NWSApiError:
        return "cannot_connect"
    return None


def _location_schema(name: str, lat: float, lon: float) -> dict[Any, Any]:
    return {
        vol.Required(CONF_NAME, default=name): TextSelector(),
        vol.Required(
            CONF_LOCATION, default={CONF_LATITUDE: lat, CONF_LONGITUDE: lon}
        ): LocationSelector(LocationSelectorConfig(radius=False)),
    }


class NWSAlertsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            loc = user_input[CONF_LOCATION]
            lat, lon = float(loc[CONF_LATITUDE]), float(loc[CONF_LONGITUDE])
            await self.async_set_unique_id(_unique_id(lat, lon))
            self._abort_if_unique_id_configured()
            if not (error := await _validate_location(self.hass, lat, lon)):
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={CONF_LOCATION: {CONF_LATITUDE: lat, CONF_LONGITUDE: lon}},
                    options={
                        **DEFAULT_OPTIONS,
                        CONF_TORNADO: user_input[CONF_TORNADO],
                        CONF_TSTORM: user_input[CONF_TSTORM],
                    },
                )
            errors["base"] = error

        default_name = "Home" if not self._async_current_entries() else ""
        schema = vol.Schema(
            {
                **_location_schema(
                    default_name, self.hass.config.latitude, self.hass.config.longitude
                ),
                vol.Required(CONF_TORNADO, default=True): BooleanSelector(),
                vol.Required(CONF_TSTORM, default=True): BooleanSelector(),
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            loc = user_input[CONF_LOCATION]
            lat, lon = float(loc[CONF_LATITUDE]), float(loc[CONF_LONGITUDE])
            await self.async_set_unique_id(_unique_id(lat, lon))
            if entry.unique_id != self.unique_id:
                self._abort_if_unique_id_configured()
            if not (error := await _validate_location(self.hass, lat, lon)):
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=self.unique_id,
                    title=user_input[CONF_NAME],
                    data={CONF_LOCATION: {CONF_LATITUDE: lat, CONF_LONGITUDE: lon}},
                )
            errors["base"] = error

        loc = entry.data[CONF_LOCATION]
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                _location_schema(entry.title, loc[CONF_LATITUDE], loc[CONF_LONGITUDE])
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return NWSAlertsOptionsFlow()


class NWSAlertsOptionsFlow(OptionsFlow):
    @property
    def _opts(self) -> dict[str, Any]:
        return {**DEFAULT_OPTIONS, **self.config_entry.options}

    def _save(self, changes: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(data={**self._opts, **changes})

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["monitoring", "notifications", "messages"]
        )

    # -------------------------------------------------------- monitoring

    async def _event_choices(self) -> list[str]:
        try:
            all_types = await NWSClient(
                async_get_clientsession(self.hass)
            ).event_types()
        except NWSApiError:
            all_types = []
        skip = {TORNADO_WARNING, SEVERE_TSTORM_WARNING}
        common = [e for e in COMMON_EVENTS if e not in skip]
        rest = sorted(set(all_types) - set(common) - skip)
        return common + rest

    async def async_step_monitoring(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            return self._save(user_input)

        o = self._opts
        choices = await self._event_choices()
        # Keep any custom/previously-chosen values selectable.
        choices += [e for e in o[CONF_OTHER_EVENTS] if e not in choices]
        schema = vol.Schema(
            {
                vol.Required(CONF_TORNADO, default=o[CONF_TORNADO]): BooleanSelector(),
                vol.Required(CONF_TSTORM, default=o[CONF_TSTORM]): BooleanSelector(),
                vol.Optional(
                    CONF_OTHER_EVENTS, default=o[CONF_OTHER_EVENTS]
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=choices,
                        multiple=True,
                        custom_value=True,
                        sort=False,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_INCLUDE_ZONE_ALERTS, default=o[CONF_INCLUDE_ZONE_ALERTS]
                ): BooleanSelector(),
                vol.Required(
                    CONF_SCAN_INTERVAL, default=o[CONF_SCAN_INTERVAL]
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=10,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="monitoring", data_schema=schema)

    # -------------------------------------------------------- notifications

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)

        o = self._opts
        services = sorted(
            f"notify.{name}"
            for name in self.hass.services.async_services().get("notify", {})
            if name != "send_message"
        )
        services += [s for s in o[CONF_NOTIFY_SERVICES] if s not in services]

        events = [TORNADO_WARNING, SEVERE_TSTORM_WARNING, *o[CONF_OTHER_EVENTS]]
        events += [e for e in o[CONF_CRITICAL_EVENTS] if e not in events]

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_NOTIFY_SERVICES, default=o[CONF_NOTIFY_SERVICES]
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=services,
                        multiple=True,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_CRITICAL_EVENTS, default=o[CONF_CRITICAL_EVENTS]
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=events,
                        multiple=True,
                        custom_value=True,
                        sort=False,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_PERSISTENT, default=o[CONF_PERSISTENT]): BooleanSelector(),
                vol.Required(
                    CONF_NOTIFY_ON_UPDATE, default=o[CONF_NOTIFY_ON_UPDATE]
                ): BooleanSelector(),
                vol.Required(
                    CONF_NOTIFY_ON_CLEAR, default=o[CONF_NOTIFY_ON_CLEAR]
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="notifications", data_schema=schema)

    # -------------------------------------------------------- messages

    async def async_step_messages(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            flat: dict[str, Any] = {}
            for name, (title_key, message_key) in MESSAGE_SECTIONS.items():
                values = user_input.get(name, {})
                # An emptied field falls back to the built-in default.
                flat[title_key] = values.get(title_key) or DEFAULT_OPTIONS[title_key]
                flat[message_key] = (
                    values.get(message_key) or DEFAULT_OPTIONS[message_key]
                )
            return self._save(flat)

        o = self._opts
        fields: dict[Any, Any] = {}
        for name, (title_key, message_key) in MESSAGE_SECTIONS.items():
            fields[vol.Required(name)] = section(
                vol.Schema(
                    {
                        vol.Optional(title_key, default=o[title_key]): TemplateSelector(),
                        vol.Optional(
                            message_key, default=o[message_key]
                        ): TemplateSelector(),
                    }
                ),
                {"collapsed": name != "tornado"},
            )
        return self.async_show_form(step_id="messages", data_schema=vol.Schema(fields))
