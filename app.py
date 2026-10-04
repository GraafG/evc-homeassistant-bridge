"""
EVC Charging Station Monitor - Web Server
Real-time status monitoring via direct API calls
Exposes REST API for Home Assistant integration
"""

import uuid
import logging
import threading
import time
from datetime import datetime
from flask import Flask, render_template, jsonify
from config import STATIONS, API_CONFIG, SERVER_CONFIG
from evc_api import EVCClient

app = Flask(__name__)
logger = logging.getLogger(__name__)

# Cache for station data
cache = {
    "stations": [],
    "timestamp": None,
    "last_fetch": None,
    "last_error": None,
    "refreshing": False,
}
cache_lock = threading.Lock()
refresh_lock = threading.Lock()
stop_event = threading.Event()
_api_client = None


def get_api_client() -> EVCClient:
    """Create the API client lazily so the web app can report config errors."""
    global _api_client
    if _api_client is None:
        _api_client = EVCClient(API_CONFIG)
    return _api_client


def get_cache_snapshot() -> dict:
    """Return a consistent copy of the cache for request handlers."""
    with cache_lock:
        return {**cache, "stations": list(cache["stations"])}


def parse_station_data(data: dict, station: dict) -> dict:
    """Parse raw API data into display format"""
    if "error" in data:
        return {
            "qr_code": station["qr_code"],
            "config_name": station["name"],
            "error": data["error"]
        }
    
    # Extract operator name (can be string or object)
    operator = data.get("operator")
    if isinstance(operator, dict):
        provider = operator.get("name", "Unknown")
    else:
        provider = operator or "Unknown"
    
    # Parse EVSE/connector info
    evses = []
    overall_status = "UNKNOWN"
    
    for evse in data.get("evses", []):
        evse_status = evse.get("status", "UNKNOWN")
        if overall_status == "UNKNOWN":
            overall_status = evse_status
        elif evse_status == "AVAILABLE":
            overall_status = "AVAILABLE"
        
        connectors = []
        for conn in evse.get("connectors", []):
            power_kw = float(conn.get("maxElectricPower", 0)) / 1000
            connectors.append({
                "connector_id": conn.get("id"),
                "type": conn.get("standard"),
                "power_type": conn.get("powerType"),
                "max_power": f"{power_kw:.1f}",
                "status": evse_status
            })
        
        evses.append({
            "evse_id": evse.get("evseId"),
            "status": evse_status,
            "connectors": connectors
        })
    
    return {
        "qr_code": station["qr_code"],
        "config_name": station["name"],
        "location_name": data.get("name"),
        "address": data.get("address") or data.get("name"),
        "postal_code": data.get("postalCode"),
        "city": data.get("city"),
        "provider": provider,
        "status": overall_status,
        "connectors": evses,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }


def fetch_all_stations(client: EVCClient | None = None) -> list:
    """Fetch status for all configured stations"""
    results = []
    device_id = str(uuid.uuid4())
    client = client or get_api_client()
    
    for station in STATIONS:
        data = client.get_station_status(station["qr_code"], device_id)
        parsed = parse_station_data(data, station)
        results.append(parsed)
    
    return results


def _perform_refresh() -> None:
    """Refresh cache state after the caller has acquired the refresh lock."""
    try:
        stations = fetch_all_stations()
        now = datetime.now().astimezone()
        with cache_lock:
            cache.update(
                stations=stations,
                timestamp=now.isoformat(),
                last_fetch=time.time(),
                last_error=None,
            )
        logger.info("Refreshed %d stations", len(stations))
    except Exception as exc:
        logger.exception("Station refresh failed")
        with cache_lock:
            cache["last_error"] = str(exc)
    finally:
        with cache_lock:
            cache["refreshing"] = False
        refresh_lock.release()


def refresh_cache(blocking: bool = True) -> bool:
    """Start a refresh unless one is already running."""
    if not refresh_lock.acquire(blocking=False):
        return False

    with cache_lock:
        cache["refreshing"] = True

    if blocking:
        _perform_refresh()
    else:
        threading.Thread(target=_perform_refresh, daemon=True).start()
    return True


def background_refresh():
    """Background thread to refresh data periodically"""
    while not stop_event.is_set():
        refresh_cache()
        stop_event.wait(SERVER_CONFIG["refresh_interval"])


# =============================================================================
# WEB UI ROUTES
# =============================================================================

@app.route("/")
def index():
    """Serve the main page"""
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    """Return cached station status (for web UI)"""
    snapshot = get_cache_snapshot()
    return jsonify({
        "success": True,
        "stations": snapshot["stations"],
        "last_update": snapshot["timestamp"],
        "refreshing": snapshot["refreshing"],
        "error": snapshot["last_error"],
    })


@app.post("/api/refresh")
def api_refresh():
    """Schedule a non-blocking refresh for the web UI."""
    started = refresh_cache(blocking=False)
    return jsonify({
        "success": True,
        "started": started,
        "message": "Refresh started" if started else "Refresh already in progress",
    }), 202


# =============================================================================
# HOME ASSISTANT API ENDPOINTS
# =============================================================================

@app.route("/api/v1/stations")
def ha_all_stations():
    """
    Get all stations - Home Assistant REST sensor friendly
    Returns flat list with all station data
    """
    snapshot = get_cache_snapshot()
    return jsonify({
        "stations": snapshot["stations"],
        "count": len(snapshot["stations"]),
        "last_update": snapshot["timestamp"],
        "refreshing": snapshot["refreshing"],
        "error": snapshot["last_error"],
    })


@app.route("/api/v1/station/<qr_code>")
def ha_single_station(qr_code):
    """
    Get single station by QR code
    Example: /api/v1/station/YOUR-CODE*1
    
    Home Assistant config:
      sensor:
        - platform: rest
          resource: http://YOUR_IP:5000/api/v1/station/YOUR-CODE*1
          name: "Charger 1"
          value_template: "{{ value_json.status }}"
          json_attributes:
            - qr_code
            - address
            - provider
            - evse_id
            - connector_type
            - max_power_kw
    """
    # Input validation: QR codes should be alphanumeric with dashes and asterisks
    import re
    if not re.match(r'^[A-Za-z0-9\-\*]+$', qr_code):
        return jsonify({"error": "Invalid QR code format"}), 400
    
    if len(qr_code) > 50:
        return jsonify({"error": "QR code too long"}), 400
    
    snapshot = get_cache_snapshot()
    stations = snapshot["stations"]
    
    for station in stations:
        if station.get("qr_code") == qr_code:
            # Flatten for easy Home Assistant parsing
            evses = station.get("connectors", [])
            first_evse = evses[0] if evses else {}
            first_conn = first_evse.get("connectors", [{}])[0] if first_evse.get("connectors") else {}
            
            return jsonify({
                "qr_code": station.get("qr_code"),
                "name": station.get("config_name"),
                "status": station.get("status", "UNKNOWN"),
                "address": station.get("address"),
                "city": station.get("city"),
                "provider": station.get("provider"),
                "evse_id": first_evse.get("evse_id"),
                "evse_status": first_evse.get("status"),
                "connector_type": first_conn.get("type"),
                "power_type": first_conn.get("power_type"),
                "max_power_kw": first_conn.get("max_power"),
                "last_update": snapshot["timestamp"],
                "available": station.get("status") == "AVAILABLE"
            })
    
    return jsonify({"error": "Station not found"}), 404


@app.route("/api/v1/summary")
def ha_summary():
    """
    Summary endpoint for Home Assistant
    Great for a single sensor showing overall availability
    
    Home Assistant config example (text sensor):
      sensor:
        - platform: rest
          resource: http://YOUR_IP:5000/api/v1/summary
          name: "EVC Chargers Status"
          value_template: "{{ value_json.availability_text }}"
          json_attributes:
            - available
            - occupied  
            - total
            - any_available
            - all_available
    
    Or for a numeric sensor (available count):
      sensor:
        - platform: rest
          resource: http://YOUR_IP:5000/api/v1/summary
          name: "EVC Chargers Available"
          value_template: "{{ value_json.available }}"
          unit_of_measurement: "stations"
    """
    snapshot = get_cache_snapshot()
    stations = snapshot["stations"]
    
    available = sum(1 for s in stations if s.get("status") == "AVAILABLE")
    occupied = sum(1 for s in stations if s.get("status") in ["OCCUPIED", "CHARGING"])
    
    return jsonify({
        "total": len(stations),
        "available": available,
        "occupied": occupied,
        "unavailable": len(stations) - available - occupied,
        "all_available": bool(stations) and available == len(stations),
        "any_available": available > 0,
        "availability_text": f"{available}/{len(stations)} available",
        "stations": [
            {
                "qr_code": s.get("qr_code"),
                "name": s.get("config_name"),
                "status": s.get("status"),
                "available": s.get("status") == "AVAILABLE"
            }
            for s in stations
        ],
        "last_update": snapshot["timestamp"],
        "refreshing": snapshot["refreshing"],
        "error": snapshot["last_error"],
    })


@app.route("/health")
def health():
    """Health check endpoint for Docker/monitoring"""
    snapshot = get_cache_snapshot()
    age = time.time() - snapshot["last_fetch"] if snapshot["last_fetch"] else None
    stale_after = SERVER_CONFIG["refresh_interval"] * 2
    if snapshot["last_fetch"] is None:
        status = "starting"
    elif snapshot["last_error"] or (age is not None and age > stale_after):
        status = "degraded"
    else:
        status = "healthy"
    
    return jsonify({
        "status": status,
        "stations_configured": len(STATIONS),
        "stations_cached": len(snapshot["stations"]),
        "last_update": snapshot["timestamp"],
        "cache_age_seconds": round(age, 1) if age is not None else None,
        "refreshing": snapshot["refreshing"],
        "error": snapshot["last_error"],
    })


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, SERVER_CONFIG["log_level"], logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    print("=" * 60)
    print("  EVC Charging Station Monitor")
    print("  Home Assistant Ready")
    print("=" * 60)
    print()
    print(f"  Monitoring {len(STATIONS)} station(s):")
    for s in STATIONS:
        print(f"    • {s['name']} ({s['qr_code']})")
    print()
    print("  Endpoints:")
    print(f"    Web UI:     http://localhost:{SERVER_CONFIG['port']}/")
    print(f"    All:        http://localhost:{SERVER_CONFIG['port']}/api/v1/stations")
    print(f"    Summary:    http://localhost:{SERVER_CONFIG['port']}/api/v1/summary")
    print(f"    Station:    http://localhost:{SERVER_CONFIG['port']}/api/v1/station/<qr_code>")
    print(f"    Health:     http://localhost:{SERVER_CONFIG['port']}/health")
    print()
    print(f"  Auto-refresh: every {SERVER_CONFIG.get('refresh_interval', 300)//60} minutes")
    print("=" * 60)
    
    # Start background refresh thread (fetches data after server starts)
    print("\nStarting background data fetcher...")
    refresh_thread = threading.Thread(target=background_refresh, daemon=True)
    refresh_thread.start()
    
    print("Server starting...\n")
    from waitress import serve

    serve(app, host=SERVER_CONFIG["host"], port=SERVER_CONFIG["port"])
