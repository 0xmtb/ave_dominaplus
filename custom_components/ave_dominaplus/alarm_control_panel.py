"""Alarm control panel platform for AVE dominaplus integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import BRAND_PREFIX
from .web_server import AveWebServer

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    _hass: HomeAssistant | None,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AVE dominaplus alarm control panel."""
    webserver: AveWebServer = entry.runtime_data
    if not webserver:
        _LOGGER.error("AVE dominaplus: Web server not initialized")
        raise ConfigEntryNotReady("Can't reach webserver")

    if not webserver.settings.antitheft_pin:
        return

    panel = AveAlarmPanel(webserver=webserver)
    webserver.alarm_panel = panel
    await webserver.set_async_add_alarm_entities(async_add_entities)
    await webserver.set_update_alarm(update_alarm)
    async_add_entities([panel])

    if not webserver.settings.arm_away_areas or not webserver.settings.arm_home_areas:
        persistent_notification.async_create(
            webserver.hass,
            (
                "Le aree da inserire non sono state configurate.\n\n"
                "Vai su **Impostazioni → Dispositivi e servizi → AVE dominaplus** "
                "e clicca su **Configura** per selezionare le aree per le modalità "
                "Fuori casa e In casa."
            ),
            title="AVE Allarme: configurazione aree necessaria",
            notification_id="ave_alarm_areas_not_configured",
        )
    else:
        persistent_notification.async_dismiss(
            webserver.hass,
            notification_id="ave_alarm_areas_not_configured",
        )


def update_alarm(
    server: AveWebServer,
    family: int,
    area_id: int,
    status: int,
    name: str | None = None,
) -> None:
    """Forward an area state update to the alarm panel entity."""
    if server.alarm_panel is not None and status >= 0:
        server.alarm_panel.update_area_state(area_id, status)


class AveAlarmPanel(AlarmControlPanelEntity):
    """Single alarm panel representing the entire AVE antitheft system.

    ARM_AWAY arms the areas configured in arm_away_areas (set in integration options).
    ARM_HOME arms the areas configured in arm_home_areas — typically a subset
    (e.g. perimeter only, excluding motion sensors) for use while at home.

    State is derived from real-time X|A push messages:
      - TRIGGERED  if any known area is in alarm
      - DISARMED   if all known areas are clear
      - ARMED_AWAY / ARMED_HOME based on the last arm command issued

    The PIN is stored in the config entry (set once during integration setup/reconfigure)
    and used silently — HA will not prompt the user on arm/disarm.
    """

    _attr_should_poll = False
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_HOME
    )
    _attr_code_arm_required = False
    _attr_available = False  # unknown until first X|A push message

    def __init__(self, webserver: AveWebServer) -> None:
        """Initialize the alarm panel."""
        self._webserver = webserver
        self.hass = webserver.hass

        # area_id -> 0 (disarmed) | 1 (armed) | 2 (triggered)
        self._area_states: dict[int, int] = {}

        # Tracks last arm command to distinguish ARMED_AWAY from ARMED_HOME
        # since AVE push messages don't carry this information.
        self._last_arm_mode: str = "disarm"

        self._attr_alarm_state = AlarmControlPanelState.DISARMED
        self._unique_id = f"ave_alarm_panel_{webserver.mac_address}"

    # ------------------------------------------------------------------
    # HA entity properties
    # ------------------------------------------------------------------

    @property
    def unique_id(self) -> str:
        """Return the unique ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the entity name."""
        return f"{BRAND_PREFIX} alarm"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "area_states": self._area_states,
            "arm_away_areas": self._webserver.settings.arm_away_areas,
            "arm_home_areas": self._webserver.settings.arm_home_areas,
            "AVE webserver MAC": self._webserver.mac_address,
        }

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Disarm all areas."""
        if await self._webserver.antitheft_disarm(0, code):
            self._last_arm_mode = "disarm"
            self._attr_available = True
            self._attr_alarm_state = AlarmControlPanelState.DISARMED
            self.async_write_ha_state()

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Arm areas configured for ARM_AWAY."""
        areas = self._webserver.settings.arm_away_areas
        if not areas:
            _LOGGER.error("arm_away_areas not configured — cannot arm")
            return
        bitmask = sum(1 << (a - 1) for a in areas)
        if await self._webserver.antitheft_arm(bitmask, code):
            self._last_arm_mode = "away"
            self._attr_available = True
            self._attr_alarm_state = AlarmControlPanelState.ARMED_AWAY
            self.async_write_ha_state()

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Arm areas configured for ARM_HOME (partial/perimeter arm)."""
        areas = self._webserver.settings.arm_home_areas
        if not areas:
            _LOGGER.error("arm_home_areas not configured — cannot arm")
            return
        bitmask = sum(1 << (a - 1) for a in areas)
        if await self._webserver.antitheft_arm(bitmask, code):
            self._last_arm_mode = "home"
            self._attr_available = True
            self._attr_alarm_state = AlarmControlPanelState.ARMED_HOME
            self.async_write_ha_state()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def update_area_state(self, area_id: int, status: int) -> None:
        """Receive a per-area status update and recompute overall panel state.

        status: 0 = disarmed, 1 = armed, 2 = triggered
        """
        self._area_states[area_id] = status
        self._attr_available = True
        self._recompute_state()
        self.async_write_ha_state()

    def _recompute_state(self) -> None:
        """Derive panel state from individual area states.

        Priority:
          1. TRIGGERED  — if any area is in alarm (overrides everything)
          2. DISARMED   — if all areas are clear
          3. ARMED_HOME / ARMED_AWAY — based on last arm command issued
        """
        if not self._area_states:
            return
        if any(s == 2 for s in self._area_states.values()):
            self._attr_alarm_state = AlarmControlPanelState.TRIGGERED
        elif all(s == 0 for s in self._area_states.values()):
            self._attr_alarm_state = AlarmControlPanelState.DISARMED
        elif self._last_arm_mode == "home":
            self._attr_alarm_state = AlarmControlPanelState.ARMED_HOME
        else:
            self._attr_alarm_state = AlarmControlPanelState.ARMED_AWAY
