"""
Unit tests for timeline_converter.py
"""

import json
import math
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from timeline_converter import (
    parse_coordinates,
    parse_iso8601,
    to_utc,
    to_central,
    get_timezone_abbreviation,
    process_segment,
    convert,
    export_csv,
    export_json,
    main,
)

_CENTRAL_TZ = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# parse_coordinates
# ---------------------------------------------------------------------------

class TestParseCoordinates:
    def test_basic_positive_coords(self):
        lat, lon = parse_coordinates("38.6260541°, -95.8180999°")
        assert lat == pytest.approx(38.6260541)
        assert lon == pytest.approx(-95.8180999)

    def test_both_positive(self):
        lat, lon = parse_coordinates("51.5074°, 0.1278°")
        assert lat == pytest.approx(51.5074)
        assert lon == pytest.approx(0.1278)

    def test_both_negative(self):
        lat, lon = parse_coordinates("-33.8688°, -70.6693°")
        assert lat == pytest.approx(-33.8688)
        assert lon == pytest.approx(-70.6693)

    def test_integer_coords(self):
        lat, lon = parse_coordinates("0°, 0°")
        assert lat == 0.0
        assert lon == 0.0

    def test_extra_whitespace(self):
        lat, lon = parse_coordinates("  38.5°,  -90.0°  ")
        assert lat == pytest.approx(38.5)
        assert lon == pytest.approx(-90.0)

    def test_invalid_format_missing_degree_symbol(self):
        with pytest.raises(ValueError, match="Cannot parse coordinates"):
            parse_coordinates("38.6260541, -95.8180999")

    def test_invalid_format_empty_string(self):
        with pytest.raises(ValueError):
            parse_coordinates("")

    def test_invalid_type(self):
        with pytest.raises(ValueError, match="Expected a string"):
            parse_coordinates(None)

    def test_latitude_out_of_range(self):
        with pytest.raises(ValueError, match="Latitude.*out of valid range"):
            parse_coordinates("91.0°, 0.0°")

    def test_longitude_out_of_range(self):
        with pytest.raises(ValueError, match="Longitude.*out of valid range"):
            parse_coordinates("0.0°, 181.0°")

    def test_extreme_valid_coords(self):
        lat, lon = parse_coordinates("90.0°, 180.0°")
        assert lat == 90.0
        assert lon == 180.0

    def test_negative_extreme_valid_coords(self):
        lat, lon = parse_coordinates("-90.0°, -180.0°")
        assert lat == -90.0
        assert lon == -180.0


# ---------------------------------------------------------------------------
# parse_iso8601
# ---------------------------------------------------------------------------

class TestParseIso8601:
    def test_with_negative_offset(self):
        dt = parse_iso8601("2024-08-27T19:26:00.000-05:00")
        assert dt.year == 2024
        assert dt.month == 8
        assert dt.day == 27
        assert dt.hour == 19
        assert dt.minute == 26
        assert dt.second == 0
        offset = dt.utcoffset()
        assert offset == timedelta(hours=-5)

    def test_with_positive_offset(self):
        dt = parse_iso8601("2024-08-27T09:00:00.000+05:30")
        assert dt.utcoffset() == timedelta(hours=5, minutes=30)

    def test_with_z_suffix(self):
        dt = parse_iso8601("2024-08-27T00:00:00Z")
        assert dt.utcoffset() == timedelta(0)

    def test_no_fractional_seconds(self):
        dt = parse_iso8601("2024-08-27T19:00:00-05:00")
        assert dt.second == 0

    def test_naive_timestamp_raises(self):
        with pytest.raises(ValueError, match="no timezone information"):
            parse_iso8601("2024-08-27T19:00:00")

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError, match="Cannot parse timestamp"):
            parse_iso8601("not-a-timestamp")

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Expected a string"):
            parse_iso8601(12345)


# ---------------------------------------------------------------------------
# to_utc
# ---------------------------------------------------------------------------

class TestToUtc:
    def test_from_minus_five(self):
        dt = parse_iso8601("2024-08-27T19:00:00-05:00")
        utc = to_utc(dt)
        assert utc.tzinfo == timezone.utc
        assert utc.hour == 0  # 19:00 - 05:00 offset = 24:00 = next day 00:00
        assert utc.day == 28

    def test_from_plus_zero(self):
        dt = parse_iso8601("2024-08-27T12:00:00+00:00")
        utc = to_utc(dt)
        assert utc.hour == 12
        assert utc.day == 27


# ---------------------------------------------------------------------------
# to_central + get_timezone_abbreviation
# ---------------------------------------------------------------------------

class TestToCentral:
    def test_august_is_cdt(self):
        """August 27, 2024 is during DST (CDT = UTC-5)."""
        dt = parse_iso8601("2024-08-27T19:00:00-05:00")
        central = to_central(dt)
        assert central.tzinfo is not None
        tz_abbr = get_timezone_abbreviation(central)
        assert tz_abbr == "CDT"

    def test_january_is_cst(self):
        """January is outside DST (CST = UTC-6)."""
        dt = parse_iso8601("2024-01-15T12:00:00-06:00")
        central = to_central(dt)
        tz_abbr = get_timezone_abbreviation(central)
        assert tz_abbr == "CST"

    def test_november_after_dst_end_is_cst(self):
        """November 5, 2024 after clocks fall back (02:00 -> 01:00)."""
        # 11:00 CST = UTC-6, so this datetime is after the fall-back
        dt = parse_iso8601("2024-11-05T12:00:00-06:00")
        central = to_central(dt)
        tz_abbr = get_timezone_abbreviation(central)
        assert tz_abbr == "CST"

    def test_utc_conversion_during_cdt(self):
        """19:00 CDT (UTC-5) should equal 00:00 UTC next day."""
        dt = parse_iso8601("2024-08-27T19:00:00-05:00")
        central = to_central(dt)
        utc = to_utc(central)
        assert utc.hour == 0
        assert utc.day == 28

    def test_cdt_offset_is_minus_5(self):
        dt = parse_iso8601("2024-08-27T00:00:00-05:00")
        central = to_central(dt)
        assert central.utcoffset() == timedelta(hours=-5)

    def test_cst_offset_is_minus_6(self):
        dt = parse_iso8601("2024-01-15T00:00:00-06:00")
        central = to_central(dt)
        assert central.utcoffset() == timedelta(hours=-6)


# ---------------------------------------------------------------------------
# process_segment – timeline_path
# ---------------------------------------------------------------------------

class TestProcessTimelinePath:
    def test_single_point(self):
        segment = {
            "startTime": "2024-08-27T19:00:00.000-05:00",
            "endTime": "2024-08-27T21:00:00.000-05:00",
            "timelinePath": [
                {
                    "point": "38.6260541°, -95.8180999°",
                    "time": "2024-08-27T19:26:00.000-05:00",
                }
            ],
        }
        records = process_segment(segment)
        assert len(records) == 1
        r = records[0]
        assert r["segment_type"] == "timeline_path"
        assert r["date"] == "2024-08-27"
        assert r["latitude"] == pytest.approx(38.6260541)
        assert r["longitude"] == pytest.approx(-95.8180999)
        assert r["local_timezone"] == "CDT"
        assert r["utc_time"] == "00:26:00"

    def test_multiple_points(self):
        segment = {
            "timelinePath": [
                {"point": "38.0°, -90.0°", "time": "2024-08-27T19:00:00-05:00"},
                {"point": "39.0°, -91.0°", "time": "2024-08-27T20:00:00-05:00"},
            ]
        }
        records = process_segment(segment)
        assert len(records) == 2

    def test_skips_malformed_point(self):
        segment = {
            "timelinePath": [
                {"point": "INVALID", "time": "2024-08-27T19:00:00-05:00"},
                {"point": "38.0°, -90.0°", "time": "2024-08-27T20:00:00-05:00"},
            ]
        }
        records = process_segment(segment)
        assert len(records) == 1

    def test_skips_malformed_timestamp(self):
        segment = {
            "timelinePath": [
                {"point": "38.0°, -90.0°", "time": "not-a-time"},
            ]
        }
        records = process_segment(segment)
        assert len(records) == 0


# ---------------------------------------------------------------------------
# process_segment – activity
# ---------------------------------------------------------------------------

class TestProcessActivity:
    def test_activity_record(self):
        segment = {
            "startTime": "2024-08-27T21:00:00.000-05:00",
            "endTime": "2024-08-27T22:30:00.000-05:00",
            "activity": {
                "topCandidate": {
                    "type": "IN_VEHICLE",
                    "probability": 0.95,
                }
            },
        }
        records = process_segment(segment)
        assert len(records) == 1
        r = records[0]
        assert r["segment_type"] == "activity"
        assert r["activity_type"] == "IN_VEHICLE"
        assert r["activity_probability"] == pytest.approx(0.95)
        assert r["local_timezone"] == "CDT"

    def test_activity_missing_start_time(self):
        segment = {
            "activity": {"topCandidate": {"type": "WALKING"}},
        }
        records = process_segment(segment)
        assert len(records) == 0


# ---------------------------------------------------------------------------
# process_segment – visit
# ---------------------------------------------------------------------------

class TestProcessVisit:
    def test_visit_with_lat_lng(self):
        segment = {
            "startTime": "2024-08-27T22:30:00.000-05:00",
            "endTime": "2024-08-28T08:00:00.000-05:00",
            "visit": {
                "probability": 0.9,
                "topCandidate": {
                    "semanticType": "HOME",
                    "probability": 0.95,
                    "placeLocation": {
                        "latLng": "38.6260541°, -90.1994042°"
                    },
                },
            },
        }
        records = process_segment(segment)
        assert len(records) == 1
        r = records[0]
        assert r["segment_type"] == "visit"
        assert r["semantic_type"] == "HOME"
        assert r["latitude"] == pytest.approx(38.6260541)
        assert r["longitude"] == pytest.approx(-90.1994042)

    def test_visit_without_lat_lng(self):
        segment = {
            "startTime": "2024-08-27T22:30:00.000-05:00",
            "visit": {
                "topCandidate": {"semanticType": "WORK"},
            },
        }
        records = process_segment(segment)
        assert len(records) == 1
        r = records[0]
        # Should use NaN for missing coordinates
        assert math.isnan(r["latitude"])
        assert math.isnan(r["longitude"])

    def test_visit_missing_start_time(self):
        segment = {"visit": {"topCandidate": {"semanticType": "HOME"}}}
        records = process_segment(segment)
        assert len(records) == 0


# ---------------------------------------------------------------------------
# convert (top-level)
# ---------------------------------------------------------------------------

class TestConvert:
    def test_convert_sample_data(self):
        data = {
            "semanticSegments": [
                {
                    "startTime": "2024-08-27T19:00:00.000-05:00",
                    "endTime": "2024-08-27T21:00:00.000-05:00",
                    "timelinePath": [
                        {
                            "point": "38.6260541°, -95.8180999°",
                            "time": "2024-08-27T19:26:00.000-05:00",
                        }
                    ],
                }
            ]
        }
        records = convert(data)
        assert len(records) == 1
        assert records[0]["date"] == "2024-08-27"

    def test_convert_missing_key_raises(self):
        with pytest.raises(ValueError, match="semanticSegments"):
            convert({"foo": []})

    def test_convert_empty_segments(self):
        records = convert({"semanticSegments": []})
        assert records == []

    def test_convert_multiple_segment_types(self):
        data = {
            "semanticSegments": [
                {
                    "startTime": "2024-08-27T19:00:00.000-05:00",
                    "endTime": "2024-08-27T21:00:00.000-05:00",
                    "timelinePath": [
                        {"point": "38.0°, -90.0°", "time": "2024-08-27T19:00:00-05:00"}
                    ],
                },
                {
                    "startTime": "2024-08-27T21:00:00.000-05:00",
                    "endTime": "2024-08-27T22:30:00.000-05:00",
                    "activity": {
                        "topCandidate": {"type": "IN_VEHICLE", "probability": 0.9}
                    },
                },
                {
                    "startTime": "2024-08-27T22:30:00.000-05:00",
                    "endTime": "2024-08-28T08:00:00.000-05:00",
                    "visit": {
                        "topCandidate": {
                            "semanticType": "HOME",
                            "placeLocation": {"latLng": "38.0°, -90.0°"},
                        }
                    },
                },
            ]
        }
        records = convert(data)
        types = [r["segment_type"] for r in records]
        assert "timeline_path" in types
        assert "activity" in types
        assert "visit" in types


# ---------------------------------------------------------------------------
# export_csv
# ---------------------------------------------------------------------------

class TestExportCsv:
    def test_creates_csv_with_header(self):
        records = [
            {
                "date": "2024-08-27",
                "local_time": "19:26:00",
                "local_timezone": "CDT",
                "utc_time": "00:26:00",
                "latitude": 38.6260541,
                "longitude": -95.8180999,
                "segment_type": "timeline_path",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "output.csv"
            export_csv(records, csv_path)
            content = csv_path.read_text(encoding="utf-8")

        lines = content.strip().split("\n")
        assert lines[0].startswith("date,")
        assert "2024-08-27" in lines[1]
        assert "CDT" in lines[1]

    def test_nan_coordinates_written_as_empty(self):
        records = [
            {
                "date": "2024-08-27",
                "local_time": "21:00:00",
                "local_timezone": "CDT",
                "utc_time": "02:00:00",
                "latitude": float("nan"),
                "longitude": float("nan"),
                "segment_type": "activity",
                "activity_type": "IN_VEHICLE",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "output.csv"
            export_csv(records, csv_path)
            content = csv_path.read_text(encoding="utf-8")

        assert "nan" not in content.lower()


# ---------------------------------------------------------------------------
# export_json
# ---------------------------------------------------------------------------

class TestExportJson:
    def test_creates_valid_json(self):
        records = [
            {
                "date": "2024-08-27",
                "local_time": "19:26:00",
                "local_timezone": "CDT",
                "utc_time": "00:26:00",
                "latitude": 38.6260541,
                "longitude": -95.8180999,
                "segment_type": "timeline_path",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "output.json"
            export_json(records, json_path)
            loaded = json.loads(json_path.read_text(encoding="utf-8"))

        assert len(loaded) == 1
        assert loaded[0]["date"] == "2024-08-27"

    def test_nan_coordinates_serialised_as_null(self):
        records = [
            {
                "date": "2024-08-27",
                "latitude": float("nan"),
                "longitude": float("nan"),
                "segment_type": "activity",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "output.json"
            export_json(records, json_path)
            content = json_path.read_text(encoding="utf-8")
            loaded = json.loads(content)

        assert loaded[0]["latitude"] is None
        assert loaded[0]["longitude"] is None


# ---------------------------------------------------------------------------
# CLI (main)
# ---------------------------------------------------------------------------

class TestMain:
    def test_main_converts_sample_file(self):
        sample = {
            "semanticSegments": [
                {
                    "startTime": "2024-08-27T19:00:00.000-05:00",
                    "endTime": "2024-08-27T21:00:00.000-05:00",
                    "timelinePath": [
                        {
                            "point": "38.6260541°, -95.8180999°",
                            "time": "2024-08-27T19:26:00.000-05:00",
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.json"
            input_path.write_text(json.dumps(sample), encoding="utf-8")
            output_stem = str(Path(tmpdir) / "output")

            result = main([str(input_path), output_stem])

        assert result == 0

    def test_main_missing_file_returns_1(self):
        result = main(["/nonexistent/file.json"])
        assert result == 1

    def test_main_invalid_json_returns_1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = Path(tmpdir) / "bad.json"
            bad_path.write_text("not json", encoding="utf-8")
            result = main([str(bad_path)])
        assert result == 1

    def test_main_missing_key_returns_1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "no_key.json"
            path.write_text(json.dumps({"foo": []}), encoding="utf-8")
            result = main([str(path)])
        assert result == 1
