import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_CENTRAL_TZ = ZoneInfo("America/Chicago")


def utc_str_to_local(timestamp: str) -> str:
    """Parse a UTC ISO 8601 timestamp and return local Central time string.

    Returns an empty string if the timestamp cannot be parsed.
    """
    if not timestamp:
        return ""
    try:
        normalised = timestamp.strip()
        if normalised.endswith("Z"):
            normalised = normalised[:-1] + "+00:00"
        dt_utc = datetime.fromisoformat(normalised)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone(_CENTRAL_TZ)
        abbr = "CDT" if dt_local.dst() else "CST"
        return f"{dt_local.strftime('%Y-%m-%d, %H:%M:%S')} {abbr}"
    except (ValueError, TypeError):
        return ""


try:
    print("Looking for JSON files in all directories...\n")

    total_count = 0
    files_processed = 0

    # Walk through all directories
    for root, dirs, files in os.walk('.'):
        # Get all JSON files in current directory
        json_files = [f for f in files if f.endswith('.json')]
        json_files.sort()  # Sort alphabetically

        if json_files:
            print(f"Directory: {root}")
            print(f"Found {len(json_files)} JSON files\n")

            for json_file in json_files:
                json_path = os.path.join(root, json_file)
                print(f"  Processing {json_file}...")

                try:
                    with open(json_path) as f:
                        data = json.load(f)

                    # Create output filename in the SAME directory as input
                    base_name = json_file.replace('.json', '')
                    output_file = os.path.join(root, f"output_{base_name}.txt")

                    with open(output_file, 'w') as out:
                        count = 0
                        for obj in data.get('timelineObjects', []):
                            if 'activitySegment' in obj:
                                seg = obj['activitySegment']
                                dur = seg.get('duration', {})
                                start_loc = seg.get('startLocation', {})
                                lat = start_loc.get('latitudeE7', 0) / 10000000
                                lon = start_loc.get('longitudeE7', 0) / 10000000
                                ts_raw = dur.get('startTimestamp', '')
                                ts = ts_raw.replace('Z', '').replace('T', ', ')
                                local = utc_str_to_local(ts_raw)
                                out.write(f"{ts} UTC, {local}, {lat}, {lon}\n")
                                count += 1

                            if 'placeVisit' in obj:
                                visit = obj['placeVisit']
                                loc = visit.get('location', {})
                                dur = visit.get('duration', {})
                                lat = loc.get('latitudeE7', 0) / 10000000
                                lon = loc.get('longitudeE7', 0) / 10000000
                                ts_raw = dur.get('startTimestamp', '')
                                ts = ts_raw.replace('Z', '').replace('T', ', ')
                                local = utc_str_to_local(ts_raw)
                                out.write(f"{ts} UTC, {local}, {lat}, {lon}\n")
                                count += 1

                        print(f"    → Extracted {count} records to output_{base_name}.txt")
                        total_count += count
                        files_processed += 1

                except Exception as e:
                    print(f"    → ERROR processing {json_file}: {e}")

            print()  # Blank line between directories

    if files_processed == 0:
        print("ERROR: No JSON files found in any directories!")
    else:
        print(f"Success! Processed {files_processed} files and extracted {total_count} total records")

    input("Press Enter to close...")

except Exception as e:
    print(f"ERROR: {e}")
    input("Press Enter to close...")
