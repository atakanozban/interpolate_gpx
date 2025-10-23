#!/usr/bin/env python3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from copy import deepcopy

NS = {"gpx": "http://www.topografix.com/GPX/1/1"}
ET.register_namespace("", NS["gpx"])

def parse_time(t: str) -> datetime:
    # GPX ISO8601 times end with Z (UTC)
    return datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(timezone.utc)

def fmt_time(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def get_ele(tp):
    el = tp.find("gpx:ele", NS)
    if el is not None and el.text not in (None, ""):
        try:
            return float(el.text)
        except ValueError:
            return None
    return None

def set_ele(tp, value):
    if value is None:
        return
    el = tp.find("gpx:ele", NS)
    if el is None:
        el = ET.SubElement(tp, f"{{{NS['gpx']}}}ele")
    el.text = f"{value:.2f}"

def interpolate_segment(seg):
    """Return a NEW <trkseg> with gaps >1s filled at 1s steps (linear lat/lon/ele)."""
    pts = seg.findall("gpx:trkpt", NS)
    if len(pts) < 2:
        return deepcopy(seg)

    new_seg = ET.Element(f"{{{NS['gpx']}}}trkseg")
    inserted_total = 0
    gaps = 0

    for i in range(len(pts) - 1):
        cur, nxt = pts[i], pts[i + 1]
        new_seg.append(deepcopy(cur))

        t1_el = cur.find("gpx:time", NS)
        t2_el = nxt.find("gpx:time", NS)
        if t1_el is None or t2_el is None or not t1_el.text or not t2_el.text:
            continue

        t1, t2 = parse_time(t1_el.text), parse_time(t2_el.text)
        dt = int((t2 - t1).total_seconds())
        if dt <= 1:
            continue

        gaps += 1
        lat1, lon1 = float(cur.get("lat")), float(cur.get("lon"))
        lat2, lon2 = float(nxt.get("lat")), float(nxt.get("lon"))
        ele1, ele2 = get_ele(cur), get_ele(nxt)

        # Fill each missing second with linear interpolation
        for s in range(1, dt):
            alpha = s / dt
            lat = lat1 + (lat2 - lat1) * alpha
            lon = lon1 + (lon2 - lon1) * alpha
            ele = None if (ele1 is None or ele2 is None) else (ele1 + (ele2 - ele1) * alpha)

            new_tp = ET.Element(f"{{{NS['gpx']}}}trkpt", attrib={
                "lat": f"{lat:.7f}",
                "lon": f"{lon:.7f}",
            })
            if ele is not None:
                ele_el = ET.SubElement(new_tp, f"{{{NS['gpx']}}}ele")
                ele_el.text = f"{ele:.2f}"
            time_el = ET.SubElement(new_tp, f"{{{NS['gpx']}}}time")
            time_el.text = fmt_time(t1 + timedelta(seconds=s))

            new_seg.append(new_tp)
            inserted_total += 1

    # append last original point
    new_seg.append(deepcopy(pts[-1]))
    return new_seg

def main(in_path, out_path):
    tree = ET.parse(in_path)
    root = tree.getroot()

    # keep original structure, only replace each trkseg content with interpolated version
    changed = False
    for trk in root.findall(".//gpx:trk", NS):
        for seg in trk.findall("gpx:trkseg", NS):
            new_seg = interpolate_segment(seg)
            if new_seg is not None:
                trk.remove(seg)
                trk.append(new_seg)
                changed = True

    if not changed:
        print("No <trkseg> found or no changes made.", file=sys.stderr)

    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"Interpolated GPX saved to: {out_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python interpolate_gpx.py input.gpx output.gpx", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
