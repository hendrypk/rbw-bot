import json
import requests
import logging
from datetime import datetime
from collections import Counter
from config import API_HOST, X_APP, EMAIL, PASSWORD
from data import init_db

def create_kledo_session():
    session = requests.Session()
    payload = {
        "email": EMAIL, "password": PASSWORD, "remember_me": 1,
        "is_otp": 0, "use_jwt": 0, "include_init": 1, "apple_identity_token": None
    }
    headers = {"Content-Type": "application/json", "Accept": "*/*", "app-client": "web", "X-App": X_APP}
    try:
        response = session.post(f"{API_HOST}/authentication/singleLogin", json=payload, headers=headers)
        response.raise_for_status()
        return session
    except Exception as e:
        logging.error(f"Kledo Login Error: {e}")
        return None

def run_kledo_analysis_pipeline():
    print("\n⏳ [1/3] Memulai proses login ke Kledo...")
    session = create_kledo_session()
    if not session:
        return "❌ Gagal login ke Kledo. Periksa kembali email/password di .env!"
    
    date_from, date_to = "2026-08-01", "2026-08-30"
    print(f"⏳ [2/3] Mengambil data invoice...")
    url = f"{API_HOST}/finance/invoices?date_from={date_from}&date_to={date_to}&contact_id=1&per_page=100"
    
    try:
        resp = session.get(url, headers={"Accept": "application/json", "X-App": X_APP})
        resp.raise_for_status()
        data = resp.json().get("data", {}).get("data", [])
        
        if not data:
            return "⚠️ Tidak ada data invoice POS Customer ditemukan."
            
        print("⏳ [3/3] Menyimpan ke database & Menganalisis...")
        db_conn = init_db()
        cursor = db_conn.cursor()
        saved_count = 0
        hour_list = []
        
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
            
            if created_at:
                try:
                    if " " in created_at:
                        hour = int(created_at.strip().split(" ")[1].split(":")[0])
                        hour_list.append(hour)
                except: continue
                    
        db_conn.commit()
        db_conn.close()
        
        counts = Counter(hour_list).most_common()
        report = f"📊 **PEAK HOURS ANALYTICS (POS CUSTOMER)**\n🗓️ `Periode: 01 - 30 Agustus 2026`\n💾 `Tersimpan: {saved_count} Invoices`\n\n"
        if counts:
            for h, c in sorted(counts): report += f"├ Jam {h:02d}:00 ➔ {c} Transaksi\n"
        else:
            report += "⚠️ Belum ada data jam transaksi spesifik."
        return report

    except Exception as e:
        return f"❌ Error API: {e}"