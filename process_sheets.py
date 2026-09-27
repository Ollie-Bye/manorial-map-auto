import csv
import json
import re
import urllib.request

# Ensure this matches your published "Units" tab CSV URL
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1v.../pub?gid=664764410&single=true&output=csv"

def parse_units_sheet(csv_url):
    spatial_units = []
    temporal_records = {}
    county_records = []
    unit_county_lookup = {}  # Tracks unit_id -> historic county

    # 1. Fetch CSV content directly from Google Sheets
    req = urllib.request.Request(csv_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        lines = [line.decode('utf-8-sig') for line in response.readlines()]

    reader = csv.reader(lines)
    rows = list(reader)

    # 2. Find header row
    header_idx = -1
    for idx, row in enumerate(rows[:15]):
        cleaned_row = [c.strip().lower() for c in row if c]
        if "id" in cleaned_row or "name" in cleaned_row:
            header_idx = idx
            break

    if header_idx == -1:
        header_idx = 2

    headers = [c.strip().lower() for c in rows[header_idx]]
    data_rows = rows[header_idx + 1:]

    def get_col(row, idx):
        if idx < len(row):
            return row[idx].strip()
        return ""

    unit_tenure_lookup = {}

    # Pass 1: Parse all units and collect county metadata
    for row in data_rows:
        if not row or not any(row):
            continue

        unit_name = get_col(row, 0)      # Col A: Unit Name
        historic_county = get_col(row, 2) # Col C: Historic County (e.g. Dorset, Lancashire)
        if not historic_county:
            historic_county = "dorset"

        # --- SEIGNEURIAL / MANOR PORTION (Col D: Manor ID) ---
        manor_id = get_col(row, 3) # Col D
        if manor_id:
            display_name = unit_name
            prefix = "Manor of"
            unit_type = "seigneurial"
            default_geom = f"{manor_id}_01"

            unit_county_lookup[manor_id] = historic_county.lower().strip()

            spatial_units.append({
                "unit_id": manor_id,
                "display_name": display_name,
                "display_prefix": prefix,
                "type": unit_type,
                "default_geometry": default_geom
            })

            dates_lines = [l.strip() for l in get_col(row, 4).split("\n") if l.strip()]
            lord_lines = [l.strip() for l in get_col(row, 5).split("\n")]
            title_lines = [l.strip() for l in get_col(row, 6).split("\n")]
            family_lines = [l.strip() for l in get_col(row, 7).split("\n")]
            overlord_lines = [l.strip() for l in get_col(row, 8).split("\n")]
            moiety_lines = [l.strip() for l in get_col(row, 9).split("\n")]
            geom_lines = [l.strip() for l in get_col(row, 10).split("\n")]

            manor_records = []
            tied_match = re.search(r"tied\s+to\s+([a-z0-9_]+)", get_col(row, 5), re.IGNORECASE)

            if tied_match:
                target_id = tied_match.group(1)
                manor_records.append({"tied_to": target_id, "type": "link"})
            else:
                for i, date_str in enumerate(dates_lines):
                    years = re.findall(r'\d{4}', date_str)
                    if not years:
                        continue
                    start_yr = int(years[0])
                    end_yr = int(years[1]) if len(years) > 1 else start_yr

                    lord = lord_lines[i] if i < len(lord_lines) else ""
                    title = title_lines[i] if i < len(title_lines) else ""
                    family = family_lines[i] if i < len(family_lines) else ""
                    overlord = overlord_lines[i] if i < len(overlord_lines) else ""
                    moiety = moiety_lines[i] if i < len(moiety_lines) else ""
                    geom_override = geom_lines[i] if i < len(geom_lines) else ""

                    full_lord = lord
                    if title:
                        full_lord += f", {title}" if full_lord else title

                    manor_records.append({
                        "start": start_yr,
                        "end": end_yr,
                        "lord": full_lord,
                        "lord_family": family,
                        "overlord": overlord,
                        "moiety": moiety,
                        "geometry_file": geom_override or default_geom,
                        "prefix": prefix,
                        "type": unit_type,
                        "name": display_name
                    })

            temporal_records[manor_id] = manor_records
            unit_tenure_lookup[manor_id] = manor_records

        # --- ADMINISTRATIVE / PARISH PORTION (Col M: Parish ID) ---
        parish_id = get_col(row, 12) # Col M
        if parish_id:
            display_name = unit_name
            prefix = "Parish of"
            unit_type = "administrative"
            default_geom = f"{parish_id}_01"

            unit_county_lookup[parish_id] = historic_county.lower().strip()

            spatial_units.append({
                "unit_id": parish_id,
                "display_name": display_name,
                "display_prefix": prefix,
                "type": unit_type,
                "default_geometry": default_geom
            })

            temporal_records[parish_id] = [{
                "start": 1066,
                "end": 1922,
                "lord": "N/A",
                "lord_family": "",
                "overlord": "",
                "moiety": "",
                "geometry_file": default_geom,
                "prefix": prefix,
                "type": unit_type,
                "name": display_name
            }]

    # Pass 2: Resolve "Tied to" inherited links globally across all counties
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

    # Pass 3: Group temporal records by county and write county JSON files
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

    with open("counties.json", "w", encoding="utf-8") as f:
        json.dump(dataset["counties"], f, indent=2)

    print("Pipeline complete! Generated datasets:", ", ".join(generated_files))
