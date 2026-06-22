import asyncio
import datetime
import json

from models import (
    Procedure,
    ProcedureOutcome,
    ProcedureStepResult,
    StepOutcome,
)
from utils import resource_path

class ProcedureEngine:
    def __init__(self, config_path: str = "config/procedures.json"):
        self.procedures = self._load_procedures(resource_path(config_path))
        self.history: list[ProcedureOutcome] = []

    def _load_procedures(self, config_path: str) -> dict[str, Procedure]:
        with open(config_path) as f:
            data = json.load(f)
        return {p["name"]: Procedure(**p) for p in data["procedures"]}

    def get_procedure(self, name: str):
        return self.procedures.get(name)
    
    async def execute(self, procedure_name: str, command_handler) -> ProcedureOutcome:
        procedure = self.procedures[procedure_name]
        started_at = datetime.datetime.now(datetime.timezone.utc)
        step_outcomes = []

        for step in procedure.steps:
            outcome = await self._execute_step(step, command_handler)
            step_outcomes.append(outcome)
            if outcome.result != ProcedureStepResult.SUCCESS:
                break

        completed_at = datetime.datetime.now(datetime.timezone.utc)
        success = all(
            o.result == ProcedureStepResult.SUCCESS for o in step_outcomes
        )

        result = ProcedureOutcome(
            procedure_name=procedure_name,
            started_at=started_at,
            completed_at=completed_at,
            step_outcomes=step_outcomes,
            success=success,
        )
        self.history.append(result)
        return result

    async def _execute_step(self, step, command_handler) -> StepOutcome:
        timestamp = datetime.datetime.now(datetime.timezone.utc)
        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, command_handler, step.action),
                timeout=step.timeout_seconds,
            )
            if result:
                return StepOutcome(
                    step_name=step.name,
                    result=ProcedureStepResult.SUCCESS,
                    message=f"Action '{step.action}' completed successfully",
                    timestamp=timestamp,
                )
            else:
                return StepOutcome(
                    step_name=step.name,
                    result=ProcedureStepResult.FAILURE,
                    message=f"Action '{step.action}' returned failure",
                    timestamp=timestamp,
                )
        except asyncio.TimeoutError:
            return StepOutcome(
                step_name=step.name,
                result=ProcedureStepResult.TIMEOUT,
                message=f"Action '{step.action}' timed out after {step.timeout_seconds}s",
                timestamp=timestamp,
            )