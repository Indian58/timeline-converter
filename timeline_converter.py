"""
Timeline Converter

Converts Google Timeline semantic segment data to a structured format with:
- Date (YYYY-MM-DD)
- Latitude & Longitude (parsed from "lat°, lon°" format)
- UTC Time (converted from ISO 8601 timestamps with timezone offset)
- Local Time (CST/CDT with proper DST handling)

Exports to both CSV and JSON formats.
"""

import csv
import json
import math
import re
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path


# ---------------------------------------------------------------------------
# Coordinate parsing
# ---------------------------------------------------------------------------

_COORD_PATTERN = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)\s*°\s*,\s*(-?\d+(?:\.\d+)?)\s*°\s*$"
)


def parse_coordinates(point: str) -> tuple[float, float]:
    """Parse a coordinate string of the form 'lat°, lon°' into (lat, lon).

    Args:
        point: Coordinate string, e.g. '38.6260541°, -95.8180999°'.

    Returns:
        A (latitude, longitude) tuple of floats.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    if not isinstance(point, str):
        raise ValueError(f"Expected a string for coordinates, got {type(point).__name__!r}")

    match = _COORD_PATTERN.match(point)
    if not match:
        raise ValueError(
            f"Cannot parse coordinates from {point!r}. "
            "Expected format: 'lat°, lon°' (e.g. '38.6260541°, -95.8180999°')"
        )

    lat = float(match.group(1))
    lon = float(match.group(2))

    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Latitude {lat} is out of valid range [-90, 90]")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Longitude {lon} is out of valid range [-180, 180]")

    return lat, lon


# ---------------------------------------------------------------------------
# Timestamp parsing & conversion
# ---------------------------------------------------------------------------

_CENTRAL_TZ = ZoneInfo("America/Chicago")


def parse_iso8601(timestamp: str) -> datetime:
    """Parse an ISO 8601 timestamp string into a timezone-aware datetime.

    Handles fractional seconds and timezone offsets such as '-05:00'.

    Args:
        timestamp: ISO 8601 string, e.g. '2024-08-27T19:26:00.000-05:00'.

    Returns:
        A timezone-aware :class:`datetime` object.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    if not isinstance(timestamp, str):
        raise ValueError(f"Expected a string for timestamp, got {type(timestamp).__name__!r}")

    # Python 3.11+ fromisoformat handles most ISO 8601 variants directly.
    # For earlier versions we normalise the string first.
    normalised = timestamp.strip()

    try:
        dt = datetime.fromisoformat(normalised)
    except ValueError:
        # Fallback: strip trailing 'Z' and retry
        if normalised.endswith("Z"):
            normalised = normalised[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(normalised)
        except ValueError as exc:
            raise ValueError(f"Cannot parse timestamp {timestamp!r}: {exc}") from exc

    if dt.tzinfo is None:
        raise ValueError(
            f"Timestamp {timestamp!r} has no timezone information. "
            "Please provide a timezone-aware ISO 8601 string."
        )

    return dt


def to_utc(dt: datetime) -> datetime:
    """Convert any timezone-aware datetime to UTC.

    Args:
        dt: A timezone-aware datetime.

    Returns:
        An equivalent datetime in UTC.
    """
    return dt.astimezone(timezone.utc)


def to_central(dt: datetime) -> datetime:
    """Convert any timezone-aware datetime to America/Chicago (CST/CDT).

    The ZoneInfo database automatically handles Daylight Saving Time.

    Args:
        dt: A timezone-aware datetime.

    Returns:
        An equivalent datetime in America/Chicago.
    """
    return dt.astimezone(_CENTRAL_TZ)


def get_timezone_abbreviation(dt: datetime) -> str:
    """Return the timezone abbreviation ('CST' or 'CDT') for a datetime.

    Args:
        dt: A datetime in the America/Chicago timezone.

    Returns:
        'CDT' if Daylight Saving Time is active, otherwise 'CST'.
    """
    dst_offset = dt.dst()
    if dst_offset is not None and dst_offset != timedelta(0):
        return "CDT"
    return "CST"


# ---------------------------------------------------------------------------
# Segment processing
# ---------------------------------------------------------------------------

def _make_record(
    dt_local: datetime,
    lat: float,
    lon: float,
    segment_type: str,
    extra: dict | None = None,
) -> dict:
    """Build a single output record dict."""
    dt_utc = to_utc(dt_local)
    tz_abbr = get_timezone_abbreviation(dt_local)

    record = {
        "date": dt_local.strftime("%Y-%m-%d"),
        "local_time": dt_local.strftime("%H:%M:%S"),
        "local_timezone": tz_abbr,
        "utc_time": dt_utc.strftime("%H:%M:%S"),
        "latitude": lat,
        "longitude": lon,
        "segment_type": segment_type,
    }
    if extra:
        record.update(extra)
    return record


def process_timeline_path(segment: dict) -> list[dict]:
    """Extract records from a *timelinePath* segment.

    Each point in the path becomes one output row.
    """
    records = []
    path = segment.get("timelinePath", [])
    for entry in path:
        try:
            lat, lon = parse_coordinates(entry.get("point", ""))
        except ValueError:
            continue  # skip malformed points

        raw_time = entry.get("time", "")
        try:
            dt = parse_iso8601(raw_time)
        except ValueError:
            continue

        dt_local = to_central(dt)
        records.append(_make_record(dt_local, lat, lon, "timeline_path"))

    return records


def _resolve_segment_time(segment: dict) -> datetime | None:
    """Return the start time of a segment as a Central datetime, or None."""
    raw = segment.get("startTime", "")
    try:
        dt = parse_iso8601(raw)
        return to_central(dt)
    except ValueError:
        return None


def process_activity(segment: dict) -> list[dict]:
    """Extract records from an *activity* segment.

    An activity segment has no explicit lat/lon, so (0.0, 0.0) is used as a
    placeholder; callers can filter or enrich this later.
    """
    activity = segment.get("activity", {})
    dt_local = _resolve_segment_time(segment)
    if dt_local is None:
        return []

    candidate = activity.get("topCandidate", {})
    extra = {
        "activity_type": candidate.get("type", ""),
        "activity_probability": candidate.get("probability", ""),
    }

    # Activities may not have location data; use NaN sentinel so consumers can
    # distinguish a missing coordinate from a genuine 0,0 coordinate.
    return [_make_record(dt_local, float("nan"), float("nan"), "activity", extra)]


def process_visit(segment: dict) -> list[dict]:
    """Extract records from a *visit* segment."""
    visit = segment.get("visit", {})
    dt_local = _resolve_segment_time(segment)
    if dt_local is None:
        return []

    candidate = visit.get("topCandidate", {})
    lat, lon = float("nan"), float("nan")
    place_location = candidate.get("placeLocation", {})
    lat_lng_str = place_location.get("latLng", "")
    if lat_lng_str:
        try:
            lat, lon = parse_coordinates(lat_lng_str)
        except ValueError:
            pass

    extra = {
        "semantic_type": candidate.get("semanticType", ""),
        "visit_probability": visit.get("probability", ""),
    }
    return [_make_record(dt_local, lat, lon, "visit", extra)]


def process_segment(segment: dict) -> list[dict]:
    """Dispatch a single segment to the appropriate handler.

    Handles 'timelinePath', 'activity', and 'visit' segment types.  Unknown
    segment types are silently skipped so that future Google Timeline formats
    do not cause failures.
    """
    records = []

    if "timelinePath" in segment:
        records.extend(process_timeline_path(segment))

    if "activity" in segment:
        records.extend(process_activity(segment))

    if "visit" in segment:
        records.extend(process_visit(segment))

    return records


# ---------------------------------------------------------------------------
# Top-level conversion
# ---------------------------------------------------------------------------

def convert(data: dict) -> list[dict]:
    """Convert a full semantic-segment payload to a list of record dicts.

    Args:
        data: Parsed JSON dict with a 'semanticSegments' key.

    Returns:
        A list of record dicts, one per timeline point / activity / visit.

    Raises:
        ValueError: If *data* does not contain a 'semanticSegments' key.
    """
    if "semanticSegments" not in data:
        raise ValueError(
            "Input JSON must contain a 'semanticSegments' key at the top level."
        )

    records = []
    for segment in data["semanticSegments"]:
        try:
            records.extend(process_segment(segment))
        except Exception as exc:  # pragma: no cover – belt-and-suspenders
            # Log but don't abort on a single bad segment
            print(f"Warning: skipping malformed segment: {exc}", file=sys.stderr)

    return records


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

_CSV_FIELDNAMES = [
    "date",
    "local_time",
    "local_timezone",
    "utc_time",
    "latitude",
    "longitude",
    "segment_type",
    "activity_type",
    "activity_probability",
    "semantic_type",
    "visit_probability",
]


def export_csv(records: list[dict], path: str | Path) -> None:
    """Write *records* to a CSV file at *path*.

    Missing fields are written as empty strings.  Floating-point NaN values
    (used for missing coordinates) are also written as empty strings.

    Args:
        records: List of record dicts as returned by :func:`convert`.
        path:    Destination file path.
    """
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=_CSV_FIELDNAMES,
            extrasaction="ignore",
        )
        writer.writeheader()
        for record in records:
            row = {k: record.get(k, "") for k in _CSV_FIELDNAMES}
            # Replace NaN coordinates with empty string for readability
            for coord_field in ("latitude", "longitude"):
                val = row[coord_field]
                try:
                    if isinstance(val, float) and math.isnan(val):
                        row[coord_field] = ""
                except TypeError:
                    pass
            writer.writerow(row)


def export_json(records: list[dict], path: str | Path) -> None:
    """Write *records* to a JSON file at *path*.

    NaN float values are serialised as ``null`` for valid JSON output.

    Args:
        records: List of record dicts as returned by :func:`convert`.
        path:    Destination file path.
    """
    path = Path(path)

    def _sanitise(value):
        if isinstance(value, float) and math.isnan(value):
            return None
        return value

    sanitised = [
        {k: _sanitise(v) for k, v in rec.items()} for rec in records
    ]

    with path.open("w", encoding="utf-8") as fh:
        json.dump(sanitised, fh, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Command-line entry point.

    Usage::

        python timeline_converter.py <input.json> [output_stem]

    If *output_stem* is omitted, it defaults to the input filename without
    its extension.  Two files are produced: ``<output_stem>.csv`` and
    ``<output_stem>.json``.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert Google Timeline semantic segments to CSV and JSON."
    )
    parser.add_argument("input", help="Path to the input JSON file")
    parser.add_argument(
        "output_stem",
        nargs="?",
        help="Output filename stem (without extension). Defaults to the input file stem.",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        with input_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"Error: failed to parse JSON: {exc}", file=sys.stderr)
        return 1

    try:
        records = convert(data)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    stem = args.output_stem if args.output_stem else input_path.stem
    csv_path = Path(stem).with_suffix(".csv")
    json_path = Path(stem).with_suffix(".json")

    export_csv(records, csv_path)
    export_json(records, json_path)

    print(f"Exported {len(records)} records to:")
    print(f"  {csv_path}")
    print(f"  {json_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
