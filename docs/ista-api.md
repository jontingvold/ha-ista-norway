# istaonline.no Scraping API Documentation

This documents the HTTP flow for scraping meter readings from `www.istaonline.no`.

## Overview

istaonline.no is an ASP.NET WebForms application. All interactions use `__VIEWSTATE` and hidden form fields. The flow is:

1. **Login** — POST credentials to `/Login.aspx`
2. **2FA** (if enabled) — POST verification code
3. **Navigate to meters** — GET `/PopUp.aspx` with username
4. **Switch meter type** — POST image button click (HW/CW/ENERGY)
5. **Export CSV** — POST export button to download readings

## Authentication

### Step 1: GET login page

```http
GET /Login.aspx?ReturnUrl=%2fTenant.aspx HTTP/1.1
Host: www.istaonline.no
```

Response is an HTML page containing a `<form>` with hidden fields. Parse all `<input type="hidden">` and `_TSM` fields:

```html
<input type="hidden" name="__VIEWSTATE" value="/wEPDwUJNjMz..." />
<input type="hidden" name="__VIEWSTATEGENERATOR" value="C2EE9ABB" />
<input type="hidden" name="__EVENTVALIDATION" value="/wEdAAf..." />
<input type="hidden" name="__EVENTTARGET" value="" />
<input type="hidden" name="__EVENTARGUMENT" value="" />
<input type="hidden" name="__LASTFOCUS" value="" />
<input name="mainContent_RadScriptManagerMain_TSM" value="" />
```

### Step 2: POST credentials

```http
POST /Login.aspx?ReturnUrl=%2fTenant.aspx HTTP/1.1
Host: www.istaonline.no
Content-Type: application/x-www-form-urlencoded
```

Body includes all hidden fields from Step 1 plus:

```
ctl00$mainContent$edtUserName=REDACTED
ctl00$mainContent$edtPassword=REDACTED
ctl00_mainContent_edtPassword_ClientState={"enabled":true,"emptyMessage":"","validationText":"REDACTED","valueAsString":"REDACTED","lastSetTextBoxValue":"REDACTED"}
ctl00$mainContent$btnLogin=Logg+inn
ctl00$mainContent$hfFingerprint=00000000000000000000000000000000
```

Key details:
- The `hfFingerprint` field accepts a static all-zeros value.
- The `_ClientState` field is a JSON blob that must contain the password in `validationText`, `valueAsString`, and `lastSetTextBoxValue`.

### Step 3: Successful login response

```http
HTTP/1.1 302 Found
Location: /Tenant.aspx
Set-Cookie: .ASPXAUTH=<long-base64-value>; path=/; secure; HttpOnly
Set-Cookie: ASP.NET_SessionId=<session-id>; path=/; secure; HttpOnly; SameSite=Lax
```

The client follows the redirect to `/Tenant.aspx`, which returns a 200 with an HTML page containing "Forbruk" (consumption) in the body.

### Step 4: 2FA (if required)

If the response HTML contains "enter the code to proceed" or "authenticator", the account has email-based 2FA. The same form is re-submitted with the verification code in the password field, plus `ctl00$mainContent$chkRemember=on` to remember the device.

## Fetching Meter Data

### GET PopUp page

```http
GET /PopUp.aspx?Control=PopUp_Table&Metertype=ENERGY&cons_id=REDACTED&Culture=&rwndrnd=0.1700000000000 HTTP/1.1
Host: www.istaonline.no
Cookie: .ASPXAUTH=<auth-cookie>; ASP.NET_SessionId=<session-cookie>
```

The `cons_id` parameter is the username. The `rwndrnd` is a cache-busting timestamp (milliseconds since epoch).

The response is an HTML page containing meter data controls. Key elements to look for:
- `PopUpContentPlaceHolder` — confirms the page loaded correctly
- RadComboBox dropdowns for year selection
- Image buttons for meter type switching

### Year range selection

The popup page contains RadComboBox dropdowns with available year periods. The HTML looks like:

```html
<ul class="rcbList">
    <li class="rcbItem">01.01.2024 - 31.12.2024</li>
    <li class="rcbItem">01.01.2025 - 31.12.2025</li>
    <li class="rcbHovered">01.01.2026 - 31.12.2026</li>
</ul>
```

Parse `<li>` elements with class `rcbItem` or `rcbHovered` for date strings matching the `dd.mm.yyyy - dd.mm.yyyy` format.

Fields for setting the year range in export requests:
- `ctl00$PopUpContentPlaceHolder$ctl00$RadComboBoxFromYear` — from period
- `ctl00$PopUpContentPlaceHolder$ctl00$RadComboBoxToYear` — to period

### Switching meter types

The popup page shows one meter type at a time. Switch by POSTing the hidden fields from the current page plus an image button click:

| Meter Type | Button Field |
|---|---|
| Cold Water (CW) | `ctl00$PopUpContentPlaceHolder$ctl00$imbColdWater` |
| Hot Water (HW) | `ctl00$PopUpContentPlaceHolder$ctl00$imbHotWater` |
| Energy | `ctl00$PopUpContentPlaceHolder$ctl00$imbEnergy` |

Extra fields for the POST:

```
__EVENTTARGET=
__EVENTARGUMENT=
ctl00$PopUpContentPlaceHolder$ctl00$imbEnergy.x=10
ctl00$PopUpContentPlaceHolder$ctl00$imbEnergy.y=10
```

The `.x` and `.y` fields simulate image button click coordinates (any value works).

**Important**: After switching meter type, use the **returned HTML** as the base for the next switch (not the original popup HTML). The `__VIEWSTATE` must chain correctly through each POST.

### CSV Export

POST the hidden fields from the meter type page plus:

```
__EVENTTARGET=ctl00$PopUpContentPlaceHolder$ctl00$Button3
__EVENTARGUMENT=
ctl00$PopUpContentPlaceHolder$ctl00$CheckBox1=on
ctl00$PopUpContentPlaceHolder$ctl00$CheckBox2=on
ctl00$PopUpContentPlaceHolder$ctl00$CheckBox3=on
ctl00_PopUpContentPlaceHolder_ctl00_RadGrid1_ctl00_ctl03_ctl01_GridSliderPager_ClientState=<pager-json>
```

| Checkbox | Meaning |
|---|---|
| `CheckBox1` | Export data only (no chart headers) |
| `CheckBox2` | Export all pages (not just current page) |
| `CheckBox3` | Open in new window |

The pager state JSON resets to page 0 so the export starts from the beginning:

```json
{"value":0,"selectionStart":0,"selectionEnd":0,"isSelectionRangeEnabled":false,"orientation":0,"smallChange":1,"largeChange":0,"trackMouseWheel":true,"showDragHandle":true,"showDecreaseHandle":true,"showIncreaseHandle":true,"width":"200px","height":"22px","animationDuration":100,"minimumValue":0,"maximumValue":8,"trackPosition":1,"liveDrag":true,"dragText":"Dra","thumbsInteractionMode":1}
```

## CSV Response

### Response headers

```http
HTTP/1.1 200 OK
Content-Type: text/csv; charset=utf-8;
Content-Disposition: attachment;filename="IstaExportToCSV.csv"
```

If you get `Content-Type: text/html` instead, the server returned an error page (see [Error Responses](#error-responses)).

### CSV format

The CSV uses UTF-8 with BOM (`\ufeff`) and Norwegian decimal separators (comma).

### Columns

| Column | Description | Example |
|---|---|---|
| Måler | Meter ID | `903026XXX` |
| Rom | Room | `?` |
| Avlesning | Cumulative reading (Norwegian decimal) | `14854,30` |
| Faktor | Factor (usually 1) | `1` |
| Korrigert avlesning | Corrected reading | `0` |
| Korrigert forbruk | Daily consumption (Norwegian decimal) | `29,90` |
| Dato | Date (dd-MM-yyyy) | `17-02-2026` |
| Målertype | Meter type | `ENERGY` / `HW` / `CW` |
| Graddager | Degree days | `0` |

### Full example: ENERGY (two meters, multiple days)

```csv
"Måler","Rom","Avlesning","Faktor","Korrigert avlesning","Korrigert forbruk","Dato","Målertype","Graddager"
"903026XXX","?","14854,30","1","0","29,90","17-02-2026","ENERGY","0"
"903026YYY","?","1691","1","0","0","17-02-2026","ENERGY","0"
"903026XXX","?","14884","1","0","29,70","18-02-2026","ENERGY","0"
"903026YYY","?","1691","1","0","0","18-02-2026","ENERGY","0"
"903026XXX","?","14912,30","1","0","28,30","19-02-2026","ENERGY","0"
"903026YYY","?","1691,20","1","0","0,20","19-02-2026","ENERGY","0"
"903026XXX","?","14926,10","1","0","13,80","20-02-2026","ENERGY","0"
"903026YYY","?","1701,30","1","0","10,10","20-02-2026","ENERGY","0"
```

Note:
- `Avlesning` (cumulative reading) increases over time per meter
- `Korrigert forbruk` (daily consumption) is the difference from previous day
- Both meters appear interleaved, sorted by date
- Meter `903026YYY` has low/zero consumption (common for sub-meters)

### Example: Hot Water (HW)

```csv
"Måler","Rom","Avlesning","Faktor","Korrigert avlesning","Korrigert forbruk","Dato","Målertype","Graddager"
"932233XXX","?","437,1700","1","0","0,0500","17-02-2026","HW","0"
"932234XXX","?","87,3200","1","0","0,0100","17-02-2026","HW","0"
"932233XXX","?","437,2100","1","0","0,0400","18-02-2026","HW","0"
"932234XXX","?","87,3400","1","0","0,0200","18-02-2026","HW","0"
```

Note: Water readings use 4 decimal places (m³).

### Example: Cold Water (CW)

```csv
"Måler","Rom","Avlesning","Faktor","Korrigert avlesning","Korrigert forbruk","Dato","Målertype","Graddager"
"929410XXX","?","153,3400","1","0","0,0200","17-02-2026","CW","0"
"932072XXX","?","43,7800","1","0","0,0100","17-02-2026","CW","0"
```

### Decimal conversion

Norwegian format uses comma as decimal separator:
- `"14854,30"` → `14854.30`
- `"0,0500"` → `0.05`
- `"1691"` → `1691.0` (no comma = integer)

### Meter types

| Type | Unit | Description |
|---|---|---|
| `ENERGY` | kWh | District heating / energy |
| `HW` | m³ | Hot water |
| `CW` | m³ | Cold water |

## Required Headers

```http
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.3 Safari/605.1.15
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
Accept-Language: nb-NO,nb;q=0.9
```

## Session management

- Auth cookies (`.ASPXAUTH`, `ASP.NET_SessionId`) must be preserved across requests
- Sessions expire after some time — re-authenticate when requests fail
- Each client should use its own cookie jar to avoid leaking cookies to other services
- The WAF also sets tracking cookies (`x-bni-fpc`, `x-bni-ci`, `BNIS_x-bni-jas`) — these should be preserved but aren't required for auth

## Error Responses

istaonline.no returns **HTTP 200** for most errors — you must inspect the response body.

### WAF rate-limit page

Triggered by too many requests in a short period. Title: "Validation request".

```html
<html><body bgcolor="#405f8d">
<title>Validation request</title>
...
<em>Number of attempts left : <b><font color=yellow>5</font></b></em>
</body></html>
```

Wait a few minutes before retrying. The counter resets over time.

### Session expired redirect

When the session cookie expires, requests to `/PopUp.aspx` return a 302 redirect to `/Login.aspx`. The response body is the login page with `edtPassword` fields present.

### ASP.NET server error

```html
<title>Runtime Error</title>
<h2>Server Error in '/' Application.</h2>
<b>Runtime Error</b>
```

### CSV export returning HTML

If the CSV export button returns `Content-Type: text/html` instead of `text/csv`, the server failed to generate the export. The HTML body may contain an error message or just re-render the popup page.

### Norwegian error messages to check for

| Text | Meaning |
|---|---|
| `Feil brukernavn eller passord` | Wrong username or password |
| `Session utløpt` | Session expired |
| `Uventet feil` | Unexpected error |
