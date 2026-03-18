# Ista Norway (unofficial)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/jontingvold/ha-ista-norway)](https://github.com/jontingvold/ha-ista-norway/releases)
[![License](https://img.shields.io/github/license/jontingvold/ha-ista-norway)](LICENSE)

Unofficial Home Assistant integration for Ista Norway ([istaonline.no](https://www.istaonline.no) and the Norwegian Ista EcoTrend app). Fetches daily meter readings for energy/heating (fjernvarme) in kWh, hot water in m³, and cold water in m³ — with historical data import and Energy Dashboard support.

---

## About Ista

[Ista](https://www.ista.com) is one of several companies that provide residential heating and water metering services to borettslag (housing cooperatives) and apartment complexes in Norway. If your building uses Ista for sub-metering, you can view your consumption data on [istaonline.no](https://www.istaonline.no) (web portal) or through the Ista EcoTrend mobile app.

This integration fetches data from the **istaonline.no** web portal.

> **Note:** This integration only works with the **Norwegian** Ista service. Ista operates in many countries, but each national company has its own separate online portal and API. There is an existing Home Assistant integration called [ista EcoTrend](https://www.home-assistant.io/integrations/ista_ecotrend/) that works with the German market — this integration is separate and for Norway only.

## Prerequisites

You need a Norwegian Ista Online / Ista EcoTrend account. Use the same username and password as you use on [istaonline.no](https://www.istaonline.no) or in the Ista EcoTrend app.

If you don't have an account, contact your borettslag/housing cooperative or Ista Norway customer service (see footer on [ista.no](https://www.ista.no)).

---

## Installation

### HACS (recommended)

1. Make sure [HACS](https://hacs.xyz) is installed
2. In HACS, go to **Integrations** → click the **three dots** (top right) → **Custom repositories**
3. Add `https://github.com/jontingvold/ha-ista-norway` with category **Integration**
4. Search for **"Ista Norway"** and install it
5. **Restart Home Assistant**

### Manual

1. Download the [latest release](https://github.com/jontingvold/ha-ista-norway/releases)
2. Copy the `custom_components/ista_no/` folder to your Home Assistant `config/custom_components/` directory
3. **Restart Home Assistant**

---

## Configuration

Configuration is done entirely through the UI — no YAML needed.

1. Go to **Settings → Devices & Services**
2. Click **+ Add Integration** (bottom right)
3. Search for **"Ista"**
4. Enter your **Username** (e.g. 51361444287) and **Password**
5. Click **Submit**

The integration will appear under Devices & Services once configured.

## Sensors

The integration auto-discovers all meters on your account and creates one sensor per meter:

| Sensor | Device Class | State Class | Unit |
|---|---|---|---|
| `sensor.ista_no_{meter_id}` (Energy) | `energy` | `total_increasing` | kWh |
| `sensor.ista_no_{meter_id}` (Hot Water) | `water` | `total_increasing` | m³ |
| `sensor.ista_no_{meter_id}` (Cold Water) | `water` | `total_increasing` | m³ |

Each sensor reports the **cumulative meter reading** (Avlesning) and includes these attributes:

| Attribute | Description |
|---|---|
| `daily_consumption` | Consumption since last reading |
| `last_reading_date` | Date of the most recent reading |
| `meter_type` | ENERGY, HW, or CW |
| `meter_id` | The meter number |

## Energy Dashboard

The energy sensor is compatible with the Home Assistant Energy Dashboard:

1. Go to **Settings → Dashboards → Energy**
2. Add the energy sensor under **Individual devices** (district heating / fjernvarme)
3. Water sensors can be added under **Water consumption**

## Historical Data

On first setup, the integration automatically imports **all available historical data** into Home Assistant's long-term statistics. Your Energy Dashboard graphs will be populated with historical readings from day one.

---

## Polling Schedule

The integration uses a smart polling schedule:

| Time | Behavior |
|---|---|
| **4:00 AM** | Daily check for new data |
| **Hourly** | If today's data hasn't arrived yet, polls every hour until it does |
| **Sleep** | Once today's data is received, sleeps until next 4:00 AM |

Meter readings on istaonline.no are typically updated once daily.

## Limitations

- **No 2FA support** — if your account has two-factor authentication enabled, the integration cannot log in. Use the "remember this device" option on istaonline.no from your browser first.
- **Cloud polling** — data comes from istaonline.no's web interface, not a local API.
- **Rate limiting** — istaonline.no has aggressive rate limiting. The polling schedule is conservative to avoid triggering it.

---

## Debug Logging

To enable debug logging, add this to your `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.ista_no: debug
```

## Development

See [CLAUDE.md](CLAUDE.md) for architecture details and development notes.

### Running tests

```bash
# Offline tests (no credentials needed)
pytest tests/ -v -k "not LiveAPI"

# Live API tests (needs .env with credentials)
cp .env.example .env   # Fill in real istaonline.no credentials
pip install requests beautifulsoup4 python-dotenv pytest pytest-asyncio
pytest tests/ -v
```

## API Documentation

See [docs/ista-api.md](docs/ista-api.md) for details on the istaonline.no scraping flow.
