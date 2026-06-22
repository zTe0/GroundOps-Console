from simulator import SatelliteSimulator
from monitor import TelemetryMonitor
from resolvers import ResolverSystem

sim = SatelliteSimulator()
sim.battery_voltage = 23.0
frame = sim.generate_frame()

mon = TelemetryMonitor()
res = ResolverSystem()
alerts = mon.evaluate(frame)

for a in alerts:
    proc = res.match(a)
    if proc:
        print(f'Alert: {a.parameter} {a.severity.value} -> Procedure: {proc}')