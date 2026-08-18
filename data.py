import os
import json
import sqlite3
from config import DATA_FILE

default_financial_data = {
    "date": "17 Aug 26",
    "seabank": 0,
    "jago": 0,
    "cash_tunai": 0,
    "alokasi": {
        "Gaji Akmal": 0, "Gaji Owner": 0, "Sewa Lapak": 0,
        "Sewa Kontainer": 0, "BMT": 0, "Cabang 2": 0, "Saving": 0,
    },
    "sales": {
        "offline": {"nota": 0, "porsi": 0, "rupiah": 0, "wallet": "cash_tunai"},
        "shopeefood": {"nota": 0, "porsi": 0, "rupiah": 0, "wallet": "seabank"},
        "gofood": {"nota": 0, "porsi": 0, "rupiah": 0, "wallet": "seabank"},
        "grabfood": {"nota": 0, "porsi": 0, "rupiah": 0, "wallet": "jago"},
    },
    "history": {}
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            if "alokasi" in data:
                for key, default_val in default_financial_data["alokasi"].items():
                    if key not in data["alokasi"]:
                        data["alokasi"][key] = default_val
            if "sales" not in data:
                data["sales"] = default_financial_data["sales"]
            else:
                for channel, default_val in default_financial_data["sales"].items():
                    if channel not in data["sales"]:
                        data["sales"][channel] = default_val
                    elif "wallet" not in data["sales"][channel]:
                        data["sales"][channel]["wallet"] = default_val["wallet"]
            if "history" not in data:
                data["history"] = {}
            return data
    return default_financial_data.copy()

def save_data(data_obj):
    with open(DATA_FILE, "w") as f:
        json.dump(data_obj, f, indent=4)

def init_db():
    conn = sqlite3.connect('kledo_invoices.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_id INTEGER PRIMARY KEY,
            ref_number TEXT,
            contact_name TEXT,
            amount REAL,
            products TEXT,
            created_time TEXT,
            raw_data TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS peak_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_type TEXT,          -- 'HOUR' atau 'DAY'
            period_key TEXT,           -- Contoh: '08' untuk jam 08:00 atau 'Senin'
            total_transactions INTEGER,
            total_omzet REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    return conn

financial_data = load_data()