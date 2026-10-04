"""
EVC Charging Station Monitor - Command Line Interface
Fetch and display station status from the terminal
"""

import uuid
import json
import argparse
from datetime import datetime
from config import STATIONS, API_CONFIG
from evc_api import EVCClient


def format_status(status: str) -> str:
    """Format status with color codes for terminal"""
    colors = {
        "AVAILABLE": "\033[92m",      # Green
        "OCCUPIED": "\033[93m",        # Yellow
        "CHARGING": "\033[93m",        # Yellow
        "OUT_OF_SERVICE": "\033[91m",  # Red
        "UNKNOWN": "\033[90m"          # Gray
    }
    reset = "\033[0m"
    color = colors.get(status, colors["UNKNOWN"])
    return f"{color}{status}{reset}"


def print_station(station: dict, data: dict, verbose: bool = False):
    """Print station status to terminal"""
    print(f"\n{'='*60}")
    print(f"📍 {station['name']} ({station['qr_code']})")
    print(f"{'='*60}")
    
    if "error" in data:
        print(f"  ❌ Error: {data['error']}")
        return
    
    # Location info
    address = data.get("address") or data.get("name", "Unknown")
    city = data.get("city", "")
    if city:
        address = f"{address}, {city}"
    print(f"  📍 {address}")
    
    # Operator
    operator = data.get("operator")
    if isinstance(operator, dict):
        operator = operator.get("name", "Unknown")
    if operator:
        print(f"  🏢 {operator}")
    
    # EVSE/Connectors
    print(f"\n  Charging Points:")
    for evse in data.get("evses", []):
        evse_id = evse.get("evseId", "Unknown")
        status = evse.get("status", "UNKNOWN")
        print(f"    ⚡ {evse_id}: {format_status(status)}")
        
        if verbose:
            for conn in evse.get("connectors", []):
                conn_type = conn.get("standard", "Unknown")
                power = float(conn.get("maxElectricPower", 0)) / 1000
                print(f"       └─ {conn_type} ({power:.1f} kW)")
    
    if verbose:
        print(f"\n  Raw data: {json.dumps(data, indent=2)}")


def main():
    parser = argparse.ArgumentParser(
        description="EVC Charging Station Status Monitor"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed connector information"
    )
    parser.add_argument(
        "-j", "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "-q", "--qr-code",
        type=str,
        help="Fetch a specific station by QR code"
    )
    
    args = parser.parse_args()
    device_id = str(uuid.uuid4())
    try:
        api_client = EVCClient(API_CONFIG)
    except ValueError as exc:
        parser.error(str(exc))
    
    print("\n" + "=" * 60)
    print("  EVC Charging Station Monitor")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Determine which stations to fetch
    if args.qr_code:
        stations = [{"qr_code": args.qr_code, "name": args.qr_code}]
    else:
        stations = STATIONS
    
    results = []
    
    for station in stations:
        print(f"\nFetching {station['name']}...", end=" ", flush=True)
        data = api_client.get_station_status(station["qr_code"], device_id)
        
        if "error" in data:
            print(f"❌ {data['error']}")
        else:
            statuses = [e.get("status", "?") for e in data.get("evses", [])]
            print(f"✓ {', '.join(statuses)}")
        
        results.append({
            "station": station,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })
    
    # Output
    if args.json:
        print("\n" + json.dumps(results, indent=2))
    else:
        for r in results:
            print_station(r["station"], r["data"], verbose=args.verbose)
    
    print(f"\n{'='*60}")
    print(f"  Fetched {len(results)} station(s)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
