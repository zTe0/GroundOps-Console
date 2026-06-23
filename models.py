import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ADCSMode(str, Enum):
    NOMINAL = "NOMINAL"
    SAFE = "SAFE"
    DETUMBLE = "DETUMBLE"


class TelemetryFrame(BaseModel):
    timestamp: datetime.datetime
    satellite_id: str
    battery_voltage: float
    obc_temperature: float
    adcs_mode: ADCSMode
    comms_signal_strength: float

    def __str__(self) -> str:
        # Formats the datetime block safely with UTC suffix
        formatted_time = self.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Aligns and appends SI/RF units to each parameter
        return (
            f"[{formatted_time}] {self.satellite_id} | "
            f"Battery: {self.battery_voltage:.2f} V | "
            f"OBC Temp: {self.obc_temperature:.2f} °C | "
            f"ADCS: {self.adcs_mode.value:<8}| "
            f"Comms: {self.comms_signal_strength:.2f} dBm"
        )

class AlertSeverity(str, Enum):
    NOMINAL = "NOMINAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Alert(BaseModel):
    timestamp: datetime.datetime
    satellite_id: str
    parameter: str
    value: float
    severity: AlertSeverity
    message: str
    resolved: bool = False

class ProcedureStepResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    TIMEOUT = "TIMEOUT"


class ProcedureStep(BaseModel):
    name: str
    action: str
    precondition: Optional[str] = None
    timeout_seconds: float = 30.0


class Procedure(BaseModel):
    name: str
    description: str
    steps: list[ProcedureStep]


class StepOutcome(BaseModel):
    step_name: str
    result: ProcedureStepResult
    message: str
    timestamp: datetime.datetime


class ProcedureOutcome(BaseModel):
    procedure_name: str
    started_at: datetime.datetime
    completed_at: datetime.datetime
    step_outcomes: list[StepOutcome]
    success: bool


class ResolverRule(BaseModel):
    name: str
    parameter: str
    severity: AlertSeverity
    procedure_name: str


class AutopilotResult(BaseModel):
    sequence_name: str
    started_at: datetime.datetime
    completed_at: datetime.datetime
    procedure_outcomes: list[ProcedureOutcome]
    all_succeeded: bool