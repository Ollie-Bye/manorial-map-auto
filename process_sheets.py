import csv
import json
import re
import urllib.request

GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR-EZVrt4IOI6M5d3DQVPSCcQMHQSmZPot7DYWZLDzKRoIhCF0Z55nG2zJJ5C_2l4RKYESXWDhtmU8G/pub?gid=664764410&single=true&output=csv"

def parse_dated_cell(cell_value, default_end=1922):
    """
    Parses multi-line cells formatted as:
    '1547 Robert Turberville\n1559 Thomas Turberville'
    Calculates start and end bounds based on the next entry's date.
    """
    if not cell_value:
        return []
        
    lines = [l.strip() for l in cell_value.split("\n") if l.strip()]
    parsed = []
    
    for line in lines:
        match = re.match(r'^(\d{4})\s+(.*)$', line)
        if match:
            year = int(match.group(1))
            val = match.group(2).strip()
            parsed.append({"year": year, "value": val})
        else:
            parsed.append({"year": None, "value": line})

    records = []
    for i, entry in enumerate(parsed):
        start_yr = entry["year"]
        val = entry["value"]
        
        if val.lower() in ["[none]", "none", "-"]:
            val = None  # Explicitly mark as unheld/vacant

        if start_yr is None:
            continue
            
        # End year is one year prior to next entry's start year, or default_end for last item
        if i + 1 < len(parsed) and parsed[i + 1]["year"] is not None:
            end_yr = parsed[i + 1]["year"] - 1
        else:
            end_yr = default_end
            
        records.append({
            "start": start_yr,
            "end": end_yr,
            "value": val
        })
        
    return records

def parse_units_sheet(csv_url):
    spatial_units = []
    temporal_records = {}
    county_records = []
    unit_county_lookup = {}

    req = urllib.request.Request(csv_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        lines = [line.decode('utf-8-sig') for line in response.readlines()]

    reader = csv.reader(lines)
    rows = list(reader)

    header_idx = -1
    for candidate_idx in [1, 2, 0]:
        if candidate_idx < len(rows):
            cleaned_row = ["".join(e for e in c.lower() if e.isalnum()) for c in rows[candidate_idx] if c]
            if any(h in cleaned_row for h in ["sid", "unit", "sgeometry", "lord"]):
                header_idx = candidate_idx
                break

    if header_idx == -1:
        header_idx = 1

    raw_headers = [c.strip() for c in rows[header_idx]]
    norm_headers = ["".join(e for e in h.lower() if e.isalnum()) for h in raw_headers]
    col_map = {name: idx for idx, name in enumerate(norm_headers) if name}
    data_rows = rows[header_idx + 1:]

    def get_val(row, *keys):
        for key in keys:
            norm_key = "".join(e for e in key.lower() if e.isalnum())
            idx = col_map.get(norm_key)
            if idx is not None and idx < len(row):
                val = row[idx].strip()
                if val:
                    return val
        return ""

    unit_tenure_lookup = {}

    for row in data_rows:
        if not row or not any(row):
            continue

        unit_name = get_val(row, "unit")
        historic_county = get_val(row, "historiccounty", "county") or "dorset"
        s_id = get_val(row, "sid")

        if not s_id:
            continue

        display_name = unit_name
        prefix = "Honour of" if s_id.startswith("hon_") else ("Duchy of" if s_id.startswith("duc_") else "Manor of")
        unit_type = "seigneurial"

        unit_county_lookup[s_id] = historic_county.lower().strip()

        s_geom_raw = get_val(row, "sgeometry")
        geom_entries = parse_dated_cell(s_geom_raw)
        lord_entries = parse_dated_cell(get_val(row, "lord"))
        overlord_entries = parse_dated_cell(get_val(row, "overlord"))
        lord_2nd_entries = parse_dated_cell(get_val(row, "lord2ndmoiety", "lord2nd"))
        overlord_2nd_entries = parse_dated_cell(get_val(row, "overlord2ndmoiety", "overlord2nd"))

        default_geom = geom_entries[0]["value"] if geom_entries and geom_entries[0]["value"] else f"{s_id}_01"

        spatial_units.append({
            "unit_id": s_id,
            "display_name": display_name,
            "display_prefix": prefix,
            "type": unit_type,
            "default_geometry": default_geom
        })

        manor_records = []
        lord_raw = get_val(row, "lord")
        tied_match = re.search(r"tied\s+to\s+([a-z0-9_]+)", lord_raw, re.IGNORECASE)

        if tied_match:
            target_id = tied_match.group(1)
            manor_records.append({"tied_to": target_id, "type": "link"})
        else:
            # Drive timeline primarily by Lord entries if available, otherwise S-Geometry
            timeline_drivers = lord_entries if lord_entries else geom_entries

            for l_item in (timeline_drivers or [{"start": 1066, "end": 1922, "value": ""}]):
                start_yr = l_item["start"] if l_item["start"] is not None else 1066
                end_yr = l_item["end"]
                lord_val = l_item["value"] if l_item["value"] is not None else ""

                # Match active geometry file for this date range
                geom_val = next((g["value"] for g in geom_entries if g["value"] and g["start"] <= start_yr <= g["end"]), default_geom)
                overlord_val = next((o["value"] for o in overlord_entries if o["value"] and o["start"] <= start_yr <= o["end"]), "")
                lord_2nd_val = next((l2["value"] for l2 in lord_2nd_entries if l2["value"] and l2["start"] <= start_yr <= l2["end"]), "")
                overlord_2nd_val = next((o2["value"] for o2 in overlord_2nd_entries if o2["value"] and o2["start"] <= start_yr <= o2["end"]), "")

                record = {
                    "start": start_yr,
                    "end": end_yr,
                    "lord": lord_val,
                    "overlord": overlord_val,
                    "geometry_file": geom_val,
                    "prefix": prefix,
                    "type": unit_type,
                    "name": display_name
                }

                if lord_2nd_val:
                    record["lord_2nd_moiety"] = lord_2nd_val
                if overlord_2nd_val:
                    record["overlord_2nd_moiety"] = overlord_2nd_val

                manor_records.append(record)

        temporal_records[s_id] = manor_records
        unit_tenure_lookup[s_id] = manor_records

    # Pass 2: Resolve "Tied to" inherited links
    for uid, records in temporal_records.items():
        if records and records[0].get("type") == "link":
            target_id = records[0]["tied_to"]
            if target_id in unit_tenure_lookup:
                spatial_info = next((s for s in spatial_units if s["unit_id"] == uid), {})
                inherited = []
                for rec in unit_tenure_lookup[target_id]:
                    r = dict(rec)
                    r["prefix"] = spatial_info.get("display_prefix", rec.get("prefix"))
                    r["type"] = spatial_info.get("type", rec.get("type"))
                    r["name"] = spatial_info.get("display_name", rec.get("name"))
                    inherited.append(r)
                temporal_records[uid] = inherited

    return {
        "spatial": spatial_units,
        "temporal": temporal_records,
        "county_lookup": unit_county_lookup,
        "counties": county_records
    }

if __name__ == "__main__":
    dataset = parse_units_sheet(GOOGLE_SHEET_CSV_URL)
    
    temporal_records = dataset["temporal"]
    unit_county_lookup = dataset["county_lookup"]

    county_grouped_history = {}

    for uid, records in temporal_records.items():
        county_name = unit_county_lookup.get(uid, "dorset")
        if county_name not in county_grouped_history:
            county_grouped_history[county_name] = {}
        county_grouped_history[county_name][uid] = records

    if "dorset" not in county_grouped_history:
        county_grouped_history["dorset"] = {}

    generated_files = []
    for county_name, history_data in county_grouped_history.items():
        filename = f"{county_name}_history.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(history_data, f, indent=2)
        generated_files.append(filename)
        print(f"Generated {filename} containing {len(history_data)} unit records.")

    print("Pipeline complete! Generated datasets:", ", ".join(generated_files))
