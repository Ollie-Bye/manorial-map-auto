import csv
import json
import re

def clean_text(val):
    if not val:
        return ""
    return val.strip()

def parse_units_sheet(csv_filepath):
    spatial_units = []
    temporal_records = {}
    county_records = []

    with open(csv_filepath, mode='r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)

    # 1. Locate primary header row (skipping top merged headers)
    header_idx = -1
    for idx, row in enumerate(rows[:10]):
        if "unit_id" in [c.lower().strip() for c in row if c]:
            header_idx = idx
            break

    if header_idx == -1:
        raise ValueError("Could not find header row containing 'unit_id'")

    headers = [c.lower().strip() for c in rows[header_idx]]
    data_rows = rows[header_idx + 1:]

    # Map column names to index positions
    col_map = {name: idx for idx, name in enumerate(headers) if name}

    unit_tenure_lookup = {}  # Store tenure timelines for "Tied to" resolution

    # First Pass: Parse all explicit units and their temporal rows
    for row in data_rows:
        if not row or not any(row):
            continue

        def get_val(col_name):
            idx = col_map.get(col_name)
            if idx is not None and idx < len(row):
                return row[idx].strip()
            return ""

        unit_id = get_val("unit_id")
        if not unit_id:
            continue

        # Extract Spatial Attributes
        display_name = get_val("display_name")
        display_prefix = get_val("display_prefix")
        unit_type = get_val("type")
        default_geometry = get_val("default_geometry") or f"{unit_id}_01"

        # Check if unit is a County
        if unit_type.lower() == "county":
            county_records.append({
                "county_id": unit_id,
                "display_name": display_name,
                "period": get_val("period") or "ancient",
                "start": int(get_val("start") or 1066),
                "end": int(get_val("end") or 1922),
                "geometry": default_geometry
            })
            continue

        # Add to Spatial list
        spatial_units.append({
            "unit_id": unit_id,
            "display_name": display_name,
            "display_prefix": display_prefix,
            "type": unit_type,
            "default_geometry": default_geometry
        })

        # Process Temporal (Seigneurial / Tenure) Data
        # Multi-line cell handling: split on \n
        dates_lines = [l.strip() for l in get_val("dates").split("\n") if l.strip()]
        lord_lines = [l.strip() for l in get_val("lord_name").split("\n")]
        title_lines = [l.strip() for l in get_val("lord_title").split("\n")]
        family_lines = [l.strip() for l in get_val("lord_family").split("\n")]
        overlord_lines = [l.strip() for l in get_val("overlord").split("\n")]
        moiety_lines = [l.strip() for l in get_val("moiety").split("\n")]
        geometry_lines = [l.strip() for l in get_val("geometry_override").split("\n")]

        unit_records = []

        # Check for "Tied to [unit_id]" directive
        tied_match = re.search(r"tied\s+to\s+([a-z0-9_]+)", get_val("lord_name"), re.IGNORECASE)
        if tied_match:
            target_unit_id = tied_match.group(1)
            unit_records.append({
                "tied_to": target_unit_id,
                "type": "link"
            })
        else:
            for i, date_str in enumerate(dates_lines):
                # Parse start/end years from formats like "1259-1350" or "1259"
                years = re.findall(r'\d{4}', date_str)
                if not years:
                    continue
                start_yr = int(years[0])
                end_yr = int(years[1]) if len(years) > 1 else start_yr

                # Safe indexing for multi-line cells
                lord = lord_lines[i] if i < len(lord_lines) else ""
                title = title_lines[i] if i < len(title_lines) else ""
                family = family_lines[i] if i < len(family_lines) else ""
                overlord = overlord_lines[i] if i < len(overlord_lines) else ""
                moiety = moiety_lines[i] if i < len(moiety_lines) else ""
                geom_override = geometry_lines[i] if i < len(geometry_lines) else ""

                # Combine Lord Name + Title
                full_lord = lord
                if title:
                    full_lord += f", {title}" if full_lord else title

                unit_records.append({
                    "start": start_yr,
                    "end": end_yr,
                    "lord": full_lord,
                    "lord_family": family,
                    "overlord": overlord,
                    "moiety": moiety,
                    "geometry_file": geom_override or default_geometry,
                    "prefix": display_prefix,
                    "type": unit_type
                })

        temporal_records[unit_id] = unit_records
        unit_tenure_lookup[unit_id] = unit_records

    # Second Pass: Resolve "Tied to" references
    for uid, records in temporal_records.items():
        if records and records[0].get("type") == "link":
            target_id = records[0]["tied_to"]
            if target_id in unit_tenure_lookup:
                # Inherit target's records, retaining local prefix/type
                spatial_info = next((s for s in spatial_units if s["unit_id"] == uid), {})
                inherited = []
                for rec in unit_tenure_lookup[target_id]:
                    r = dict(rec)
                    r["prefix"] = spatial_info.get("display_prefix", rec.get("prefix"))
                    r["type"] = spatial_info.get("type", rec.get("type"))
                    inherited.append(r)
                temporal_records[uid] = inherited

    return {
        "spatial": spatial_units,
        "temporal": temporal_records,
        "counties": county_records
    }

# Execute parsing and save outputs
if __name__ == "__main__":
    dataset = parse_units_sheet("units_raw.csv")
    
    with open("dorset_history.json", "w", encoding="utf-8") as f:
        json.dump(dataset["temporal"], f, indent=2)
        
    with open("counties.json", "w", encoding="utf-8") as f:
        json.dump(dataset["counties"], f, indent=2)

    print("Data successfully transformed into production JSON datasets!")
