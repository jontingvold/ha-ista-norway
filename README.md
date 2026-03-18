# Ista Norway — Home Assistant Integration

Custom Home Assistant integration that fetches daily meter readings from [istaonline.no](https://www.istaonline.no):

- **Energy** (kWh) — district heating
- **Hot water** (m³)
- **Cold water** (m³)

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS
2. Install "Ista Norway"
3. Restart Home Assistant

### Manual

1. Copy `custom_components/ista_no/` to your Home Assistant `custom_components/` directory
2. Restart Home Assistant

## Configuration

Configuration is done entirely through the UI — no YAML needed.

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Ista Norway**
3. Enter your **Username** (e.g. 51361444287) and **Password** (the same credentials you use on istaonline.no)
4. Click Submit

## Sensors

The integration auto-discovers all meters on your istaonline.no account and creates one sensor per meter:

| Sensor | Device Class | State Class | Unit |
|---|---|---|---|
| `sensor.ista_no_{meter_id}` (Energy) | `energy` | `total_increasing` | kWh |
| `sensor.ista_no_{meter_id}` (Hot Water) | `water` | `total_increasing` | m³ |
| `sensor.ista_no_{meter_id}` (Cold Water) | `water` | `total_increasing` | m³ |

Each sensor reports the **cumulative meter reading** (Avlesning) and includes these attributes:
- `daily_consumption` — consumption since last reading
- `last_reading_date` — date of the most recent reading
- `meter_type` — ENERGY, HW, or CW
- `meter_id` — the meter number

## Polling Schedule

The integration uses a smart polling schedule:
- **4:00 AM** — daily check for new data
- **Hourly** — if today's data hasn't arrived yet, polls every hour until it does
- **Sleep** — once today's data is received, sleeps until next 4:00 AM

Meter readings on istaonline.no are typically updated once daily.

## Historical Data

On first setup, the integration automatically imports **all available historical data** into Home Assistant's long-term statistics. This means your Energy Dashboard graphs will be populated with historical readings from day one.

## Energy Dashboard

The energy sensor (`ENERGY` type) is compatible with the Home Assistant Energy Dashboard:

1. Go to **Settings → Dashboards → Energy**
2. Add the energy sensor under **Individual devices** (district heating)
3. Water sensors can be added under **Water consumption**

## Limitations

- **No 2FA support** — if your account has two-factor authentication enabled, the integration cannot log in. Use the "remember this device" option on istaonline.no from your browser first.
- **Cloud polling** — data comes from istaonline.no's web interface, not a local API.
- **Rate limiting** — istaonline.no has aggressive rate limiting. The polling schedule is conservative to avoid triggering it.

## Development

See [CLAUDE.md](CLAUDE.md) for architecture details and development notes.

### Running integration tests

The tests exercise the real istaonline.no API (no mocking):

```bash
cp .env.example .env   # Fill in real credentials
pip install requests beautifulsoup4 python-dotenv pytest pytest-asyncio
pytest tests/ -v
```

## API Documentation

See [docs/ista-api.md](docs/ista-api.md) for details on the istaonline.no scraping flow (redacted).
