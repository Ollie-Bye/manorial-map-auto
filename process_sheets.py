import csv
import json
import re
import urllib.request

# Published Google Sheets CSV URL for "Units" tab
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/109Dg1l11_7gnsE84UVXAFvfl8qdDievI_FiR2P-Xcx8/gviz/tq?tqx=out:csv&gid=664764410"

def parse_dated_cell(cell_value, default_end=1922):
    """
    Parses multi-line cells formatted as:
    '1066 bere_01\n1380 [None]'
    Returns a list of dicts with start, end, and value.
    """
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
        
        # If explicitly marked as [None] or None, the unit/geometry ceases to exist from this date
        if val.lower() in ["[none]", "none", "-"]:
            continue

        if start_yr is None:
            continue
            
        # Determine end year: one year prior to next entry's start year, or default_end
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

    # 1. Locate primary header row dynamically
    header_idx = -1
    for idx, row in enumerate(rows[:15]):
        cleaned_row = [re.sub(r'[\s_\-]', '', c.lower().strip()) for c in row if c]
        if "manorid" in cleaned_row or "id" in cleaned_row or "unitname" in cleaned_row:
            header_idx = idx
            break

    if header_idx == -1:
        header_idx = 2

    raw_headers = [c.strip() for c in rows[header_idx]]
    norm_headers = [re.sub(r'[\s_\-]', '', h.lower()) for h in raw_headers]
    col_map = {name: idx for idx, name in enumerate(norm_headers) if name}
    data_rows = rows[header_idx + 1:]

    def get_val(row, *keys):
        for key in keys:
            norm_key = re.sub(r'[\s_\-]', '', key.lower())
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

        unit_name = get_val(row, "unitname", "name")
        historic_county = get_val(row, "historiccounty", "county") or "dorset"

        manor_id = get_val(row, "manorid")
        parish_id = get_val(row, "parishid")

        primary_id = manor_id or parish_id
        if not primary_id:
            continue

        # --- SEIGNEURIAL / MANOR PORTION ---
        if manor_id:
            display_name = unit_name
            prefix = "Honour of" if "hon_" in manor_id else ("Duchy of" if "duc_" in manor_id else "Manor of")
            unit_type = "seigneurial"

            unit_county_lookup[manor_id] = historic_county.lower().strip()

            # Parse dated attributes targeting "S-Geometry"
            s_geom_raw = get_val(row, "sgeometry", "sgeom", "manorgeometry")
            geom_entries = parse_dated_cell(s_geom_raw)
            lord_entries = parse_dated_cell(get_val(row, "lord"))
            overlord_entries = parse_dated_cell(get_val(row, "overlord"))
            lord_2nd_entries = parse_dated_cell(get_val(row, "lord2ndmoiety", "lord2nd"))
            overlord_2nd_entries = parse_dated_cell(get_val(row, "overlord2ndmoiety", "overlord2nd"))

            default_geom = geom_entries[0]["value"] if geom_entries else f"{manor_id}_01"

            spatial_units.append({
                "unit_id": manor_id,
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
                # Build time segments based on S-Geometry date ranges
                for g_item in (geom_entries or [{"start": 1066, "end": 1922, "value": default_geom}]):
                    start_yr = g_item["start"]
                    end_yr = g_item["end"]
                    geom_file = g_item["value"]

                    lord_val = next((l["value"] for l in lord_entries if l["start"] <= start_yr <= l["end"]), "")
                    overlord_val = next((o["value"] for o in overlord_entries if o["start"] <= start_yr <= o["end"]), "")
                    lord_2nd_val = next((l2["value"] for l2 in lord_2nd_entries if l2["start"] <= start_yr <= l2["end"]), "")
                    overlord_2nd_val = next((o2["value"] for o2 in overlord_2nd_entries if o2["start"] <= start_yr <= o2["end"]), "")

                    record = {
                        "start": start_yr,
                        "end": end_yr,
                        "lord": lord_val,
                        "overlord": overlord_val,
                        "geometry_file": geom_file,
                        "prefix": prefix,
                        "type": unit_type,
                        "name": display_name
                    }

                    if lord_2nd_val:
                        record["lord_2nd_moiety"] = lord_2nd_val
                    if overlord_2nd_val:
                        record["overlord_2nd_moiety"] = overlord_2nd_val

                    manor_records.append(record)

            temporal_records[manor_id] = manor_records
            unit_tenure_lookup[manor_id] = manor_records

        # --- ADMINISTRATIVE / PARISH PORTION ---
        if parish_id:
            display_name = unit_name
            prefix = "Parish of"
            unit_type = "administrative"
            
            # Parse dated attributes targeting "A-Geometry"
            a_geom_raw = get_val(row, "ageometry", "ageom", "parishgeometry") or f"{parish_id}_01"
            parish_geom_entries = parse_dated_cell(a_geom_raw)
            parish_geom = parish_geom_entries[0]["value"] if parish_geom_entries else a_geom_raw

            unit_county_lookup[parish_id] = historic_county.lower().strip()

            spatial_units.append({
                "unit_id": parish_id,
                "display_name": display_name,
                "display_prefix": prefix,
                "type": unit_type,
                "default_geometry": parish_geom
            })

            temporal_records[parish_id] = [{
                "start": parish_geom_entries[0]["start"] if parish_geom_entries else 1066,
                "end": parish_geom_entries[-1]["end"] if parish_geom_entries else 1922,
                "lord": "N/A",
                "overlord": "",
                "geometry_file": parish_geom,
                "prefix": prefix,
                "type": unit_type,
                "name": display_name
            }]

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

    generated_files = []
    for county_name, history_data in county_grouped_history.items():
        filename = f"{county_name}_history.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(history_data, f, indent=2)
        generated_files.append(filename)
        print(f"Generated {filename} containing {len(history_data)} unit records.")

    print("Pipeline complete! Generated datasets:", ", ".join(generated_files))
