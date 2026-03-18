"""Constants for the ista online (Norway) integration."""

from datetime import timedelta

DOMAIN = "ista_no"

BASE_URL = "https://www.istaonline.no"
LOGIN_PATH = "/Login.aspx?ReturnUrl=%2fTenant.aspx"

# ASP.NET form field names for meter-type image buttons
METER_BUTTON = {
    "CW": "ctl00$PopUpContentPlaceHolder$ctl00$imbColdWater",
    "HW": "ctl00$PopUpContentPlaceHolder$ctl00$imbHotWater",
    "ENERGY": "ctl00$PopUpContentPlaceHolder$ctl00$imbEnergy",
}

CSV_EXPORT_TARGET = "ctl00$PopUpContentPlaceHolder$ctl00$Button3"

# Pager state at page 0 so CSV export starts from the beginning
PAGER_STATE_PAGE0 = (
    '{"value":0,"selectionStart":0,"selectionEnd":0,'
    '"isSelectionRangeEnabled":false,"orientation":0,'
    '"smallChange":1,"largeChange":0,"trackMouseWheel":true,'
    '"showDragHandle":true,"showDecreaseHandle":true,'
    '"showIncreaseHandle":true,"width":"200px","height":"22px",'
    '"animationDuration":100,"minimumValue":0,"maximumValue":8,'
    '"trackPosition":1,"liveDrag":true,"dragText":"Dra",'
    '"thumbsInteractionMode":1}'
)

# CSV column names (Norwegian)
CSV_METER = "Måler"
CSV_ROOM = "Rom"
CSV_READING = "Avlesning"
CSV_FACTOR = "Faktor"
CSV_CORRECTED_READING = "Korrigert avlesning"
CSV_CORRECTED_CONSUMPTION = "Korrigert forbruk"
CSV_DATE = "Dato"
CSV_METER_TYPE = "Målertype"
CSV_DEGREE_DAYS = "Graddager"

# Meter type display labels and units
UNIT = {"CW": "m³", "HW": "m³", "ENERGY": "kWh"}
LABEL = {"CW": "Cold water", "HW": "Hot water", "ENERGY": "Heating (energy)"}

# Meter types to iterate
METER_TYPES = ("HW", "CW", "ENERGY")

# Static fingerprint value (works for login)
FINGERPRINT = "00000000000000000000000000000000"

# Browser-like headers
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.3 Safari/605.1.15"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nb-NO,nb;q=0.9",
}

# Polling interval
UPDATE_INTERVAL = timedelta(hours=6)

# Form field names used during login
FIELD_USERNAME = "ctl00$mainContent$edtUserName"
FIELD_PASSWORD = "ctl00$mainContent$edtPassword"
FIELD_PASSWORD_STATE = "ctl00_mainContent_edtPassword_ClientState"
FIELD_LOGIN_BUTTON = "ctl00$mainContent$btnLogin"
FIELD_FINGERPRINT = "ctl00$mainContent$hfFingerprint"

# ComboBox field names for year selection
FIELD_FROM_YEAR = "ctl00$PopUpContentPlaceHolder$ctl00$RadComboBoxFromYear"
FIELD_TO_YEAR = "ctl00$PopUpContentPlaceHolder$ctl00$RadComboBoxToYear"

# Export checkboxes
FIELD_EXPORT_DATA_ONLY = "ctl00$PopUpContentPlaceHolder$ctl00$CheckBox1"
FIELD_EXPORT_ALL_PAGES = "ctl00$PopUpContentPlaceHolder$ctl00$CheckBox2"
FIELD_EXPORT_NEW_WINDOW = "ctl00$PopUpContentPlaceHolder$ctl00$CheckBox3"
FIELD_PAGER_STATE = "ctl00_PopUpContentPlaceHolder_ctl00_RadGrid1_ctl00_ctl03_ctl01_GridSliderPager_ClientState"
