import datetime
import json

from models import Alert, ProcedureOutcome, ResolverRule
from utils import resource_path

class ResolverSystem:
    def __init__(self, config_path: str = "config/resolvers.json"):
        self.rules = self._load_rules(resource_path(config_path))
        self.history: list[dict] = []

    def _load_rules(self, config_path: str) -> list[ResolverRule]:
        with open(config_path) as f:
            data = json.load(f)
        return [ResolverRule(**r) for r in data["rules"]]

    def match(self, alert: Alert) -> str | None:
        for rule in self.rules:
            if rule.parameter == alert.parameter and rule.severity == alert.severity:
                return rule.procedure_name
        return None

    def log_action(self, alert: Alert, outcome: ProcedureOutcome):
        self.history.append({
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "alert_parameter": alert.parameter,
            "alert_severity": alert.severity.value,
            "alert_value": alert.value,
            "procedure_executed": outcome.procedure_name,
            "procedure_success": outcome.success,
        })