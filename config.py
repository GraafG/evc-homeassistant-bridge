"""
EVC Charging Station Monitor - Configuration
Reads from environment variables for Docker, falls back to defaults for local dev
"""

import os


def positive_int_env(name, default):
    """Read a positive integer from the environment with a clear error."""
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value

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
        if not item.strip():
            continue
        if ":" in item:
            qr_code, name = item.split(":", 1)
            qr_code = qr_code.strip()
            name = name.strip() or qr_code
        else:
            # Just QR code, use it as name too
            qr_code = item.strip()
            name = qr_code
        if qr_code:
            stations.append({"qr_code": qr_code, "name": name})
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
    "api_key": os.environ.get("EVC_API_KEY"),
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
    "port": positive_int_env("PORT", 5000),
    "refresh_interval": positive_int_env("REFRESH_INTERVAL", 300),
    "log_level": os.environ.get("LOG_LEVEL", "INFO").upper(),
}
