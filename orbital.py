import math
from datetime import datetime, timedelta, timezone
from sgp4.api import Satrec, jday
import httpx

# async def register_custom_satellite(sat_id: str, name: str, norad_id: int) -> bool:
#     """Fetch live TLE for a custom NORAD ID and append it to our in-memory registry."""
#     # Ensure it's not already registered to prevent duplicates
#     if sat_id in SATELLITE_REGISTRY:
#         return True
        
#     live_tle = await fetch_live_tle(norad_id)
#     if not live_tle:
#         return False
        
#     line1, line2 = live_tle
#     # Add to the global registry dictionaries
#     SATELLITE_REGISTRY[sat_id] = {
#         "name": name,
#         "norad_id": norad_id,
#         "tle_line1": line1,
#         "tle_line2": line2
#     }
#     _satellites[sat_id] = Satrec.twoline2rv(line1, line2)
#     return True


def _elevation_angle(sat_lat, sat_lon, sat_alt_km, gs_lat=None, gs_lon=None, gs_alt_km=0.003):
    """Compute elevation angle from custom ground station coordinates (defaults to KSC)."""
    # Use fallback values if custom coords are not provided
    lat_val = gs_lat if gs_lat is not None else GROUND_STATION["lat"]
    lon_val = gs_lon if gs_lon is not None else GROUND_STATION["lon"]
    alt_val = gs_alt_km if gs_alt_km is not None else GROUND_STATION["alt_km"]

    gs_lat_r = math.radians(lat_val)
    gs_lon_r = math.radians(lon_val)
    sat_lat_r = math.radians(sat_lat)
    sat_lon_r = math.radians(sat_lon)
    
    cos_gamma = (
        math.sin(gs_lat_r) * math.sin(sat_lat_r)
        + math.cos(gs_lat_r) * math.cos(sat_lat_r)
        * math.cos(sat_lon_r - gs_lon_r)
    )
    cos_gamma = max(-1.0, min(1.0, cos_gamma))
    gamma = math.acos(cos_gamma)
    
    R = 6378.137
    r_sat = R + sat_alt_km
    r_gs = R + alt_val
    elev = math.atan2(
        r_sat * cos_gamma - r_gs, r_sat * math.sin(gamma)
    )
    return math.degrees(elev)

def get_passes(sat_id, hours=24, gs_lat=None, gs_lon=None, gs_alt_km=None):
    """Predict passes over a dynamically provided observer location."""
    if sat_id not in _satellites:
        return []
    now = datetime.now(timezone.utc)
    passes = []
    in_pass = False
    current_pass = {}
    max_elev = 0.0
    steps = int(hours * 3600 / 30)
    
    for i in range(steps):
        dt = now + timedelta(seconds=i * 30)
        pos = get_satellite_position(sat_id, dt)
        if not pos:
            continue
        # Pass the dynamic coordinates down to the elevation calculator
        elev = _elevation_angle(
            pos["lat"], pos["lon"], pos["alt_km"], 
            gs_lat, gs_lon, gs_alt_km
        )
        if elev > 10 and not in_pass:
            in_pass = True
            current_pass = {"aos_time": dt.isoformat(), "max_elevation": elev}
            max_elev = elev
        elif elev > 10 and in_pass:
            if elev > max_elev:
                max_elev = elev
                current_pass["max_elevation"] = elev
        elif elev <= 10 and in_pass:
            in_pass = False
            current_pass["los_time"] = dt.isoformat()
            aos_dt = datetime.fromisoformat(current_pass["aos_time"])
            current_pass["duration_seconds"] = (dt - aos_dt).total_seconds()
            passes.append(current_pass)
    return passes


# === Satellite Registry ===
# 5 LEO satellites defined by name, NORAD ID, and TLE lines
SATELLITE_REGISTRY = {
    "iss": {
        "name": "ISS (ZARYA)",
        "norad_id": 25544,
        "tle_line1": "1 25544U 98067A   26171.15661001  .00008669  00000+0  16345-3 0  9997",
        "tle_line2": "2 25544  51.6329 285.3962 0004555 207.7610 152.3136 15.49327998572210",
    },
    "noaa18": {
        "name": "NOAA 18",
        "norad_id": 28654,
        "tle_line1": "1 28654U 05018A   24045.48572069  .00000193  00000-0  13419-3 0  9990",
        "tle_line2": "2 28654  99.0300 100.5268 0013614 276.5217  83.4404 14.12629527980123",
    },
    "noaa19": {
        "name": "NOAA 19",
        "norad_id": 33591,
        "tle_line1": "1 33591U 09005A   24045.53458028  .00000195  00000-0  13578-3 0  9999",
        "tle_line2": "2 33591  99.1900  58.7160 0013987 150.1234 210.0789 14.12452344787234",
    },
    "starlink1007": {
        "name": "STARLINK-1007",
        "norad_id": 44713,
        "tle_line1": "1 44713U 19074A   24045.50000000  .00001234  00000-0  87654-4 0  9991",
        "tle_line2": "2 44713  53.0500 234.5600 0001234  90.1234 270.0012 15.06390000200001",
    },
    "starlink1808": {
        "name": "STARLINK-1808",
        "norad_id": 46161,
        "tle_line1": "1 46161U 20055A   24045.50000000  .00001500  00000-0  91234-4 0  9998",
        "tle_line2": "2 46161  53.0500 120.3400 0001500  45.6789 314.4321 15.06380000150001",
    },
}

# Ground station: Kennedy Space Center, Florida
GROUND_STATION = {
    "name": "Kennedy Space Center",
    "lat": 28.5721,
    "lon": -80.6480,
    "alt_km": 0.003,
}

# Load TLE data into Satrec propagator objects on module import
_satellites = {}
for sat_id, sat_data in SATELLITE_REGISTRY.items():
    _satellites[sat_id] = Satrec.twoline2rv(
        sat_data["tle_line1"], sat_data["tle_line2"]
    )


def _gmst(jd, fr):
    """Compute Greenwich Mean Sidereal Time in radians.
    Correctly accounts for both the precession offset and the Earth's daily rotation fraction.
    """
    # Julian centuries from J2000.0
    t = (jd - 2451545.0 + fr) / 36525.0
    
    # GMST in seconds of time (precession offset)
    g = 67310.54841 + (8640184.812866 + (0.093104 + (-6.2e-6) * t) * t) * t
    
    # Add the primary Earth rotation terms:
    # (jd % 1.0) is the fraction of the day since noon (0.5 at midnight)
    # fr is the fractional time since midnight
    # g / 86400.0 is the precession offset scaled to a fraction of a day
    theta = ((jd % 1.0) + fr + g / 86400.0) % 1.0 * 2.0 * math.pi
    return theta



def teme_to_ecef(pos_teme, dt):
    """Rotate TEME position vector to ECEF using GMST angle.
    Applies rot_z(-theta) per Vallado AIAA 2006-6753.
    """
    # Get Julian date components for the given datetime
    jd, fr = jday(
        dt.year, dt.month, dt.day,
        dt.hour, dt.minute, dt.second + dt.microsecond / 1e6
    )
    theta = _gmst(jd, fr)
    # Apply rotation matrix Rz(-theta) to convert TEME -> ECEF
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    x_teme, y_teme, z_teme = pos_teme
    x_ecef = cos_t * x_teme + sin_t * y_teme
    y_ecef = -sin_t * x_teme + cos_t * y_teme
    z_ecef = z_teme
    return (x_ecef, y_ecef, z_ecef)

def ecef_to_geodetic(x, y, z):
    """Convert ECEF coordinates (km) to geodetic lat/lon/alt.
    Uses WGS84 ellipsoid with iterative latitude refinement.
    """
    # WGS84 parameters
    a = 6378.137  # semi-major axis in km
    f = 1.0 / 298.257223563  # flattening
    b = a * (1.0 - f)  # semi-minor axis
    e2 = 1.0 - (b * b) / (a * a)  # eccentricity squared
    # Longitude is straightforward
    lon = math.atan2(y, x)
    # Distance from z-axis
    p = math.sqrt(x * x + y * y)
    # Initial latitude estimate
    lat = math.atan2(z, p * (1.0 - e2))
    # Iterative refinement (converges in 3-5 iterations)
    for _ in range(10):
        sin_lat = math.sin(lat)
        N = a / math.sqrt(1.0 - e2 * sin_lat * sin_lat)
        lat = math.atan2(z + e2 * N * sin_lat, p)
    # Compute altitude
    sin_lat = math.sin(lat)
    N = a / math.sqrt(1.0 - e2 * sin_lat * sin_lat)
    alt_km = p / math.cos(lat) - N
    return (math.degrees(lat), math.degrees(lon), alt_km)

def get_satellite_position(sat_id, dt):
    """Get satellite lat/lon/alt_km at a given UTC datetime."""
    if sat_id not in _satellites:
        return None
    sat = _satellites[sat_id]
    # Convert datetime to Julian date components
    jd, fr = jday(
        dt.year, dt.month, dt.day,
        dt.hour, dt.minute, dt.second + dt.microsecond / 1e6
    )
    # Propagate orbit to get TEME position (km) and velocity (km/s)
    e, pos_teme, vel_teme = sat.sgp4(jd, fr)
    if e != 0:
        return None
    # Convert TEME -> ECEF -> geodetic
    pos_ecef = teme_to_ecef(pos_teme, dt)
    lat, lon, alt_km = ecef_to_geodetic(*pos_ecef)
    return {"lat": lat, "lon": lon, "alt_km": alt_km}

def get_orbital_period_minutes(sat_id: str) -> float:
    """Calculate the satellite's exact orbital period in minutes using Kozai mean motion."""
    if sat_id not in _satellites:
        return 90.0  # Fallback to standard 90 minutes if not found
        
    sat = _satellites[sat_id]
    
    # sat.no_kozai represents mean motion in radians per minute
    if sat.no_kozai <= 0:
        return 90.0  # Safe safety guard
        
    # Period (T) = 2 * pi / n_0
    period_mins = (2.0 * math.pi) / sat.no_kozai
    return period_mins

# def get_ground_track(sat_id, minutes=90, interval_s=60):
#     """Generate ground track points for the next N minutes."""
#     now = datetime.now(timezone.utc)
#     track = []
#     for i in range(0, minutes * 60, interval_s):
#         dt = now + timedelta(seconds=i)
#         pos = get_satellite_position(sat_id, dt)
#         if pos:
#             track.append({"time": dt.isoformat(), **pos})
#     return track

def get_ground_track(sat_id, interval_s=60):
    """Generate ground track points tracing exactly one full orbital period."""
    # 1. Fetch the exact physical orbit duration
    period_mins = get_orbital_period_minutes(sat_id)
    total_seconds = int(period_mins * 60)
    
    print(f"[SYSTEM] Generating ground track for {sat_id}: Period is {period_mins:.2f} minutes.")
    
    now = datetime.now(timezone.utc)
    track = []
    
    # 2. Iterate for exactly one complete revolution around Earth
    for i in range(0, total_seconds, interval_s):
        dt = now + timedelta(seconds=i)
        pos = get_satellite_position(sat_id, dt)
        if pos:
            track.append({"time": dt.isoformat(), **pos})
            
    return track

# def _elevation_angle(sat_lat, sat_lon, sat_alt_km):
#     """Compute elevation angle (degrees) from ground station to satellite.
#     Uses spherical Earth approximation for the geometry.
#     """
#     gs_lat = math.radians(GROUND_STATION["lat"])
#     gs_lon = math.radians(GROUND_STATION["lon"])
#     sat_lat_r = math.radians(sat_lat)
#     sat_lon_r = math.radians(sat_lon)
#     # Central angle between ground station and sub-satellite point
#     cos_gamma = (
#         math.sin(gs_lat) * math.sin(sat_lat_r)
#         + math.cos(gs_lat) * math.cos(sat_lat_r)
#         * math.cos(sat_lon_r - gs_lon)
#     )
#     cos_gamma = max(-1.0, min(1.0, cos_gamma))
#     gamma = math.acos(cos_gamma)
#     # Elevation angle from ground station horizon
#     R = 6378.137
#     r_sat = R + sat_alt_km
#     r_gs = R + GROUND_STATION["alt_km"]
#     elev = math.atan2(
#         r_sat * cos_gamma - r_gs, r_sat * math.sin(gamma)
#     )
#     return math.degrees(elev)


# def get_passes(sat_id, hours=24):
#     """Predict passes over ground station in the next N hours.
#     Steps through time at 30s increments detecting AOS/LOS.
#     """
#     if sat_id not in _satellites:
#         return []
#     now = datetime.now(timezone.utc)
#     passes = []
#     in_pass = False
#     current_pass = {}
#     max_elev = 0.0
#     # Step through time at 30-second increments
#     steps = int(hours * 3600 / 30)
#     for i in range(steps):
#         dt = now + timedelta(seconds=i * 30)
#         pos = get_satellite_position(sat_id, dt)
#         if not pos:
#             continue
#         elev = _elevation_angle(pos["lat"], pos["lon"], pos["alt_km"])
#         if elev > 0 and not in_pass:
#             # Acquisition of Signal (AOS)
#             in_pass = True
#             current_pass = {"aos_time": dt.isoformat(), "max_elevation": elev}
#             max_elev = elev
#         elif elev > 0 and in_pass:
#             # Track maximum elevation during the pass
#             if elev > max_elev:
#                 max_elev = elev
#                 current_pass["max_elevation"] = elev
#         elif elev <= 0 and in_pass:
#             # Loss of Signal (LOS)
#             in_pass = False
#             current_pass["los_time"] = dt.isoformat()
#             aos_dt = datetime.fromisoformat(current_pass["aos_time"])
#             current_pass["duration_seconds"] = (dt - aos_dt).total_seconds()
#             passes.append(current_pass)
#     return passes


async def register_custom_satellite(norad_id: int) -> bool:
    """Fetch live TLE and name from PocketWorld and register it using a schema-tolerant parser."""
    sat_id = f"sat-{norad_id}"
    if sat_id in SATELLITE_REGISTRY:
        return True

    url = f"https://pocketworld.org/api/tle/{norad_id}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5.0)
            if response.status_code != 200:
                print(f"[WARM] PocketWorld returned status {response.status_code} for NORAD {norad_id}")
                return False
                
            data = response.json()
            
            # --- 1. Dynamic Name Discovery ---
            # name = (
            #     data.get("name") or 
            #     data.get("title") or 
            #     data.get("satname") or 
            #     data.get("satellite") or 
            #     f"NORAD {norad_id}"
            # ).strip()

            info = data.get("info")
            name = info.get("satname")
            # print(info)
            # print(name)
            
            # --- 2. Schema-Tolerant TLE Line Extraction ---
            line1 = None
            line2 = None
            
            # Case A: Keys are line1 and line2 (standard)
            if "line1" in data and "line2" in data:
                line1 = data["line1"]
                line2 = data["line2"]
            # Case B: Keys are tle_line1 and tle_line2
            elif "tle_line1" in data and "tle_line2" in data:
                line1 = data["tle_line1"]
                line2 = data["tle_line2"]
            # Case C: Keys are tle1 and tle2
            elif "tle1" in data and "tle2" in data:
                line1 = data["tle1"]
                line2 = data["tle2"]
            # Case D: Single raw string 'tle' containing both lines separated by newline
            elif "tle" in data and isinstance(data["tle"], str):
                lines = data["tle"].splitlines()
                if len(lines) >= 2:
                    # If there's a title line (3-line TLE format), grab the last two
                    line1 = lines[-2]
                    line2 = lines[-1]

            # --- 3. Parse and Instantiate SGP4 ---
            if line1 and line2:
                line1_clean = line1.strip()
                line2_clean = line2.strip()
                
                # Register in memory SATELLITE_REGISTRY
                SATELLITE_REGISTRY[sat_id] = {
                    "name": f"{name} [{norad_id}]",
                    "norad_id": norad_id,
                    "tle_line1": line1_clean,
                    "tle_line2": line2_clean
                }
                
                # Load into SGP4 propagator
                _satellites[sat_id] = Satrec.twoline2rv(line1_clean, line2_clean)
                print(f"[SYSTEM] Successfully registered: {name} (ID: {sat_id})")
                return True
                
            print(f"[ERROR] Could not find valid TLE lines in JSON payload for NORAD {norad_id}: {data}")
            
    except Exception as e:
        print(f"[ERROR] Connection or parsing error for NORAD {norad_id}: {e}")
    return False

