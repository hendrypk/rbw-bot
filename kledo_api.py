import json
import sqlite3
import requests
import logging
import os
import pandas as pd
from datetime import datetime, timedelta
from config import API_HOST, X_APP, EMAIL, PASSWORD, KLEDO_COOKIE_NAME, KLEDO_COOKIE_VALUE
from data import init_db

TEMP_JSON_FILE = "temp_invoices.json"

def escape_markdown(text):
    """Escape karakter khusus agar aman di parse_mode='Markdown'"""
    escape_chars = r'_*`['
    return "".join(['\\' + char if char in escape_chars else char for char in text])

def create_kledo_session():
    session = requests.Session()
    login_url = f"{API_HOST}/authentication/singleLogin"
    
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
    
    cookies = {}
    if KLEDO_COOKIE_NAME and KLEDO_COOKIE_VALUE:
        cookies[KLEDO_COOKIE_NAME] = KLEDO_COOKIE_VALUE

    try:
        logging.info("Mengirim request login ke Kledo dengan payload & cookie...")
        response = session.post(login_url, json=payload, headers=headers, cookies=cookies, timeout=15)
        response.raise_for_status()
        res_data = response.json()
        
        logging.info("🎉 LOGIN BERHASIL!")
        
        access_token = res_data.get("data", {}).get("data", {}).get("access_token")
        
        if access_token:
            session.headers.update({
                "Content-Type": "application/json",
                "Accept": "application/json",
                "app-client": "web",
                "X-App": X_APP,
                "Authorization": f"Bearer {access_token}"
            })
        else:
            session.headers.update(headers)
            
        return session
        
    except requests.exceptions.HTTPError as err:
        logging.error(f"❌ Kledo Login HTTP Error {err.response.status_code}: {err.response.text}")
        return None
    except Exception as e:
        logging.error(f"❌ Kledo Login Error Lainnya: {e}")
        return None

def fetch_invoices_to_json(target_date):
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
        return None, f"❌ Error API Kledo: {escape_markdown(str(e))}"

def insert_temp_json_to_db():
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
        return 0, f"❌ Error Database: {escape_markdown(str(e))}"

def sync_missing_invoices():
    try:
        session = create_kledo_session()
        if not session: return "❌ Gagal login ke Kledo."

        db_conn = init_db()
        cursor = db_conn.cursor()
        total_inserted = 0
        total_updated = 0
        
        current_page = 1
        while True:
            url = f"{API_HOST}/finance/invoices?page={current_page}&per_page=50"
            resp = session.get(url, headers={"Accept": "application/json", "X-App": X_APP}, timeout=15)
            res = resp.json()
            data_list = res.get("data", {}).get("data", [])
            if not data_list: break
            
            for inv_list in data_list:
                inv_id = inv_list.get("id")
                updated_at_kledo = inv_list.get("updated_at")
                
                cursor.execute("SELECT updated_at FROM invoices WHERE invoice_id = ?", (inv_id,))
                row = cursor.fetchone()
                
                if not row or row[0] != updated_at_kledo:
                    detail_resp = session.get(f"{API_HOST}/finance/invoices/{inv_id}", headers={"Accept": "application/json", "X-App": X_APP})
                    
                    # FIXED: Proteksi jika Kledo API error atau kosong
                    if detail_resp.status_code != 200: continue
                    detail = detail_resp.json().get("data")
                    if not detail: continue 
                    
                    log_created_at = detail.get("log", {}).get("action", {}).get("created_at")
                    
                    items = detail.get("items", [])
                    products_str = ", ".join([f"{i.get('product_name')} (x{i.get('qty', 1)})" for i in items])
                    raw_data_json = json.dumps(detail)
                    
                    if not row:
                        cursor.execute('''INSERT INTO invoices 
                            (invoice_id, ref_number, contact_name, amount, products, created_time, raw_data, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                            (inv_id, detail.get("ref_number"), detail.get("contact", {}).get("name"), 
                             detail.get("amount"), products_str, log_created_at, raw_data_json, updated_at_kledo))
                        total_inserted += 1
                    else:
                        cursor.execute('''UPDATE invoices SET ref_number=?, contact_name=?, amount=?, 
                                          products=?, created_time=?, raw_data=?, updated_at=? 
                                          WHERE invoice_id=?''', 
                                          (detail.get("ref_number"), detail.get("contact", {}).get("name"), detail.get("amount"), 
                                           products_str, log_created_at, raw_data_json, updated_at_kledo, inv_id))
                        total_updated += 1
            
            current_page += 1
            if current_page > res.get("data", {}).get("last_page", 1): break
            
        db_conn.commit()
        db_conn.close()
        return f"🔄 **SYNC SELESAI**\n✅ Baru: {total_inserted}\n✏️ Update: {total_updated}"
    except Exception as e:
        return f"❌ Error Sync: {escape_markdown(str(e))}"

def analyze_season_from_db(mode="peak"):
    try:
        db_conn = init_db()
        df = pd.read_sql("SELECT amount, raw_data FROM invoices", db_conn)
        db_conn.close()
        
        if df.empty:
            return "⚠️ Database kosong."

        def parse_row(raw):
            try:
                data = json.loads(raw)
                ts = data.get("log", {}).get("action", {}).get("created_at")
                if not ts: ts = data.get("created_at")
                qty = sum(float(i.get('qty', 1)) for i in data.get('items', []))
                return ts, qty
            except:
                return None, 0

        df[['ts_str', 'total_items']] = df['raw_data'].apply(lambda x: pd.Series(parse_row(x)))
        df['dt'] = pd.to_datetime(df['ts_str'], errors='coerce')
        df = df.dropna(subset=['dt'])
        df['dt'] = pd.to_datetime(df['dt'])
        
        df['hour'] = df['dt'].dt.hour
        df['date'] = df['dt'].dt.date
        df['day_id'] = df['dt'].dt.day_name().map({
            'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu', 
            'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu', 'Sunday': 'Minggu'
        })
        
        asc = (mode == "low")
        # FIXED: Menambahkan reset_index() agar nama variabel yang dipanggil saat loop sesuai dengan DataFramenya
        h_sum = df.groupby('hour').agg(tx=('amount', 'count'), omzet=('amount', 'sum'), items=('total_items', 'sum')).query('tx > 0').sort_values(['tx', 'omzet'], ascending=asc).reset_index()
        d_sum = df.groupby('day_id').agg(tx=('amount', 'count'), omzet=('amount', 'sum'), items=('total_items', 'sum')).query('tx > 0').sort_values(['tx', 'omzet'], ascending=asc).reset_index()
        t_sum = df.groupby('date').agg(tx=('amount', 'count'), omzet=('amount', 'sum'), items=('total_items', 'sum')).query('tx > 0').sort_values(['tx', 'omzet'], ascending=asc).head(5).reset_index()
        
        title = "🔥 PEAK SEASON (TERAMAI)" if mode == "peak" else "❄️ LOW SEASON (TERSEPI)"
        report = f"📊 **ANALISIS {title}**\n\n"
        
        report += f"🕒 **1. {'JAM SIBUK' if mode == 'peak' else 'JAM SEPI'}**\n"
        # FIXED: Menggunakan variabel h_sum, d_sum, t_sum
        for _, r in h_sum.iterrows():
            report += f"- Jam {int(r['hour']):02d}:00 ➔ {int(r['tx'])} Tx | {int(r['items'])} Porsi | Rp {int(r['omzet']):,}\n"
            
        report += f"\n📅 **2. {'HARI SIBUK' if mode == 'peak' else 'HARI SEPI'}**\n"
        for _, r in d_sum.iterrows():
            report += f"- {r['day_id']} ➔ {int(r['tx'])} Tx | {int(r['items'])} Porsi | Rp {int(r['omzet']):,}\n"
            
        report += f"\n📆 **3. TOP 5 {'TANGGAL TERAMAI' if mode == 'peak' else 'TANGGAL TERSEPI'}**\n"
        for _, r in t_sum.iterrows():
            report += f"- {r['date']} ➔ {int(r['tx'])} Tx | {int(r['items'])} Porsi | Rp {int(r['omzet']):,}\n"
        
        return report.replace(",", ".")
    except Exception as e:
        return f"❌ Error: {escape_markdown(str(e))}"