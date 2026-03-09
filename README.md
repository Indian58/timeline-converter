# timeline-converter

Convert Google Timeline data to a clean spreadsheet (CSV) or JSON file with dates, coordinates, UTC times, and local CST/CDT times.

---

## Step 1 — Download your Google Timeline data

1. Go to **[Google Takeout](https://takeout.google.com/)** and sign in with your Google account.
2. Click **Deselect all**, then scroll down and check only **Location History (Timeline)**.
3. Click **Next step**, choose your preferred file format (`.zip` is fine), then click **Create export**.
4. Google will email you a download link — this can take a few minutes to a few hours.
5. Download and unzip the archive.
6. Inside the unzipped folder, find the file:
   ```
   Takeout/Location History (Timeline)/Semantic Location History/<year>/<year>_<MONTH>.json
   ```
   For example:
   ```
   Takeout/Location History (Timeline)/Semantic Location History/2024/2024_AUGUST.json
   ```
   That JSON file is your input.

---

## Step 2 — Requirements

- **Python 3.9 or newer** (Python 3.11+ recommended).  
  Check your version: `python --version`
- No third-party packages are required to run the converter.  
  The `pytest` package is only needed if you want to run the tests.

---

## Step 3 — Run the converter

Open a terminal, navigate to this folder, and run:

```bash
python timeline_converter.py path/to/your_input.json
```

**Example** using the included sample file:

```bash
python timeline_converter.py sample_input.json
```

Expected output:

```
Exported 5 records to:
  sample_input.csv
  sample_input.json
```

Two files are created in the same directory you run the command from:

| File | Contents |
|------|----------|
| `sample_input.csv` | Spreadsheet — open in Excel, Google Sheets, etc. |
| `sample_input.json` | Structured JSON — useful for further processing |

### Choosing a different output name

```bash
python timeline_converter.py path/to/input.json my_trips
```

This produces `my_trips.csv` and `my_trips.json`.

---

## Output columns

| Column | Example | Description |
|--------|---------|-------------|
| `date` | `2024-08-27` | Date in YYYY-MM-DD format |
| `local_time` | `19:26:00` | Time in local (Central) timezone |
| `local_timezone` | `CDT` | `CDT` during summer (DST), `CST` in winter |
| `utc_time` | `00:26:00` | Same moment converted to UTC |
| `latitude` | `38.6260541` | Latitude |
| `longitude` | `-95.8180999` | Longitude |
| `segment_type` | `timeline_path` | `timeline_path`, `activity`, or `visit` |
| `activity_type` | `IN_VEHICLE` | Movement type (activities only) |
| `activity_probability` | `0.95` | Confidence score (activities only) |
| `semantic_type` | `HOME` | Place label like `HOME` or `WORK` (visits only) |
| `visit_probability` | `0.9` | Confidence score (visits only) |

---

## Using the converter from Python

```python
import json
from timeline_converter import convert, export_csv, export_json

with open("your_input.json", encoding="utf-8") as f:
    data = json.load(f)

records = convert(data)
export_csv(records, "output.csv")
export_json(records, "output.json")

print(f"Converted {len(records)} records")
```

---

## Running the tests

```bash
pip install pytest
python -m pytest test_timeline_converter.py -v
```

All 48 tests should pass.
