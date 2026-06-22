import json

from models import Alert, AlertSeverity, TelemetryFrame    

from utils import resource_path

class TelemetryMonitor:
    def __init__(self, config_path: str = "config/alarm_limits.json"):
        self.limits = self._load_limits(config_path)
        self.alerts: list[Alert] = []
        self.active_alerts: dict[str, Alert] = {}

    def _load_limits(self, config_path: str) -> dict:
        with open(resource_path(config_path)) as f:
            return json.load(f)

    def evaluate(self, frame: TelemetryFrame) -> list[Alert]:
        new_alerts = []
        for param_name, limits in self.limits.items():
            value = getattr(frame, param_name, None)
            if value is None or isinstance(value, str):
                continue

            alert_key = f"{frame.satellite_id}:{param_name}"
            severity = self._check_limits(value, limits)

            if severity != AlertSeverity.NOMINAL:
                alert = Alert(
                    timestamp=frame.timestamp,
                    satellite_id=frame.satellite_id,
                    parameter=param_name,
                    value=value,
                    severity=severity,
                    message=f"{param_name} is {severity.value}: {value}",
                )
                self.alerts.append(alert)
                self.active_alerts[alert_key] = alert
                new_alerts.append(alert)
            else:
                if alert_key in self.active_alerts:
                    self.active_alerts[alert_key].resolved = True
                    del self.active_alerts[alert_key]

        return new_alerts

    def _check_limits(self, value: float, limits: dict) -> AlertSeverity:
        if "critical_low" in limits and value <= limits["critical_low"]:
            return AlertSeverity.CRITICAL
        if "critical_high" in limits and value >= limits["critical_high"]:
            return AlertSeverity.CRITICAL
        if "warning_low" in limits and value <= limits["warning_low"]:
            return AlertSeverity.WARNING
        if "warning_high" in limits and value >= limits["warning_high"]:
            return AlertSeverity.WARNING
        return AlertSeverity.NOMINAL