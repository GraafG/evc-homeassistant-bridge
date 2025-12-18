"""
EVC Charging Station Monitor - Configuration
Reads from environment variables for Docker, falls back to defaults for local dev
"""

import os

# =============================================================================
# CHARGING STATIONS
# =============================================================================
# Can be set via STATIONS env var: "GRDR-0123*1:Station 1,GRDR-0124*1:Station 2"
# Or edit the default list below for local development

def parse_stations_env():
    """Parse STATIONS from environment variable"""
    env_stations = os.environ.get("STATIONS", "")
    if not env_stations:
        return None
    
    stations = []
    for item in env_stations.split(","):
        if ":" in item:
            qr_code, name = item.split(":", 1)
            stations.append({"qr_code": qr_code.strip(), "name": name.strip()})
        else:
            # Just QR code, use it as name too
            stations.append({"qr_code": item.strip(), "name": item.strip()})
    return stations if stations else None

# Try environment first, then fall back to defaults
STATIONS = parse_stations_env() or [
    {
        "qr_code": "GRDR-0123*1",
        "name": "Station 1"
    },
    {
        "qr_code": "GRDR-0124*1", 
        "name": "Station 2"
    },
    # Add more stations:
    # {
    #     "qr_code": "YOUR-CODE*1",
    #     "name": "Your Station Name"
    # },
]

# =============================================================================
# API CONFIGURATION (Don't change unless you know what you're doing)
# =============================================================================

API_CONFIG = {
    "base_url": "https://mobile-gateway.evc-net.com/api/v1",
    "api_key": "dab0e236-94b6-4b5d-a856-7d8773ceb496",
    "headers": {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://directpayment.evc-net.com",
        "referer": "https://directpayment.evc-net.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36",
    },
    "app_identifier": "ECQ-WEB",
    "service_name": "ECQ",
    "service_version": "1.12.1",
    "app_version": "1.12.1",
    "platform": "ECQ-WEB:1.0.0--android-Android 6.0",
    "locale": "en"
}

# =============================================================================
# SERVER SETTINGS
# =============================================================================

SERVER_CONFIG = {
    "host": "0.0.0.0",
    "port": int(os.environ.get("PORT", 5000)),
    "refresh_interval": int(os.environ.get("REFRESH_INTERVAL", 300)),
    "auto_refresh_seconds": int(os.environ.get("REFRESH_INTERVAL", 300))
}
