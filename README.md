# EVC Charging Station Monitor

Real-time status monitoring for EVC Network charging stations with Home Assistant integration.

## 🚀 Quick Start

### Docker (Recommended for Home Assistant)

The tracked `.env` contains only non-sensitive station settings. Keep credentials
out of it; supply `EVC_API_KEY` through your shell or deployment secret configuration.

```bash
# Configure the API key separately from the tracked .env
export EVC_API_KEY="YOUR_API_KEY"
# Edit station settings in .env, then build and run
docker-compose up -d

# Or manually
docker build -t evc-monitor .
docker run -d -p 5000:5000 --env-file .env -e EVC_API_KEY --name evc-monitor evc-monitor
```

### Local Development

```powershell
$env:EVC_API_KEY = "YOUR_API_KEY"
pip install -r requirements-dev.txt
python app.py
```

Run the test suite with `python -m pytest`.

## 📡 API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/` | Web UI dashboard |
| `/api/v1/stations` | All stations (JSON) |
| `/api/v1/station/<qr_code>` | Single station details |
| `/api/v1/summary` | Summary with counts |
| `POST /api/refresh` | Start a non-blocking refresh (returns HTTP 202) |
| `/health` | Health check for Docker |

## 🏠 Home Assistant Integration

### Option 1: Summary Sensor (Recommended)

```yaml
# configuration.yaml
sensor:
  - platform: rest
    resource: http://YOUR_IP:5000/api/v1/summary
    name: "EVC Chargers"
    value_template: "{{ value_json.available }}/{{ value_json.total }}"
    unit_of_measurement: "available"
    scan_interval: 300
    json_attributes:
      - available
      - occupied
      - total
      - all_available
      - any_available
      - stations
      - last_update
```

### Option 2: Individual Station Sensors

```yaml
# configuration.yaml
sensor:
  - platform: rest
    resource: http://YOUR_IP:5000/api/v1/station/YOUR-CODE*1
    name: "Charger Station 1"
    value_template: "{{ value_json.status }}"
    scan_interval: 300
    json_attributes:
      - qr_code
      - address
      - city
      - provider
      - evse_id
      - connector_type
      - max_power_kw
      - available
      - last_update

  - platform: rest
    resource: http://YOUR_IP:5000/api/v1/station/YOUR-CODE*2
    name: "Charger Station 2"
    value_template: "{{ value_json.status }}"
    scan_interval: 300
    json_attributes:
      - qr_code
      - address
      - available
```

### Option 3: Binary Sensor for Availability

```yaml
# configuration.yaml
binary_sensor:
  - platform: template
    sensors:
      charger_available:
        friendly_name: "Charger Available"
        value_template: "{{ state_attr('sensor.evc_chargers', 'any_available') }}"
        device_class: plug
```

### Automation Example

```yaml
# automations.yaml
automation:
  - alias: "Notify when charger becomes available"
    trigger:
      - platform: state
        entity_id: sensor.charger_station_1
        to: "AVAILABLE"
    action:
      - service: notify.mobile_app
        data:
          message: "Charger is now available!"
```

## 📊 API Response Examples

### `/api/v1/summary`
```json
{
  "total": 2,
  "available": 1,
  "occupied": 1,
  "unavailable": 0,
  "all_available": false,
  "any_available": true,
  "stations": [
    {"qr_code": "ABCD-1234*1", "name": "Station 1", "status": "AVAILABLE", "available": true},
    {"qr_code": "ABCD-1234*2", "name": "Station 2", "status": "OCCUPIED", "available": false}
  ],
  "last_update": "2025-12-17T20:30:00"
}
```

### `/api/v1/station/ABCD-1234*1`
```json
{
  "qr_code": "ABCD-1234*1",
  "name": "Station 1",
  "status": "AVAILABLE",
  "address": "Example Street 1",
  "city": "Amsterdam",
  "provider": "EVC Network",
  "evse_id": "NLEVCP00000001*1",
  "connector_type": "IEC_62196_T2",
  "power_type": "AC_3_PHASE",
  "max_power_kw": "22.0",
  "available": true,
  "last_update": "2025-12-17T20:30:00"
}
```

## ⚙️ Configuration

Edit station settings in the tracked `.env`; `.env.example` is a configuration
reference. Do not put real API keys, tokens, or passwords in either tracked file.

```dotenv
STATIONS=YOUR-CODE*1:Station 1,YOUR-CODE*2:Station 2
```

Docker Compose reads `.env` automatically. For local Python runs, set environment
variables in your shell; the application does not load `.env` itself.

## 📁 Project Structure

```
├── .env                # Tracked, non-sensitive station defaults
├── app.py              # Main server with API
├── cli.py              # Command-line tool
├── config.py           # Station configuration
├── evc_api.py          # Shared EVC API client
├── templates/
│   └── index.html      # Web UI
├── tests/              # Unit tests
├── Dockerfile          # Docker build
├── docker-compose.yml  # Docker Compose
├── requirements-dev.txt # Development and test dependencies
└── requirements.txt    # Python dependencies
```

## 🔧 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EVC_API_KEY` | Required | API key used by the EVC web application; supply outside tracked `.env` |
| `STATIONS` | Example stations | Comma-separated `QR_CODE:Display Name` entries |
| `TZ` | UTC | Timezone for timestamps |
| `PORT` | `5000` | HTTP server port |
| `REFRESH_INTERVAL` | `300` | Background refresh interval in seconds |
| `LOG_LEVEL` | `INFO` | Python logging level |

## 📝 License

MIT
