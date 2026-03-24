"""AVE Dominaplus thermostat datatypes."""


class AveThermostatProperties:
    """Store thermostat data."""

    def __init__(self) -> None:
        """Initialize thermostat properties."""
        self.device_id: int = -1
        self.device_name: str = ""
        self.device_response: str = ""
        self.fan_level: int = -1
        self.configuration: str = ""
        self.offset: float | None = None
        self.season: str = ""
        self.temperature: float = 0.0
        self.mode: str = ""
        self.set_point: float | None = None
        self.forced_mode: int = 0
        self.local_off: int | None = None

    @staticmethod
    def from_wts(
        parameters: list[str], records: list[list[str]]
    ) -> "AveThermostatProperties":
        """Create thermostat properties from WTS data.

        Args:
            parameters: List of parameter strings.
            records: List of record lists.

        Returns:
            AveThermostatProperties instance populated with WTS data.

        """

        def get_record_value(index: int) -> str | None:
            if len(records) > 0 and len(records[0]) > index:
                return records[0][index]
            return None

        if parameters is None or len(parameters) == 0:
            raise ValueError("Parameters list is empty or None")
        if not parameters[0].isdigit():
            raise ValueError("First parameter must be a valid device ID")

        props = AveThermostatProperties()
        props.device_id = int(parameters[0])
        props.device_name = parameters[0] if len(parameters) > 0 else ""
        props.device_response = get_record_value(0) or ""
        fan_level_str = get_record_value(1)
        props.fan_level = int(fan_level_str) if fan_level_str is not None else -1
        props.configuration = get_record_value(2) or ""
        offset_str = get_record_value(3)
        props.offset = int(offset_str) / 10 if offset_str is not None else None
        props.season = get_record_value(4) or ""
        temperature_str = get_record_value(5)
        props.temperature = (
            int(temperature_str) / 10 if temperature_str is not None else 0.0
        )
        forced_mode_record = get_record_value(8) or "0"
        props.mode = (
            "1F" if int(forced_mode_record) == 1 else (get_record_value(6) or "")
        )
        set_point_str = get_record_value(7)
        props.set_point = int(set_point_str) / 10 if set_point_str is not None else None
        forced_mode_str = get_record_value(8)
        props.forced_mode = int(forced_mode_str) if forced_mode_str is not None else 0
        local_off_str = get_record_value(9)
        props.local_off = int(local_off_str) if local_off_str is not None else None
        return props
