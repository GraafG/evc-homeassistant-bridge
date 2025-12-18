"""
EVC Charging Station Monitor - Web Server
Real-time status monitoring via direct API calls
Exposes REST API for Home Assistant integration
"""

import requests
import uuid
import threading
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from config import STATIONS, API_CONFIG, SERVER_CONFIG

app = Flask(__name__)

# Cache for station data
cache = {
    "stations": [],
    "timestamp": None,
    "last_fetch": None
}


def get_headers():
    """Get API headers with API key"""
    headers = API_CONFIG["headers"].copy()
    headers["x-api-key"] = API_CONFIG["api_key"]
    return headers


def get_guest_token(device_id: str) -> str:
    """Get a fresh guest token from the API"""
    url = f"{API_CONFIG['base_url']}/user/guestLogin"
    
    payload = {
        "deviceId": device_id,
        "locale": API_CONFIG["locale"],
        "platform": API_CONFIG["platform"],
        "serviceName": API_CONFIG["service_name"],
        "serviceVersion": API_CONFIG["service_version"],
        "appVersion": API_CONFIG["app_version"],
        "appIdentifier": API_CONFIG["app_identifier"],
        "webUrl": "directpayment.evc-net.com"
    }
    
    try:
        response = requests.post(url, headers=get_headers(), json=payload, timeout=10)
        if response.ok:
            return response.json().get("data", {}).get("token")
    except requests.RequestException:
        pass
    return None


def get_station_status(qr_code: str, device_id: str) -> dict:
    """Fetch status for a single charging station"""
    
    # Get fresh token (tokens are single-use)
    token = get_guest_token(device_id)
    if not token:
        return {"error": "Failed to get authentication token"}
    
    url = f"{API_CONFIG['base_url']}/location/getLocationDetails"
    
    payload = {
        "locationId": "",
        "channelId": "",
        "qrCode": qr_code,
        "evseId": "",
        "token": token,
        "referenceGeoBounds": {},
        "deviceId": device_id,
        "locale": API_CONFIG["locale"],
        "platform": API_CONFIG["platform"],
        "serviceName": API_CONFIG["service_name"],
        "serviceVersion": API_CONFIG["service_version"],
        "appIdentifier": API_CONFIG["app_identifier"],
        "appVersion": API_CONFIG["app_version"]
    }
    
    try:
        response = requests.post(url, headers=get_headers(), json=payload, timeout=10)
        if response.ok:
            return response.json().get("data", {})
        return {"error": f"API error: {response.status_code}"}
    except requests.RequestException as e:
        return {"error": str(e)}


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


def fetch_all_stations() -> list:
    """Fetch status for all configured stations"""
    results = []
    device_id = str(uuid.uuid4())
    
    for station in STATIONS:
        data = get_station_status(station["qr_code"], device_id)
        parsed = parse_station_data(data, station)
        results.append(parsed)
    
    return results


def background_refresh():
    """Background thread to refresh data periodically"""
    while True:
        try:
            stations = fetch_all_stations()
            cache["stations"] = stations
            cache["timestamp"] = datetime.now().isoformat()
            cache["last_fetch"] = time.time()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Refreshed {len(stations)} stations")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Refresh error: {e}")
        
        # Sleep for configured interval (default 5 minutes)
        time.sleep(SERVER_CONFIG.get("refresh_interval", 300))


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
    return jsonify({
        "success": True,
        "stations": cache["stations"] or [],
        "last_update": cache["timestamp"]
    })


@app.route("/api/refresh")
def api_refresh():
    """Refresh station data and return results (for web UI)"""
    try:
        stations = fetch_all_stations()
        cache["stations"] = stations
        cache["timestamp"] = datetime.now().isoformat()
        
        return jsonify({
            "success": True,
            "stations": stations,
            "last_update": cache["timestamp"]
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =============================================================================
# HOME ASSISTANT API ENDPOINTS
# =============================================================================

@app.route("/api/v1/stations")
def ha_all_stations():
    """
    Get all stations - Home Assistant REST sensor friendly
    Returns flat list with all station data
    """
    return jsonify({
        "stations": cache["stations"] or [],
        "count": len(cache["stations"] or []),
        "last_update": cache["timestamp"]
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
    
    stations = cache.get("stations") or []
    
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
                "last_update": cache["timestamp"],
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
    stations = cache.get("stations") or []
    
    available = sum(1 for s in stations if s.get("status") == "AVAILABLE")
    occupied = sum(1 for s in stations if s.get("status") in ["OCCUPIED", "CHARGING"])
    
    return jsonify({
        "total": len(stations),
        "available": available,
        "occupied": occupied,
        "unavailable": len(stations) - available - occupied,
        "all_available": available == len(stations),
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
        "last_update": cache["timestamp"]
    })


@app.route("/health")
def health():
    """Health check endpoint for Docker/monitoring"""
    age = time.time() - cache.get("last_fetch", 0) if cache.get("last_fetch") else None
    
    return jsonify({
        "status": "healthy",
        "stations_configured": len(STATIONS),
        "stations_cached": len(cache.get("stations") or []),
        "last_update": cache["timestamp"],
        "cache_age_seconds": round(age, 1) if age else None
    })


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
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
    app.run(
        host=SERVER_CONFIG["host"],
        port=SERVER_CONFIG["port"]
    )
