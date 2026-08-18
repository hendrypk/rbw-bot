import json
import sqlite3
import requests
import logging
import os
import pandas as pd
from collections import Counter
from config import API_HOST, X_APP, EMAIL, PASSWORD, KLEDO_COOKIE_NAME, KLEDO_COOKIE_VALUE
from data import init_db

TEMP_JSON_FILE = "temp_invoices.json"

def create_kledo_session():
    """
    Membuat session Kledo menggunakan metode singleLogin 
    dengan payload JSON lengkap, custom headers, dan cookies.
    """
    session = requests.Session()
    login_url = f"{API_HOST}/authentication/singleLogin"
    
    # Payload lengkap sesuai panduan Postman/Script Anda
    payload = {
        "email": EMAIL,
        "password": PASSWORD,
        "remember_me": 1,
        "is_otp": 0,
        "use_jwt": 0,
        "include_init": 1,
        "apple_identity_token": None
    }
    
    headers = {
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'app-client': 'web',
        'X-App': X_APP
    }
    
    # Memasukkan cookie jika nama dan nilainya tersedia di .env
    cookies = {}
    if KLEDO_COOKIE_NAME and KLEDO_COOKIE_VALUE:
        cookies[KLEDO_COOKIE_NAME] = KLEDO_COOKIE_VALUE

    try:
        logging.info("Mengirim request login ke Kledo dengan payload & cookie...")
        response = session.post(login_url, json=payload, headers=headers, cookies=cookies, timeout=15)
        
        # Cek jika ada error HTTP (401, 500, dll)
        response.raise_for_status()
        res_data = response.json()
        
        logging.info("🎉 LOGIN BERHASIL!")
        
        # Mengambil access_token untuk request selanjutnya (seperti fetch invoices)
        access_token = res_data.get("data", {}).get("data", {}).get("access_token")
        
        if access_token:
            # Update header sesi agar request ke /finance/invoices menggunakan token yang valid
            session.headers.update({
                "Content-Type": "application/json",
                "Accept": "application/json",
                "app-client": "web",
                "X-App": X_APP,
                "Authorization": f"Bearer {access_token}"
            })
        else:
            # Jika Kledo menggunakan cookie untuk otorisasi, setel header dasar
            session.headers.update(headers)
            
        return session
        
    except requests.exceptions.HTTPError as err:
        logging.error(f"❌ Kledo Login HTTP Error {err.response.status_code}: {err.response.text}")
        return None
    except Exception as e:
        logging.error(f"❌ Kledo Login Error Lainnya: {e}")
        return None

def fetch_invoices_to_json(target_date):
    """Tahap 1: Login, Tarik data Kledo berdasarkan tanggal, simpan ke file JSON sementara."""
    session = create_kledo_session()
    if not session:
        return None, "❌ Gagal login ke Kledo. Periksa kembali email, password, atau cookie di file .env!"
    
    url = f"{API_HOST}/finance/invoices?date_from={target_date}&date_to={target_date}&contact_id=1&per_page=100"
    
    try:
        resp = session.get(url, headers={"Accept": "application/json", "X-App": X_APP}, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", {}).get("data", [])
        
        if not data:
            return None, f"⚠️ Tidak ada data invoice POS Customer untuk tanggal {target_date}."
            
        with open(TEMP_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        return len(data), None
    except Exception as e:
        return None, f"❌ Error API Kledo: {e}"

def insert_temp_json_to_db():
    """Tahap 2: Membaca file JSON sementara dan memasukkannya ke SQLite Database."""
    try:
        if not os.path.exists(TEMP_JSON_FILE):
            return 0, "⚠️ Data JSON sementara tidak ditemukan."
            
        with open(TEMP_JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        db_conn = init_db()
        cursor = db_conn.cursor()
        saved_count = 0
        
        for inv in data:
            contact = inv.get("contact", {})
            if contact.get("id") != 1 and contact.get("name") != "POS Customer":
                continue
                
            inv_id = inv.get("id")
            ref_number = inv.get("ref_number")
            c_name = contact.get("name")
            amount = inv.get("amount")
            created_at = inv.get("log", {}).get("action", {}).get("created_at") or inv.get("created_at") or inv.get("trans_date")
            
            items = inv.get("items", [])
            product_list = [f"{i.get('product_name')} (x{i.get('qty', 1)})" for i in items]
            products_str = ", ".join(product_list)
            raw_data_json = json.dumps(inv)
            
            cursor.execute('''
                INSERT OR REPLACE INTO invoices 
                (invoice_id, ref_number, contact_name, amount, products, created_time, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (inv_id, ref_number, c_name, amount, products_str, created_at, raw_data_json))
            
            saved_count += 1
            
        db_conn.commit()
        db_conn.close()
        
        os.remove(TEMP_JSON_FILE)
        return saved_count, None
    except Exception as e:
        return 0, f"❌ Error Database: {e}"

def analyze_peak_hours_from_db():
    """Tahap 3: Analisis Peak Hour & Peak Day menggunakan Pandas, lalu simpan ke database SQLite."""
    try:
        db_conn = init_db()
        query = "SELECT created_time, amount FROM invoices"
        df = pd.read_sql(query, db_conn)
        
        if df.empty or "created_time" not in df.columns:
            db_conn.close()
            return "⚠️ Database masih kosong atau kolom waktu tidak ditemukan."
            
        df['dt'] = pd.to_datetime(df['created_time'], errors='coerce')
        df = df.dropna(subset=['dt'])
        
        if df.empty:
            db_conn.close()
            return "⚠️ Tidak ada data waktu transaksi yang valid di database."
            
        df['hour'] = df['dt'].dt.hour
        df['day_name'] = df['dt'].dt.day_name()
        
        day_mapping = {
            'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
            'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu', 'Sunday': 'Minggu'
        }
        df['day_id'] = df['day_name'].map(day_mapping)
        
        # 1. Agregasi Peak Hour
        hour_summary = df.groupby('hour').agg(
            total_transaksi=('amount', 'count'),
            total_omzet=('amount', 'sum')
        ).reset_index()
        
        # 2. Agregasi Peak Day
        day_order = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
        day_summary = df.groupby('day_id').agg(
            total_transaksi=('amount', 'count'),
            total_omzet=('amount', 'sum')
        ).reindex(day_order).reset_index()
        
        cursor = db_conn.cursor()
        
        # Buat tabel penyimpanan peak analytics jika belum ada
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS peak_analytics (
                period_type TEXT,
                period_key TEXT PRIMARY KEY,
                total_transactions INTEGER,
                total_omzet REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Simpan hasil Peak Hour ke DB
        for _, row in hour_summary.iterrows():
            h_key = f"Jam {int(row['hour']):02d}:00"
            cursor.execute('''
                INSERT OR REPLACE INTO peak_analytics (period_type, period_key, total_transactions, total_omzet, updated_at)
                VALUES ('HOUR', ?, ?, ?, datetime('now'))
            ''', (h_key, int(row['total_transaksi']), float(row['total_omzet'])))
            
        # Simpan hasil Peak Day ke DB
        for _, row in day_summary.dropna(subset=['total_transaksi']).iterrows():
            d_key = row['day_id']
            cursor.execute('''
                INSERT OR REPLACE INTO peak_analytics (period_type, period_key, total_transactions, total_omzet, updated_at)
                VALUES ('DAY', ?, ?, ?, datetime('now'))
            ''', (d_key, int(row['total_transaksi']), float(row['total_omzet'])))
            
        db_conn.commit()
        db_conn.close()
        
        # Susun Laporan Teks
        report = "📊 **ANALISIS PEAK SESSION (PANDAS & DB)**\n\n"
        
        report += "🕒 **1. PEAK HOUR (JAM SIBUK)**\n"
        for _, row in hour_summary.sort_values(by='total_transaksi', ascending=False).iterrows():
            h = int(row['hour'])
            tx = int(row['total_transaksi'])
            omz = row['total_omzet']
            report += f"- Jam {h:02d}:00 -> {tx} Transaksi (Rp {omz:,.0f})\n".replace(",", ".")
            
        report += "\n📅 **2. PEAK DAY (HARI SIBUK)**\n"
        for _, row in day_summary.dropna(subset=['total_transaksi']).iterrows():
            d = row['day_id']
            tx = int(row['total_transaksi'])
            omz = row['total_omzet']
            report += f"- {d}: {tx} Transaksi (Rp {omz:,.0f})\n".replace(",", ".")
            
        return report
    except Exception as e:
        return f"❌ Error analisis & simpan DB: {e}"