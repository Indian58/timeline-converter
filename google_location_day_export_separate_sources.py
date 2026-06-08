import json
import csv
import re
from datetime import datetime
from pathlib import Path

LATLNG_RE = re.compile(r'^\s*([+-]?\d+(?:\.\d+)?)°?,\s*([+-]?\d+(?:\.\d+)?)°?\s*$')


def parse_latlng_string(value):
    if not isinstance(value, str):
        return "", ""
    m = LATLNG_RE.match(value.strip())
    if not m:
        return "", ""
    return round(float(m.group(1)), 6), round(float(m.group(2)), 6)


def e7_to_float(value):
    if value in (None, ""):
        return ""
    try:
        return round(float(value) / 1e7, 6)
    except Exception:
        return ""


def split_timestamp(ts):
    if not ts:
        return "", ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.date().isoformat(), dt.time().isoformat()
    except Exception:
        return "", ""


def duration_minutes(start, end):
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return round((b - a).total_seconds() / 60, 2)
    except Exception:
        return ""


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def detect_format(data):
    if "semanticSegments" in data:
        return "new_timeline"
    if "locations" in data:
        return "records"
    if "timelineObjects" in data:
        return "old_semantic"
    return "unknown"


def process_new_timeline(data, target_date):
    visits = []
    activities = []
    points = []

    segments = data.get("semanticSegments", [])

    for idx, segment in enumerate(segments):
        start_time = segment.get("startTime", "")
        end_time = segment.get("endTime", "")
        start_date, start_clock = split_timestamp(start_time)
        end_date, end_clock = split_timestamp(end_time)
        minutes = duration_minutes(start_time, end_time)

        if "visit" in segment and start_date == target_date:
            visit = segment.get("visit", {})
            top = visit.get("topCandidate", {})
            lat, lon = parse_latlng_string(top.get("placeLocation", {}).get("latLng"))

            visits.append({
                "segment_index": idx,
                "start_date": start_date,
                "start_time": start_clock,
                "end_date": end_date,
                "end_time": end_clock,
                "duration_minutes": minutes,
                "latitude": lat,
                "longitude": lon,
                "place_id": top.get("placeId", ""),
                "name": "",
                "address": "",
                "semantic_type": top.get("semanticType", ""),
                "visit_probability": visit.get("probability", ""),
                "candidate_probability": top.get("probability", ""),
                "hierarchy_level": visit.get("hierarchyLevel", ""),
            })

        if "activity" in segment and start_date == target_date:
            activity = segment.get("activity", {})
            top = activity.get("topCandidate", {})
            start_lat, start_lon = parse_latlng_string(activity.get("start", {}).get("latLng"))
            end_lat, end_lon = parse_latlng_string(activity.get("end", {}).get("latLng"))

            activities.append({
                "segment_index": idx,
                "start_date": start_date,
                "start_time": start_clock,
                "end_date": end_date,
                "end_time": end_clock,
                "duration_minutes": minutes,
                "start_latitude": start_lat,
                "start_longitude": start_lon,
                "end_latitude": end_lat,
                "end_longitude": end_lon,
                "distance_meters": activity.get("distanceMeters", ""),
                "activity_type": top.get("type", ""),
                "activity_confidence": top.get("probability", ""),
                "travel_mode": "",
            })

        if "timelinePath" in segment:
            for point_idx, pt in enumerate(segment.get("timelinePath", [])):
                point_date, point_time = split_timestamp(pt.get("time", ""))
                if point_date != target_date:
                    continue
                lat, lon = parse_latlng_string(pt.get("point", ""))

                points.append({
                    "segment_index": idx,
                    "point_index": point_idx,
                    "date": point_date,
                    "time": point_time,
                    "latitude": lat,
                    "longitude": lon,
                    "accuracy_meters": "",
                    "source": "",
                    "device_tag": "",
                })

    return visits, activities, points, []


def process_records(data, target_date):
    record_points = []

    locations = data.get("locations", [])

    for idx, loc in enumerate(locations):
        ts = loc.get("timestamp", "")
        date_part, time_part = split_timestamp(ts)
        if date_part != target_date:
            continue

        lat = e7_to_float(loc.get("latitudeE7"))
        lon = e7_to_float(loc.get("longitudeE7"))

        activity_type = ""
        activity_confidence = ""

        activity_blocks = loc.get("activity", [])
        if activity_blocks:
            first_block = activity_blocks[0]
            activities = first_block.get("activity", [])
            if activities:
                best = max(activities, key=lambda x: x.get("confidence", -1))
                activity_type = best.get("type", "")
                activity_confidence = best.get("confidence", "")

        record_points.append({
            "record_index": idx,
            "date": date_part,
            "time": time_part,
            "latitude": lat,
            "longitude": lon,
            "accuracy_meters": loc.get("accuracy", ""),
            "source": loc.get("source", ""),
            "device_tag": loc.get("deviceTag", ""),
            "activity_type": activity_type,
            "activity_confidence": activity_confidence,
        })

    return [], [], [], record_points


def process_old_semantic(data, target_date):
    visits = []
    activities = []
    points = []

    objects = data.get("timelineObjects", [])

    for idx, obj in enumerate(objects):
        if "placeVisit" in obj:
            pv = obj.get("placeVisit", {})
            duration = pv.get("duration", {})
            start_time = duration.get("startTimestamp", "")
            end_time = duration.get("endTimestamp", "")
            start_date, start_clock = split_timestamp(start_time)
            end_date, end_clock = split_timestamp(end_time)

            if start_date != target_date:
                continue

            loc = pv.get("location", {})
            visits.append({
                "segment_index": idx,
                "start_date": start_date,
                "start_time": start_clock,
                "end_date": end_date,
                "end_time": end_clock,
                "duration_minutes": duration_minutes(start_time, end_time),
                "latitude": e7_to_float(loc.get("latitudeE7")),
                "longitude": e7_to_float(loc.get("longitudeE7")),
                "place_id": loc.get("placeId", ""),
                "name": loc.get("name", ""),
                "address": loc.get("address", ""),
                "semantic_type": loc.get("semanticType", ""),
                "visit_probability": pv.get("visitConfidence", ""),
                "candidate_probability": loc.get("calibratedProbability", ""),
                "hierarchy_level": "",
            })

        if "activitySegment" in obj:
            seg = obj.get("activitySegment", {})
            duration = seg.get("duration", {})
            start_time = duration.get("startTimestamp", "")
            end_time = duration.get("endTimestamp", "")
            start_date, start_clock = split_timestamp(start_time)
            end_date, end_clock = split_timestamp(end_time)

            if start_date == target_date:
                start_loc = seg.get("startLocation", {})
                end_loc = seg.get("endLocation", {})

                activities.append({
                    "segment_index": idx,
                    "start_date": start_date,
                    "start_time": start_clock,
                    "end_date": end_date,
                    "end_time": end_clock,
                    "duration_minutes": duration_minutes(start_time, end_time),
                    "start_latitude": e7_to_float(start_loc.get("latitudeE7")),
                    "start_longitude": e7_to_float(start_loc.get("longitudeE7")),
                    "end_latitude": e7_to_float(end_loc.get("latitudeE7")),
                    "end_longitude": e7_to_float(end_loc.get("longitudeE7")),
                    "distance_meters": seg.get("distance", ""),
                    "activity_type": seg.get("activityType", ""),
                    "activity_confidence": seg.get("confidence", ""),
                    "travel_mode": seg.get("waypointPath", {}).get("travelMode", ""),
                })

            raw_points = seg.get("simplifiedRawPath", {}).get("points", [])
            for point_idx, pt in enumerate(raw_points):
                point_date, point_time = split_timestamp(pt.get("timestamp", ""))
                if point_date != target_date:
                    continue

                points.append({
                    "segment_index": idx,
                    "point_index": point_idx,
                    "date": point_date,
                    "time": point_time,
                    "latitude": e7_to_float(pt.get("latE7")),
                    "longitude": e7_to_float(pt.get("lngE7")),
                    "accuracy_meters": pt.get("accuracyMeters", ""),
                    "source": "",
                    "device_tag": "",
                })

            waypoint_points = seg.get("waypointPath", {}).get("waypoints", [])
            for point_idx, pt in enumerate(waypoint_points):
                if start_date != target_date:
                    continue

                points.append({
                    "segment_index": idx,
                    "point_index": f"waypoint_{point_idx}",
                    "date": start_date,
                    "time": "",
                    "latitude": e7_to_float(pt.get("latE7")),
                    "longitude": e7_to_float(pt.get("lngE7")),
                    "accuracy_meters": "",
                    "source": "waypointPath",
                    "device_tag": "",
                })

    return visits, activities, points, []


def main():
    filename = input("Enter JSON filename (example: Timeline.json, Records.json, semantic.json): ").strip()
    target_date = input("Enter date to export (YYYY-MM-DD): ").strip()

    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        print("ERROR: Date must be in YYYY-MM-DD format.")
        return

    input_path = Path(filename)
    if not input_path.exists():
        print(f"ERROR: File not found: {filename}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    format_type = detect_format(data)

    if format_type == "new_timeline":
        visits, activities, points, record_points = process_new_timeline(data, target_date)
    elif format_type == "records":
        visits, activities, points, record_points = process_records(data, target_date)
    elif format_type == "old_semantic":
        visits, activities, points, record_points = process_old_semantic(data, target_date)
    else:
        print("ERROR: Unrecognized JSON format.")
        print("Supported formats: Timeline.json, Records.json, old semantic timeline JSON")
        return

    if visits:
        write_csv(
            f"day_visits_{target_date}.csv",
            [
                "segment_index",
                "start_date",
                "start_time",
                "end_date",
                "end_time",
                "duration_minutes",
                "latitude",
                "longitude",
                "place_id",
                "name",
                "address",
                "semantic_type",
                "visit_probability",
                "candidate_probability",
                "hierarchy_level",
            ],
            visits,
        )

    if activities:
        write_csv(
            f"day_activities_{target_date}.csv",
            [
                "segment_index",
                "start_date",
                "start_time",
                "end_date",
                "end_time",
                "duration_minutes",
                "start_latitude",
                "start_longitude",
                "end_latitude",
                "end_longitude",
                "distance_meters",
                "activity_type",
                "activity_confidence",
                "travel_mode",
            ],
            activities,
        )

    if points:
        write_csv(
            f"day_timeline_points_{target_date}.csv",
            [
                "segment_index",
                "point_index",
                "date",
                "time",
                "latitude",
                "longitude",
                "accuracy_meters",
                "source",
                "device_tag",
            ],
            points,
        )

    if record_points:
        write_csv(
            f"day_records_points_{target_date}.csv",
            [
                "record_index",
                "date",
                "time",
                "latitude",
                "longitude",
                "accuracy_meters",
                "source",
                "device_tag",
                "activity_type",
                "activity_confidence",
            ],
            record_points,
        )

    print(f"Detected format: {format_type}")
    print("Done.")
    print(f"Visits: {len(visits)}")
    print(f"Activities: {len(activities)}")
    print(f"Timeline points: {len(points)}")
    print(f"Record points: {len(record_points)}")


if __name__ == "__main__":
    main()