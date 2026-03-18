# CLAUDE.md — Ista Norway HA Integration

## Project Overview

Custom Home Assistant integration that fetches daily meter readings (energy kWh, hot water m³, cold water m³) from [istaonline.no](https://www.istaonline.no). All config via HA UI — no hardcoded credentials.

## Repository Structure

```
custom_components/ista_no/   # The HA integration
  __init__.py                # Setup/teardown
  manifest.json              # Integration metadata
  config_flow.py             # UI config (username/password)
  const.py                   # URLs, field names, constants
  api.py                     # IstaClient — scraping via requests + asyncio.to_thread
  coordinator.py             # DataUpdateCoordinator + historical import
  sensor.py                  # Sensor entities per meter
  strings.json               # UI strings (source of truth)
  translations/              # en.json, nb.json, nn.json
docs/ista-api.md             # Public API documentation (redacted)
tests/                       # Integration tests (real API, needs .env)
private/                     # Git-ignored: original script, example queries with real data
```

## Key Architecture Decisions

- **`requests` via `asyncio.to_thread`** (not `aiohttp`): istaonline.no uses ASP.NET Telerik WebForms with strict form encoding validation. `aiohttp` encodes form data differently enough to trigger Telerik's EventValidation errors. `requests` works correctly.
- **Smart polling schedule**: Check at 4am daily. If no data for today, poll hourly until it arrives. Once today's data is received, sleep until next 4am.
- **Historical import**: On first setup, imports all available years into HA long-term statistics via `async_import_statistics`.

## Credentials & Privacy

- **NEVER commit real credentials.** All user data lives in `private/` (git-ignored) and `.env` (git-ignored).
- Docs use `REDACTED` for usernames/passwords and `XXX` for last 3 digits of meter IDs.
- The `.env` / `.env.example` files are ONLY for running integration tests.

## Testing

```bash
# Offline tests (always safe to run, no network needed)
pytest tests/ -v -k "not LiveAPI"

# Live API tests (needs .env with credentials — see below)
cp .env.example .env   # Fill in real istaonline.no credentials
pip install requests beautifulsoup4 python-dotenv pytest pytest-asyncio
pytest tests/ -v
```

**IMPORTANT: istaonline.no rate-limits aggressively.** The WAF blocks your IP after a few requests in quick succession, returning a "Validation request" challenge page. Live API tests (`TestLiveAPI`) should be run **rarely** — only when validating changes to the scraping logic. Prefer offline tests for day-to-day development. If rate-limited, wait 5+ minutes before retrying.

## Development Notes

- ASP.NET form fields use `$` in names (e.g., `ctl00$mainContent$edtPassword`) — this is normal
- Password must be sent in both the form field AND a `_ClientState` JSON blob
- Fingerprint field accepts static all-zeros value
- CSV uses Norwegian decimal separator (`,` → `.`)
- After switching meter type, the returned HTML must be used as base for the next switch (ViewState chaining)
- The site returns HTTP 200 for errors with error messages in HTML body — `api.py` has `_check_for_errors()` for this

## Naming

- Integration domain: `ista_no`
- Display name: "Ista Norway"
- Data source: istaonline.no
