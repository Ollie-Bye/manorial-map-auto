# Historical Manorial Map Architecture

An automated, GIS-enabled Leaflet.js web application that transforms editorial Google Sheets into temporal historical county datasets.

## Repository Structure

```text
├── .github/workflows/sync.yml   # GitHub Actions workflow (runs process_sheets.py daily / on dispatch)
├── data/
│   └── dorset/
│       └── shapes.json          # GeoJSON boundaries for Dorset units
├── index.html                   # Leaflet.js frontend application
├── process_sheets.py            # Python ETL script (Google Sheets CSV -> JSON)
├── dorset_history.json          # Generated temporal data for Dorset units
└── counties.json                # Generated county index dataset
```

## Data Pipeline Flow
```text
Editorial data is maintained in a published Google Sheet ("Units" tab).
sync.yml triggers process_sheets.py.
process_sheets.py fetches the CSV, handles multi-line attributes, resolves seigneurial inheritance (tied to <unit_id>), and outputs county-grouped JSON files (e.g., dorset_history.json).
index.html fetches {county}_history.json and matches spatial records via unit_id
