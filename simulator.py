import datetime
import random

from models import ADCSMode, TelemetryFrame


class SatelliteSimulator:
    def __init__(self, satellite_id: str = "SAT-01"):
        self.satellite_id = satellite_id
        self.battery_voltage = 28.0
        self.obc_temperature = 44.0
        self.adcs_mode = ADCSMode.NOMINAL
        self.comms_signal_strength = -99.0
        self._running = False

    def generate_frame(self) -> TelemetryFrame:
        # Apply random-walk drift to each parameter
        self.battery_voltage += random.uniform(-0.3, 0.2)
        self.battery_voltage = max(20.0, min(32.0, self.battery_voltage))

        self.obc_temperature += random.uniform(-0.5, 0.6)
        self.obc_temperature = max(-10.0, min(60.0, self.obc_temperature))

        self.comms_signal_strength += random.uniform(-2.0, 2.0)
        self.comms_signal_strength = max(-120.0, min(-50.0, self.comms_signal_strength))

        return TelemetryFrame(
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            satellite_id=self.satellite_id,
            battery_voltage=round(self.battery_voltage, 2),
            obc_temperature=round(self.obc_temperature, 2),
            adcs_mode=self.adcs_mode,
            comms_signal_strength=round(self.comms_signal_strength, 2),
        )

    def stop(self):
        self._running = False

    def command(self, action: str) -> bool:
        # Execute a command and reset the relevant parameter to nominal
        if action == "reset_battery_controller":
            self.battery_voltage = 28.0
            return True
        elif action == "activate_heater":
            self.obc_temperature = 25.0
            return True
        elif action == "switch_adcs_nominal":
            self.adcs_mode = ADCSMode.NOMINAL
            return True
        elif action == "reset_comms":
            self.comms_signal_strength = -80.0
            return True
        elif action == "power_cycle_obc":
            self.obc_temperature = 22.0
            self.battery_voltage = 27.5
            return True
        return False