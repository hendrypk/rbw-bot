import json
import sqlite3
import requests
import logging
from collections import Counter
from config import API_HOST, X_APP, EMAIL, PASSWORD
from data import init_db

TEMP_JSON_FILE = "temp_invoices.json"

def create_kledo_session():
    session = requests.Session()
    payload = {
        "email": EMAIL, "password": PASSWORD, "remember_me": 1,
        "is_otp": 0, "use_jwt": 0, "include_init": 1, "apple_identity_token": None
    }
    headers = {"Content-Type": "application/json", "Accept": "*/*", "app-client": "web", "X-App": X_APP}
    try:
        response = session.post(f"{API_HOST}/authentication/singleLogin", json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return session
    except Exception as e:
        logging.error(f"Kledo Login Error: {e}")
        return None

def fetch_invoices_to_json(target_date):
    """Tahap 1: Login, Tarik data Kledo berdasarkan tanggal, simpan ke file JSON sementara."""
    session = create_kledo_session()
    if not session:
        return None, "❌ Gagal login ke Kledo. Periksa kembali email/password di .env!"
    
    url = f"{API_HOST}/finance/invoices?date_from={target_date}&date_to={target_date}&contact_id=1&per_page=100"
    
    try:
        resp = session.get(url, headers={"Accept": "application/json", "X-App": X_APP}, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", {}).get("data", [])
        
        if not data:
            return None, f"⚠️ Tidak ada data invoice POS Customer untuk tanggal {target_date}."
            
        # Simpan ke file JSON sementara
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
        
        # Hapus file temp setelah sukses dimasukkan ke DB
        os.remove(TEMP_JSON_FILE)
        return saved_count, None
    except Exception as e:
        return 0, f"❌ Error Database: {e}"

def analyze_peak_hours_from_db():
    """Tahap 3: Membaca data dari Database SQLite untuk analisis Peak Hours."""
    try:
        db_conn = init_db()
        cursor = db_conn.cursor()
        cursor.execute("SELECT created_time FROM invoices")
        rows = cursor.fetchall()
        db_conn.close()
        
        if not rows:
            return "⚠️ Database masih kosong. Belum ada invoice yang di-insert."
            
        hour_list = []
        for row in rows:
            created_at = row[0]
            if created_at:
                try:
                    if " " in created_at:
                        hour = int(created_at.strip().split(" ")[1].split(":")[0])
                        hour_list.append(hour)
                except: continue
                
        counts = Counter(hour_list).most_common()
        report = "📊 PEAK HOURS ANALYTICS (DARI DATABASE)\n\n"
        if counts:
            for h, c in sorted(counts):
                report += f"- Jam {h:02d}:00 -> {c} Transaksi\n"
        else:
            report += "⚠️ Tidak ada data jam transaksi yang valid di database."
        return report
    except Exception as e:
        return f"❌ Error membaca database: {e}"

import os # pastikan os terimport di kledo_api.py