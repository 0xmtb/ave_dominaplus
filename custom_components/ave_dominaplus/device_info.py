"""Helpers for Home Assistant device registry metadata."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo

from .const import (
    AVE_FAMILY_ANTITHEFT_AREA,
    AVE_FAMILY_DIMMER,
    AVE_FAMILY_MOTION_SENSOR,
    AVE_FAMILY_ONOFFLIGHTS,
    AVE_FAMILY_SCENARIO,
    AVE_FAMILY_SHUTTER_HUNG,
    AVE_FAMILY_SHUTTER_ROLLING,
    AVE_FAMILY_SHUTTER_SLIDING,
    AVE_FAMILY_THERMOSTAT,
    DOMAIN,
)
from .web_server import AveWebServer

_GROUP_LIGHTING = "lighting"
_GROUP_COVERS = "covers"
_GROUP_ANTITHEFT_SENSORS = "antitheft_sensors"
_GROUP_ANTITHEFT_AREAS = "antitheft_areas"
_GROUP_SCENARIOS = "scenarios"

_FAMILY_TO_GROUP: dict[int, str] = {
    AVE_FAMILY_ONOFFLIGHTS: _GROUP_LIGHTING,
    AVE_FAMILY_DIMMER: _GROUP_LIGHTING,
    AVE_FAMILY_SHUTTER_ROLLING: _GROUP_COVERS,
    AVE_FAMILY_SHUTTER_SLIDING: _GROUP_COVERS,
    AVE_FAMILY_SHUTTER_HUNG: _GROUP_COVERS,
    AVE_FAMILY_MOTION_SENSOR: _GROUP_ANTITHEFT_SENSORS,
    AVE_FAMILY_ANTITHEFT_AREA: _GROUP_ANTITHEFT_AREAS,
    AVE_FAMILY_SCENARIO: _GROUP_SCENARIOS,
}

_GROUP_MODELS: dict[str, str] = {
    _GROUP_LIGHTING: "AVE dominaplus lighting",
    _GROUP_COVERS: "AVE dominaplus covers",
    _GROUP_ANTITHEFT_SENSORS: "AVE dominaplus antitheft sensors",
    _GROUP_ANTITHEFT_AREAS: "AVE dominaplus antitheft areas",
    _GROUP_SCENARIOS: "AVE dominaplus scenarios",
}

_GROUP_NAMES: dict[str, str] = {
    _GROUP_LIGHTING: "Dominaplus Lighting",
    _GROUP_COVERS: "Dominaplus Covers",
    _GROUP_ANTITHEFT_SENSORS: "Dominaplus Antitheft Sensors",
    _GROUP_ANTITHEFT_AREAS: "Dominaplus Antitheft Areas",
    _GROUP_SCENARIOS: "Dominaplus Scenarios",
}


def _hub_identifier(server: AveWebServer) -> str:
    """Build a stable hub identifier for the device registry."""
    if server.mac_address:
        return server.mac_address.lower()
    if server.config_entry_unique_id:
        return server.config_entry_unique_id.lower()
    if server.config_entry_id:
        return server.config_entry_id
    return server.settings.host


def _hub_device_identifier(server: AveWebServer) -> tuple[str, str]:
    """Return the DeviceInfo identifier tuple for the integration hub."""
    return (DOMAIN, f"hub_{_hub_identifier(server)}")


def _endpoint_model(family: int) -> str:
    """Return an endpoint model label based on AVE family."""
    if family == AVE_FAMILY_THERMOSTAT:
        return "AVE dominaplus thermostat"
    group = _FAMILY_TO_GROUP.get(family)
    if group:
        return _GROUP_MODELS[group]
    return f"AVE dominaplus endpoint family {family}"


def _endpoint_group_key(family: int, ave_device_id: int) -> str:
    """Return stable grouping key for endpoint devices under the hub."""
    if family == AVE_FAMILY_SCENARIO:
        return f"scenario_{ave_device_id}"
    group = _FAMILY_TO_GROUP.get(family)
    if group:
        return group
    if family == AVE_FAMILY_THERMOSTAT:
        return f"thermostat_{ave_device_id}"
    return f"family_{family}_{ave_device_id}"


def _clean_ave_device_name(ave_name: str | None) -> str | None:
    """Normalize AVE-provided names for registry device labels."""
    if not ave_name:
        return None
    clean_name = ave_name.strip()
    if clean_name.lower().endswith(" offset"):
        clean_name = clean_name[:-7].strip()
    return clean_name or None


def _thermostat_device_name(ave_device_id: int, ave_name: str | None) -> str:
    """Build thermostat device name from AVE name or fallback device id."""
    clean_name = _clean_ave_device_name(ave_name)
    if not clean_name:
        return f"Thermostat {ave_device_id}"
    if clean_name.lower().startswith("thermostat "):
        return clean_name
    return f"Thermostat {clean_name}"


def _scenario_device_name(ave_device_id: int, ave_name: str | None) -> str:
    """Build scenario device name from AVE name or fallback device id."""
    clean_name = _clean_ave_device_name(ave_name)
    if not clean_name:
        return f"Scenario {ave_device_id}"
    if clean_name.lower().startswith("scenario "):
        return clean_name
    return f"Scenario {clean_name}"


def _endpoint_name(family: int, ave_device_id: int, ave_name: str | None) -> str:
    """Return a stable endpoint device name."""
    if family == AVE_FAMILY_THERMOSTAT:
        return _thermostat_device_name(ave_device_id, ave_name)
    if family == AVE_FAMILY_SCENARIO:
        return _scenario_device_name(ave_device_id, ave_name)
    group = _FAMILY_TO_GROUP.get(family)
    if group:
        return _GROUP_NAMES[group]
    return f"Dominaplus Device Family {family}"


def build_hub_device_info(server: AveWebServer) -> DeviceInfo:
    """Return device_info for the AVE hub.

    Keep this stable to avoid changing existing entity IDs/friendly names.
    """
    connections = set()
    if server.mac_address:
        connections.add((CONNECTION_NETWORK_MAC, server.mac_address.lower()))

    return DeviceInfo(
        identifiers={_hub_device_identifier(server)},
        connections=connections,
        manufacturer="AVE",
        model="AVE dominaplus webserver",
        name="Dominaplus Hub",
        configuration_url=f"http://{server.settings.host}",
    )


def build_endpoint_device_info(
    server: AveWebServer,
    family: int,
    ave_device_id: int,
    *,
    ave_name: str | None = None,
) -> DeviceInfo:
    """Return device_info for a child endpoint routed through the hub.

    Device identifiers include the hub identifier to avoid collisions across hubs.
    """
    group_key = _endpoint_group_key(family, ave_device_id)
    endpoint_identifier = (
        DOMAIN,
        f"endpoint_{_hub_identifier(server)}_{group_key}",
    )

    return DeviceInfo(
        identifiers={endpoint_identifier},
        manufacturer="AVE",
        model=_endpoint_model(family),
        name=_endpoint_name(family, ave_device_id, ave_name),
        via_device=_hub_device_identifier(server),
        configuration_url=f"http://{server.settings.host}",
    )


def sync_device_registry_name(
    hass: HomeAssistant | None,
    device_info: DeviceInfo,
    *,
    identifiers: set[tuple[str, str]] | None = None,
    device_registry_getter: Callable[[HomeAssistant], Any] | None = None,
) -> None:
    """Sync registry device name from device_info unless user customized it."""
    if hass is None:
        return

    resolved_identifiers = identifiers or device_info.get("identifiers")
    if not resolved_identifiers:
        return

    get_registry = device_registry_getter or dr.async_get
    device_registry = get_registry(hass)
    device_entry = device_registry.async_get_device(identifiers=resolved_identifiers)
    if device_entry is None:
        return

    # Respect user-chosen device names from the HA UI.
    if device_entry.name_by_user is not None:
        return

    resolved_name = device_info.get("name")
    if resolved_name and device_entry.name != resolved_name:
        device_registry.async_update_device(
            device_id=device_entry.id,
            name=resolved_name,
        )
