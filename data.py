import os
import json
import sqlite3
import logging
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
    if not os.path.exists(DATA_FILE):
        return default_financial_data.copy()

    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    data.setdefault("alokasi", {})
    for key, default_val in default_financial_data["alokasi"].items():
        data["alokasi"].setdefault(key, default_val)

    data.setdefault("sales", {})
    for channel, default_val in default_financial_data["sales"].items():
        if channel not in data["sales"]:
            data["sales"][channel] = default_val.copy()
        else:
            data["sales"][channel].setdefault("wallet", default_val["wallet"])

    data.setdefault("history", {})
    return data

def save_data(data_obj):
    with open(DATA_FILE, "w") as f:
        json.dump(data_obj, f, indent=4)

def run_migrations(conn):
    """Sistem Migrasi Database Internal"""
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY
        )
    ''')
    
    cursor.execute('SELECT MAX(version) FROM schema_migrations')
    result = cursor.fetchone()[0]
    current_version = result if result is not None else 0

    migrations = [
        # Versi 1: Struktur awal tabel invoices
        (1, '''
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_id INTEGER PRIMARY KEY,
                ref_number TEXT,
                contact_name TEXT,
                amount REAL DEFAULT 0,
                products TEXT,
                created_time TEXT,
                raw_data TEXT
            )
        '''),
        
        # Versi 2: Penambahan kolom updated_at untuk Sync Kledo
        (2, '''
            ALTER TABLE invoices ADD COLUMN updated_at TEXT
        '''),
        
        # Versi 3: Pembuatan tabel peak_analytics
        (3, '''
            CREATE TABLE IF NOT EXISTS peak_analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_type TEXT NOT NULL,
                period_key TEXT UNIQUE NOT NULL,
                total_transactions INTEGER DEFAULT 0,
                total_omzet REAL DEFAULT 0.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''),

        # Versi 4: Tabel relasional terpisah untuk item produk di setiap invoice
        (4, '''
            CREATE TABLE IF NOT EXISTS invoice_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER,
                product_name TEXT,
                qty REAL DEFAULT 1,
                price REAL DEFAULT 0,
                subtotal REAL DEFAULT 0,
                FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id) ON DELETE CASCADE
            )
        ''')
    ]
    
    for version, query in migrations:
        if version > current_version:
            try:
                cursor.execute(query)
                cursor.execute('INSERT INTO schema_migrations (version) VALUES (?)', (version,))
                conn.commit()
                logging.info(f"✅ DB Migration: Versi {version} berhasil dijalankan.")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    cursor.execute('INSERT INTO schema_migrations (version) VALUES (?)', (version,))
                    conn.commit()
                else:
                    raise e

def init_db():
    conn = sqlite3.connect('kledo_invoices.db')
    # Mengaktifkan dukungan Foreign Key pada SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    run_migrations(conn)
    return conn

financial_data = load_data()