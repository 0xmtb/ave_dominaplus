"""Web server settings for AVE Domina Plus integration."""

from types import MappingProxyType
from typing import Any


def _parse_areas(value: str) -> list[int]:
    """Parse a comma-separated string of area numbers into a list of ints.

    Values are the sequential area numbers as returned by the AVE LDI (1, 2, 3, ...).
    The arm command converts them to bitmask: area N -> bit (N-1) -> 1 << (N-1).
    """
    if not value:
        return []
    return [int(x.strip()) for x in value.split(",") if x.strip().isdigit()]


class AveWebServerSettings:
    """Web server settings class."""

    host: str
    get_entity_names: bool
    fetch_sensor_areas: bool
    fetch_sensors: bool
    fetch_lights: bool
    fetch_covers: bool
    fetch_scenarios: bool
    fetch_thermostats: bool
    antitheft_pin: str
    arm_away_areas: list[int]
    arm_home_areas: list[int]

    def __init__(self) -> None:
        """Initialize the settings."""
        self.host = ""
        self.get_entity_names = True
        self.fetch_sensor_areas = False
        self.fetch_sensors = False
        self.fetch_lights = True
        self.fetch_covers = True
        self.fetch_scenarios = True
        self.fetch_thermostats = True
        self.on_off_lights_as_switch = True
        self.antitheft_pin = ""
        self.arm_away_areas = []
        self.arm_home_areas = []

    @staticmethod
    def from_config_entry_options(
        options: MappingProxyType[str, Any],
    ) -> "AveWebServerSettings":
        """Create settings from config entry options."""
        settings = AveWebServerSettings()
        settings.host = options["ip_address"]
        settings.get_entity_names = options.get("get_entities_names", True)
        settings.fetch_sensor_areas = options.get("fetch_sensor_areas", False)
        settings.fetch_sensors = options.get("fetch_sensors", False)
        settings.fetch_lights = options.get("fetch_lights", True)
        settings.fetch_covers = options.get("fetch_covers", True)
        settings.fetch_scenarios = options.get("fetch_scenarios", True)
        settings.fetch_thermostats = options.get("fetch_thermostats", True)
        settings.on_off_lights_as_switch = options.get("on_off_lights_as_switch", True)
        settings.antitheft_pin = options.get("antitheft_pin", "")
        settings.arm_away_areas = _parse_areas(options.get("arm_away_areas", ""))
        settings.arm_home_areas = _parse_areas(options.get("arm_home_areas", ""))
        return settings
