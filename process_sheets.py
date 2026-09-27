import csv
import json
import re
import urllib.request

# Replace this string with your actual "Publish to web" CSV URL for the Units tab
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR-EZVrt4IOI6M5d3DQVPSCcQMHQSmZPot7DYWZLDzKRoIhCF0Z55nG2zJJ5C_2l4RKYESXWDhtmU8G/pub?gid=664764410&single=true&output=csv"

def fetch_and_process():
    # 1. Download latest CSV from Google Sheets
    req = urllib.request.Request(GOOGLE_SHEET_CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        lines = [line.decode('utf-8-sig') for line in response.readlines()]

    reader = csv.reader(lines)
    rows = list(reader)

    # (Insert the rest of the parsing logic from our previous process_sheets.py here)