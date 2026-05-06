# timeline-converter (semantic data only)

This script only works on the old location semantic data Google used to include in Google takeout.  The old Takeout provided Semantic location history in .json format.  Also in that takeout it included records.json which was the raw location data and was not editable by the user and way more accurate. Semantic data which is the timeline data and should not be trusted as a 4 year old can modify it.



Googles new location data is saved on your phone and can be exported to csv.  The new data is semantic and like the old semantic data cannot be trusted.  



Convert Google Timeline data to a clean spreadsheet (CSV) or JSON file with dates, coordinates, UTC times, and local CST/CDT times.This

\---

## Step 1 — Download your Google Timeline data

1. Go to [**Google Takeout**](https://takeout.google.com/) and sign in with your Google account.
2. Click **Deselect all**, then scroll down and check only **Location History (Timeline)**.
3. Click **Next step**, choose your preferred file format (`.zip` is fine), then click **Create export**.
4. Google will email you a download link — this can take a few minutes to a few hours.
5. Download and unzip the archive.
6. Inside the unzipped folder, find the file:

```
   Takeout/Location History (Timeline)/Semantic Location History/<year>/<year>\_<MONTH>.json
   ```

   For example:

   ```
   Takeout/Location History (Timeline)/Semantic Location History/2024/2024\_AUGUST.json
   ```

   That JSON file is your input.

   \---

   ## Step 2 — Requirements

* **Python 3.9 or newer** (Python 3.11+ recommended).  
Check your version: `python --version`
* No third-party packages are required to run the converter.  
The `pytest` package is only needed if you want to run the tests.

  \---

  ## Step 3 — Run the converter

  Open a terminal, navigate to this folder, and run:

  ```bash
python timeline\_converter.py path/to/your\_input.json
```

  **Example** using the included sample file:

  ```bash
python timeline\_converter.py sample\_input.json
```

  Expected output:

  ```
Exported 5 records to:
  sample\_input.csv
  sample\_input.json
```

  Two files are created in the same directory you run the command from:

|File|Contents|
|-|-|
|`sample\_input.csv`|Spreadsheet — open in Excel, Google Sheets, etc.|
|`sample\_input.json`|Structured JSON — useful for further processing|

### Choosing a different output name

```bash
python timeline\_converter.py path/to/input.json my\_trips
```

This produces `my\_trips.csv` and `my\_trips.json`.

\---

## Output columns

|Column|Example|Description|
|-|-|-|
|`date`|`2024-08-27`|Date in YYYY-MM-DD format|
|`local\_time`|`19:26:00`|Time in local (Central) timezone|
|`local\_timezone`|`CDT`|`CDT` during summer (DST), `CST` in winter|
|`utc\_time`|`00:26:00`|Same moment converted to UTC|
|`latitude`|`38.6260541`|Latitude|
|`longitude`|`-95.8180999`|Longitude|
|`segment\_type`|`timeline\_path`|`timeline\_path`, `activity`, or `visit`|
|`activity\_type`|`IN\_VEHICLE`|Movement type (activities only)|
|`activity\_probability`|`0.95`|Confidence score (activities only)|
|`semantic\_type`|`HOME`|Place label like `HOME` or `WORK` (visits only)|
|`visit\_probability`|`0.9`|Confidence score (visits only)|

\---

## Using the converter from Python

```python
import json
from timeline\_converter import convert, export\_csv, export\_json

with open("your\_input.json", encoding="utf-8") as f:
    data = json.load(f)

records = convert(data)
export\_csv(records, "output.csv")
export\_json(records, "output.json")

print(f"Converted {len(records)} records")
```

\---

## Running the tests

```bash
pip install pytest
python -m pytest test\_timeline\_converter.py -v
```

All 48 tests should pass.

