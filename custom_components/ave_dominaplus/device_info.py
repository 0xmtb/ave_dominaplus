"""Helpers for Home Assistant device registry metadata."""

from __future__ import annotations

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
    if family in {AVE_FAMILY_ONOFFLIGHTS, AVE_FAMILY_DIMMER}:
        return "AVE dominaplus lighting"
    if family in {
        AVE_FAMILY_SHUTTER_ROLLING,
        AVE_FAMILY_SHUTTER_SLIDING,
        AVE_FAMILY_SHUTTER_HUNG,
    }:
        return "AVE dominaplus covers"
    if family == AVE_FAMILY_THERMOSTAT:
        return "AVE dominaplus thermostat"
    if family == AVE_FAMILY_MOTION_SENSOR:
        return "AVE dominaplus antitheft sensors"
    if family == AVE_FAMILY_ANTITHEFT_AREA:
        return "AVE dominaplus antitheft areas"
    if family == AVE_FAMILY_SCENARIO:
        return "AVE dominaplus scenarios"
    return f"AVE dominaplus endpoint family {family}"


def _endpoint_group_key(family: int, ave_device_id: int) -> str:
    """Return stable grouping key for endpoint devices under the hub."""
    if family in {AVE_FAMILY_ONOFFLIGHTS, AVE_FAMILY_DIMMER}:
        return "lighting"
    if family in {
        AVE_FAMILY_SHUTTER_ROLLING,
        AVE_FAMILY_SHUTTER_SLIDING,
        AVE_FAMILY_SHUTTER_HUNG,
    }:
        return "covers"
    if family == AVE_FAMILY_MOTION_SENSOR:
        return "antitheft_sensors"
    if family == AVE_FAMILY_ANTITHEFT_AREA:
        return "antitheft_areas"
    if family == AVE_FAMILY_SCENARIO:
        return "scenarios"
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


def _endpoint_name(family: int, ave_device_id: int, ave_name: str | None) -> str:
    """Return a stable endpoint device name."""
    if family == AVE_FAMILY_THERMOSTAT:
        clean_name = _clean_ave_device_name(ave_name)
        if clean_name:
            if clean_name.lower().startswith("thermostat "):
                return clean_name
            return f"Thermostat {clean_name}"
        return f"Thermostat {ave_device_id}"
    if family in {AVE_FAMILY_ONOFFLIGHTS, AVE_FAMILY_DIMMER}:
        return "Dominaplus Lighting"
    if family in {
        AVE_FAMILY_SHUTTER_ROLLING,
        AVE_FAMILY_SHUTTER_SLIDING,
        AVE_FAMILY_SHUTTER_HUNG,
    }:
        return "Dominaplus Covers"
    if family == AVE_FAMILY_MOTION_SENSOR:
        return "Dominaplus Antitheft Sensors"
    if family == AVE_FAMILY_ANTITHEFT_AREA:
        return "Dominaplus Antitheft Areas"
    if family == AVE_FAMILY_SCENARIO:
        return "Dominaplus Scenarios"
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
