import csv
import json
import re
import urllib.request

# Ensure this matches your "Publish to Web" CSV URL for the "Units" tab
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR-EZVrt4IOI6M5d3DQVPSCcQMHQSmZPot7DYWZLDzKRoIhCF0Z55nG2zJJ5C_2l4RKYESXWDhtmU8G/pub?gid=664764410&single=true&output=csv"

def parse_units_sheet(csv_url):
    spatial_units = []
    temporal_records = {}
    county_records = []

    # 1. Fetch CSV content directly from Google Sheets
    req = urllib.request.Request(csv_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        lines = [line.decode('utf-8-sig') for line in response.readlines()]

    reader = csv.reader(lines)
    rows = list(reader)

    # 2. Find header row containing "ID" or "Name"
    header_idx = -1
    for idx, row in enumerate(rows[:15]):
        cleaned_row = [c.strip().lower() for c in row if c]
        if "id" in cleaned_row or "name" in cleaned_row:
            header_idx = idx
            break

    if header_idx == -1:
        # Fallback to row 2 if header detection fails
        header_idx = 2

    headers = [c.strip().lower() for c in rows[header_idx]]
    data_rows = rows[header_idx + 1:]

    # Helper function to get value by absolute column index (0-based: A=0, B=1, C=2, D=3, etc.)
    def get_col(row, idx):
        if idx < len(row):
            return row[idx].strip()
        return ""

    unit_tenure_lookup = {}

    for row in data_rows:
        if not row or not any(row):
            continue

        unit_name = get_col(row, 0) # Col A: Unit Name (e.g. Bere Regis)

        # --- SEIGNEURIAL / MANOR PORTION (Col D: Manor ID) ---
        manor_id = get_col(row, 3) # Col D is index 3
        if manor_id:
            display_name = unit_name
            prefix = "Manor of"
            unit_type = "seigneurial"
            default_geom = f"{manor_id}_01"

            spatial_units.append({
                "unit_id": manor_id,
                "display_name": display_name,
                "display_prefix": prefix,
                "type": unit_type,
                "default_geometry": default_geom
            })

            # Multi-line cells for Manor attributes (adjust column indices if needed)
            dates_lines = [l.strip() for l in get_col(row, 4).split("\n") if l.strip()]   # Col E: Dates
            lord_lines = [l.strip() for l in get_col(row, 5).split("\n")]                # Col F: Lord
            title_lines = [l.strip() for l in get_col(row, 6).split("\n")]               # Col G: Title
            family_lines = [l.strip() for l in get_col(row, 7).split("\n")]              # Col H: Family
            overlord_lines = [l.strip() for l in get_col(row, 8).split("\n")]            # Col I: Overlord
            moiety_lines = [l.strip() for l in get_col(row, 9).split("\n")]              # Col J: Moiety
            geom_lines = [l.strip() for l in get_col(row, 10).split("\n")]               # Col K: Geom Override

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
        parish_id = get_col(row, 12) # Col M is index 12
        if parish_id:
            display_name = unit_name
            prefix = "Parish of"
            unit_type = "administrative"
            default_geom = f"{parish_id}_01"

            spatial_units.append({
                "unit_id": parish_id,
                "display_name": display_name,
                "display_prefix": prefix,
                "type": unit_type,
                "default_geometry": default_geom
            })

            # Basic administrative temporal record
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
        "counties": county_records
    }

if __name__ == "__main__":
    dataset = parse_units_sheet(GOOGLE_SHEET_CSV_URL)
    
    with open("dorset_history.json", "w", encoding="utf-8") as f:
        json.dump(dataset["temporal"], f, indent=2)
        
    with open("counties.json", "w", encoding="utf-8") as f:
        json.dump(dataset["counties"], f, indent=2)

    print("Data successfully fetched from Google Sheets and generated JSON files!")
