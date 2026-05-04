# Known Issues

## Open

### 503 Service Unavailable from istaonline.no during authentication (2026-05-04)

**Symptom**

`async_setup_entry` failed with:

```
requests.exceptions.HTTPError: 503 Server Error: Service Unavailable for url:
  https://www.istaonline.no/Login.aspx?ReturnUrl=%2FTenant.aspx
```

In the original report this was masked by an `AttributeError: module 'requests'
has no attribute 'SSLError'` — fixed separately by switching to
`requests.exceptions.SSLError`.

**Timing**

Single failure at `2026-05-04 22:00:23 UTC` (≈ `00:00:23` local Norwegian
time). One setup attempt only — no other `ista_no` log lines around it.

**What we don't know**

We don't yet know whether the 503 is:

1. Scheduled maintenance / app-pool recycle on istaonline.no — the midnight
   timing is suspicious.
2. The Cloudflare/WAF tier returning a 503 instead of its usual HTTP-200
   "Validation request" challenge page (CLAUDE.md notes the WAF is
   aggressive).
3. A short-lived origin outage.

**Mitigations already in place**

- Setup now raises `ConfigEntryNotReady` on `IstaConnectionError` /
  `IstaResponseError`, so HA will retry with backoff instead of marking the
  entry permanently failed.
- `_sync_request` retries once after 5s on 502/503/504, so a single blip
  doesn't surface to the user at all.
- `_sync_request` now logs the response body + `Server` / `cf-ray` headers
  on any HTTP error, so the next 503 will tell us whether it's a Cloudflare
  WAF block or an origin outage.

**To investigate**

- [ ] Reproduce: hit `https://www.istaonline.no/Login.aspx` from a few
      different IPs and times-of-day. Capture status code + response body for
      a 503 to confirm whether it's WAF-tagged (look for `cf-ray`,
      `Server: cloudflare`, or Telerik error markup).
- [ ] Once root cause is known, document the maintenance/WAF behavior in
      `docs/ista-api.md`.
