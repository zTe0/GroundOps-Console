import asyncio
import time

from autopilot import AutopilotSequencer
from models import AlertSeverity, ProcedureStepResult
from monitor import TelemetryMonitor
from procedures import ProcedureEngine
from resolvers import ResolverSystem
from simulator import SatelliteSimulator


class TestAutopilotEndToEnd:
    """Test-as-you-fly: exercises the full automation chain."""

    def test_autopilot_executes_sequence_successfully(self):
        result = asyncio.run(self._run_sequence_test())
        assert result.all_succeeded is True
        assert len(result.procedure_outcomes) == 3
        for outcome in result.procedure_outcomes:
            assert outcome.success is True

    async def _run_sequence_test(self):
        sim = SatelliteSimulator()
        engine = ProcedureEngine()
        autopilot = AutopilotSequencer(engine)
        return await autopilot.execute_sequence(
            sequence_name="health_check_sequence",
            procedure_names=["battery_recovery", "thermal_protection", "comms_recovery"],
            command_handler=sim.command,
        )
    
    def test_resolver_fires_on_alert(self):
        result = asyncio.run(self._run_resolver_test())
        assert result["alert_detected"] is True
        assert result["procedure_fired"] is True
        assert result["procedure_success"] is True

    async def _run_resolver_test(self):
        sim = SatelliteSimulator()
        monitor = TelemetryMonitor()
        engine = ProcedureEngine()
        resolver = ResolverSystem()
        sim.battery_voltage = 23.0
        frame = sim.generate_frame()
        alerts = monitor.evaluate(frame)
        alert_detected = any(
            a.parameter == "battery_voltage" and a.severity == AlertSeverity.WARNING
            for a in alerts
        )
        procedure_fired = False
        procedure_success = False
        for alert in alerts:
            proc_name = resolver.match(alert)
            if proc_name:
                outcome = await engine.execute(proc_name, sim.command)
                resolver.log_action(alert, outcome)
                procedure_fired = True
                procedure_success = outcome.success
        return {"alert_detected": alert_detected, "procedure_fired": procedure_fired, "procedure_success": procedure_success}

    def test_full_automation_chain(self):
        result = asyncio.run(self._run_full_chain_test())
        assert result["initial_alert"] is True
        assert result["resolver_acted"] is True
        assert result["recovery_confirmed"] is True

    async def _run_full_chain_test(self):
        sim = SatelliteSimulator()
        monitor = TelemetryMonitor()
        engine = ProcedureEngine()
        resolver = ResolverSystem()
        sim.battery_voltage = 21.5
        frame = sim.generate_frame()
        alerts = monitor.evaluate(frame)
        initial_alert = any(
            a.parameter == "battery_voltage" and a.severity == AlertSeverity.CRITICAL
            for a in alerts
        )
        resolver_acted = False
        for alert in alerts:
            proc_name = resolver.match(alert)
            if proc_name:
                outcome = await engine.execute(proc_name, sim.command)
                resolver.log_action(alert, outcome)
                resolver_acted = outcome.success
        recovery_frame = sim.generate_frame()
        recovery_alerts = monitor.evaluate(recovery_frame)
        battery_still_critical = any(
            a.parameter == "battery_voltage" and a.severity == AlertSeverity.CRITICAL
            for a in recovery_alerts
        )
        return {"initial_alert": initial_alert, "resolver_acted": resolver_acted, "recovery_confirmed": not battery_still_critical}

    def test_procedure_timeout_handling(self):
        """Fault injection: slow command handler triggers timeout."""
        result = asyncio.run(self._run_timeout_test())
        assert result.all_succeeded is False
        timeout_found = any(
            step.result == ProcedureStepResult.TIMEOUT
            for outcome in result.procedure_outcomes
            for step in outcome.step_outcomes
        )
        assert timeout_found is True

    async def _run_timeout_test(self):
        sim = SatelliteSimulator()
        engine = ProcedureEngine()
        autopilot = AutopilotSequencer(engine)

        def slow_handler(action: str) -> bool:
            time.sleep(2.0)
            return sim.command(action)

        engine.procedures["battery_recovery"].steps[0].timeout_seconds = 0.5

        return await autopilot.execute_sequence(
            sequence_name="fault_injection_test",
            procedure_names=["battery_recovery"],
            command_handler=slow_handler,
        )
    
    def test_autopilot_abort_mid_sequence(self):
        """Abort signal stops autopilot before completing all procedures."""
        result = asyncio.run(self._run_abort_test())
        assert result.all_succeeded is False
        assert len(result.procedure_outcomes) < 3

    async def _run_abort_test(self):
        sim = SatelliteSimulator()
        engine = ProcedureEngine()
        autopilot = AutopilotSequencer(engine)

        def slow_handler(action: str) -> bool:
            time.sleep(0.3)
            return sim.command(action)

        async def abort_after_delay():
            await asyncio.sleep(0.5)
            autopilot.abort()

        asyncio.create_task(abort_after_delay())

        return await autopilot.execute_sequence(
            sequence_name="abort_test",
            procedure_names=["battery_recovery", "thermal_protection", "comms_recovery"],
            command_handler=slow_handler,
        )

    