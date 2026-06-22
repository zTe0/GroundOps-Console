import time
import sys
from simulator import SatelliteSimulator

def run_simulation_console():
    sim = SatelliteSimulator()
    print("=" * 85)
    print("  SATELLITE GROUND OPS AUTOMATION ENGINE - REAL-TIME TELEMETRY STREAM")
    print("  Units calibrated to SI (Volts, °C) & RF (dBm). Press Ctrl+C to terminate.")
    print("=" * 85)
    
    try:
        while True:
            frame = sim.generate_frame()
            # Prints using the custom __str__ method we defined on the TelemetryFrame
            print(frame)
            sys.stdout.flush()
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n" + "=" * 85)
        print("  Simulation stream paused by operator. Exiting console session safely.")
        print("=" * 85)

if __name__ == "__main__":
    run_simulation_console()
