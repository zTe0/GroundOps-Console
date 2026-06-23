import datetime

from models import AutopilotResult, ProcedureOutcome
from procedures import ProcedureEngine


class AutopilotSequencer:
    def __init__(self, procedure_engine: ProcedureEngine):
        self.engine = procedure_engine
        self.history: list[AutopilotResult] = []
        self._running = False

    async def execute_sequence(
        self, sequence_name: str, procedure_names: list[str], command_handler
    ) -> AutopilotResult:
        self._running = True
        started_at = datetime.datetime.now(datetime.timezone.utc)
        outcomes: list[ProcedureOutcome] = []

        for proc_name in procedure_names:
            if not self._running:
                break
            outcome = await self.engine.execute(proc_name, command_handler)
            outcomes.append(outcome)

        completed_at = datetime.datetime.now(datetime.timezone.utc)
        
        # Logical fix: Verify all procedures ran AND all succeeded
        all_succeeded = len(outcomes) == len(procedure_names) and all(o.success for o in outcomes)

        result = AutopilotResult(
            sequence_name=sequence_name,
            started_at=started_at,
            completed_at=completed_at,
            procedure_outcomes=outcomes,
            all_succeeded=all_succeeded,
        )
        self.history.append(result)
        self._running = False
        return result

    def abort(self):
        self._running = False