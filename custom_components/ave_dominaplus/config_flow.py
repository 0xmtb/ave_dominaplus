"""Config flow for the AVE ws integration."""

from __future__ import annotations

import asyncio
import logging
from types import MappingProxyType
from typing import Any

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import AVE_FAMILY_ANTITHEFT_AREA, DOMAIN
from .web_server import AveWebServer

_LOGGER = logging.getLogger(__name__)


def _build_step_user_data_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build config schema for user-like setup steps."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_IP_ADDRESS,
                default=defaults.get(CONF_IP_ADDRESS, "192.168.1.10"),
            ): str,
            vol.Required(
                "fetch_lights",
                default=defaults.get("fetch_lights", True),
            ): bool,
            vol.Required(
                "on_off_lights_as_switch",
                default=defaults.get("on_off_lights_as_switch", True),
            ): bool,
            vol.Required(
                "fetch_thermostats",
                default=defaults.get("fetch_thermostats", True),
            ): bool,
            vol.Required(
                "fetch_covers",
                default=defaults.get("fetch_covers", True),
            ): bool,
            vol.Required(
                "fetch_scenarios",
                default=defaults.get("fetch_scenarios", True),
            ): bool,
            vol.Required(
                "fetch_sensor_areas",
                default=defaults.get("fetch_sensor_areas", True),
            ): bool,
            vol.Required(
                "fetch_sensors",
                default=defaults.get("fetch_sensors", True),
            ): bool,
            vol.Required(
                "get_entities_names",
                default=defaults.get("get_entities_names", True),
            ): bool,
            vol.Optional(
                "antitheft_pin",
                default=defaults.get("antitheft_pin", ""),
            ): str,
        }
    )


class AveWsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AVE ws."""

    VERSION = 1

    _discovered_user_input: dict[str, Any] | None = None
    _discovered_title: str | None = None
    _discovered_mac: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        """Return the options flow handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_IP_ADDRESS: user_input[CONF_IP_ADDRESS]}
            )

            try:
                info = await self.validate_input(user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_step_user_data_schema(),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery."""
        _LOGGER.debug(
            "Zeroconf discovery for AVE candidate: name=%s type=%s host=%s ips=%s",
            discovery_info.name,
            discovery_info.type,
            discovery_info.host,
            [str(ip_addr) for ip_addr in discovery_info.ip_addresses],
        )
        discovered_host = discovery_info.host
        for ip_addr in discovery_info.ip_addresses:
            if ip_addr.version == 4:
                discovered_host = str(ip_addr)
                break

        user_input = {
            CONF_IP_ADDRESS: discovered_host,
            "get_entities_names": True,
            "fetch_sensor_areas": True,
            "fetch_sensors": True,
            "fetch_lights": True,
            "fetch_covers": True,
            "fetch_scenarios": True,
            "fetch_thermostats": True,
            "on_off_lights_as_switch": True,
        }
        self._async_abort_entries_match({CONF_IP_ADDRESS: user_input[CONF_IP_ADDRESS]})

        try:
            info = await self.validate_input(user_input, require_mac_address=True)
        except CannotConnect:
            return self.async_abort(reason="cannot_connect")
        except MacAddressNotFound:
            return self.async_abort(reason="not_ave_webserver")
        except data_entry_flow.AbortFlow as err:
            if err.reason == "already_in_progress":
                return self.async_abort(reason="already_in_progress")
            raise
        except Exception:
            _LOGGER.exception("Unexpected exception")
            return self.async_abort(reason="unknown")

        legacy_entry = await self._async_adopt_legacy_entry_by_mac(
            discovered_mac=info["mac_address"],
            discovered_host=user_input[CONF_IP_ADDRESS],
        )
        if legacy_entry is not None:
            return self.async_abort(reason="already_configured")

        self._abort_if_unique_id_configured(
            updates={CONF_IP_ADDRESS: user_input[CONF_IP_ADDRESS]}
        )
        self._discovered_user_input = user_input
        self._discovered_title = info["title"]
        self._discovered_mac = info["mac_address"]

        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovered AVE webserver before creating the entry."""
        if (
            self._discovered_user_input is None
            or self._discovered_title is None
            or self._discovered_mac is None
        ):
            return self.async_abort(reason="unknown")

        if user_input is not None:
            return await self.async_step_zeroconf_configure()

        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "ip_address": self._discovered_user_input[CONF_IP_ADDRESS],
                "mac_address": self._discovered_mac,
            },
        )

    async def async_step_zeroconf_configure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a discovered AVE webserver with manual options."""
        if self._discovered_user_input is None:
            return self.async_abort(reason="unknown")

        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_IP_ADDRESS: user_input[CONF_IP_ADDRESS]}
            )
            try:
                info = await self.validate_input(user_input, require_mac_address=True)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except MacAddressNotFound:
                errors["base"] = "not_ave_webserver"
            except data_entry_flow.AbortFlow as err:
                if err.reason == "already_in_progress":
                    return self.async_abort(reason="already_in_progress")
                raise
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="zeroconf_configure",
            data_schema=_build_step_user_data_schema(self._discovered_user_input),
            errors=errors,
        )

    async def _async_adopt_legacy_entry_by_mac(
        self, discovered_mac: str, discovered_host: str
    ) -> Any | None:
        """Adopt legacy entries missing unique_id if their MAC matches."""
        for entry in self._async_current_entries():
            if entry.unique_id:
                continue

            entry_data = dict(entry.data)
            entry_host = entry_data.get(CONF_IP_ADDRESS)
            if not entry_host or not isinstance(entry_host, str):
                continue

            webserver = AveWebServer(
                settings_data=MappingProxyType(entry_data), hass=self.hass
            )
            legacy_mac = await webserver.tryget_mac_address()

            if not legacy_mac:
                continue

            if format_mac(legacy_mac) != discovered_mac:
                continue

            entry_data[CONF_IP_ADDRESS] = discovered_host
            self.hass.config_entries.async_update_entry(
                entry,
                data=entry_data,
                title=f"AVE webserver {discovered_mac}",
                unique_id=discovered_mac,
            )
            return entry

        return None

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # self.async_set_unique_id(user_id)
            # self._abort_if_unique_id_mismatch()
            try:
                await self.validate_input(user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates=user_input,
                )

        current = self._get_reconfigure_entry()
        defaults = {**current.data, **current.options}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_step_user_data_schema(defaults),
            errors=errors,
        )

    async def validate_input(
        self, data: dict[str, Any], require_mac_address: bool = False
    ) -> dict[str, Any]:
        """Validate the user input allows us to connect.

        Data has the keys from STEP_USER_DATA_SCHEMA
        with values provided by the user.
        """
        webserver = AveWebServer(settings_data=MappingProxyType(data), hass=self.hass)
        resp_code, _resp_content = await webserver.get_device_list_bridge()
        if resp_code == 900:
            raise CannotConnect
        if resp_code != 200:
            _LOGGER.error("AVE dominaplus: Cannot connect to the web server")
            raise CannotConnect

        mac_address: str = await self._configure_unique_id(webserver)
        if require_mac_address and not mac_address:
            raise MacAddressNotFound
        return {
            "title": f"AVE webserver {mac_address}",
            "mac_address": mac_address,
        }

    async def _configure_unique_id(self, webserver: AveWebServer) -> str:
        mac_address: str | None = await webserver.tryget_mac_address()
        if mac_address is None:
            mac_address = ""
        else:
            mac_address = format_mac(mac_address)
            await self.async_set_unique_id(mac_address)
        return mac_address


class OptionsFlowHandler(OptionsFlow):
    """Handle options for AVE dominaplus — lets the user pick alarm areas by name."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Store the config entry."""
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show area selection if areas have been discovered, text fallback otherwise."""
        webserver: AveWebServer | None = self._entry.runtime_data
        antitheft_areas = []
        if webserver is not None:
            if not webserver.raw_ldi:
                # LDI not yet populated — request a fresh one and wait briefly
                try:
                    webserver.ldi_done.clear()
                    await webserver.send_ws_command("LDI")
                    await asyncio.wait_for(webserver.ldi_done.wait(), 5.0)
                except (TimeoutError, Exception):
                    _LOGGER.warning("Timed out waiting for LDI response in options flow")
            antitheft_areas = [
                d for d in webserver.raw_ldi
                if d["device_type"] == AVE_FAMILY_ANTITHEFT_AREA
            ]
            _LOGGER.debug(
                "Options flow: raw_ldi has %d entries, %d antitheft areas (type %d)",
                len(webserver.raw_ldi),
                len(antitheft_areas),
                AVE_FAMILY_ANTITHEFT_AREA,
            )

        if antitheft_areas:
            return await self._async_step_with_areas(user_input, antitheft_areas)
        return await self._async_step_no_areas(user_input)

    async def _async_step_with_areas(
        self,
        user_input: dict[str, Any] | None,
        areas: list[dict],
    ) -> ConfigFlowResult:
        """Show a multi-select with real area names."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    "arm_away_areas": ",".join(user_input.get("arm_away_areas", [])),
                    "arm_home_areas": ",".join(user_input.get("arm_home_areas", [])),
                },
            )

        # Build select options from discovered areas
        options = [
            {
                "value": str(a["device_id"]),
                "label": a["device_name"] or f"Area {a['device_id']}",
            }
            for a in areas
        ]

        # Pre-select previously saved values
        current_away = _split_areas(
            self._entry.options.get("arm_away_areas", self._entry.data.get("arm_away_areas", ""))
        )
        current_home = _split_areas(
            self._entry.options.get("arm_home_areas", self._entry.data.get("arm_home_areas", ""))
        )

        schema = vol.Schema(
            {
                vol.Optional("arm_away_areas", default=current_away): SelectSelector(
                    SelectSelectorConfig(options=options, multiple=True)
                ),
                vol.Optional("arm_home_areas", default=current_home): SelectSelector(
                    SelectSelectorConfig(options=options, multiple=True)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def _async_step_no_areas(
        self, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Fallback text input when no areas have been discovered yet."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    "arm_away_areas": user_input.get("arm_away_areas", ""),
                    "arm_home_areas": user_input.get("arm_home_areas", ""),
                },
            )

        current_away = self._entry.options.get(
            "arm_away_areas", self._entry.data.get("arm_away_areas", "")
        )
        current_home = self._entry.options.get(
            "arm_home_areas", self._entry.data.get("arm_home_areas", "")
        )

        schema = vol.Schema(
            {
                vol.Optional("arm_away_areas", default=current_away): str,
                vol.Optional("arm_home_areas", default=current_home): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


def _split_areas(value: str) -> list[str]:
    """Split a comma-separated area string into a list of stripped strings."""
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class MacAddressNotFound(HomeAssistantError):
    """Error to indicate discovered host is not an AVE webserver."""
