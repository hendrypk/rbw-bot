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

def create_kledo_session():
    """
    Membuat session Kledo menggunakan metode singleLogin 
    dengan payload JSON lengkap, custom headers, dan cookies.
    """
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

def sync_missing_invoices():
    try:
        db_conn = init_db()
        cursor = db_conn.cursor()
        
        # 1. Cari tanggal transaksi terakhir
        cursor.execute("SELECT MAX(substr(created_time, 1, 10)) FROM invoices")
        result = cursor.fetchone()
        latest_db_date_str = result[0] if result and result[0] else None
        
        today = datetime.now().date()
        start_date = datetime.strptime(latest_db_date_str, "%Y-%m-%d").date() if latest_db_date_str else today - timedelta(days=7)
            
        dates_to_check = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") 
                          for i in range((today - start_date).days + 1)]
            
        if not dates_to_check:
            return "✅ Database sudah up-to-date."

        session = create_kledo_session()
        if not session:
            return "❌ Gagal login ke Kledo."
            
        report_lines = []
        total_inserted = 0
        total_updated = 0
        
        for check_date in dates_to_check:
            url = f"{API_HOST}/finance/invoices?date_from={check_date}&date_to={check_date}&contact_id=1&per_page=100"
            try:
                resp = session.get(url, headers={"Accept": "application/json", "X-App": X_APP}, timeout=15)
                resp.raise_for_status()
                data = resp.json().get("data", {}).get("data", [])
                
                for inv in data:
                    inv_id = inv.get("id")
                    # Pastikan data lengkap
                    ref_number = inv.get("ref_number")
                    c_name = inv.get("contact", {}).get("name")
                    amount = inv.get("amount")
                    created_at = inv.get("log", {}).get("action", {}).get("created_at") or inv.get("created_at") or inv.get("trans_date")
                    items = inv.get("items", [])
                    products_str = ", ".join([f"{i.get('product_name')} (x{i.get('qty', 1)})" for i in items])
                    raw_data_json = json.dumps(inv)
                    
                    # 2. Cek apakah invoice sudah ada
                    cursor.execute("SELECT raw_data FROM invoices WHERE invoice_id = ?", (inv_id,))
                    row = cursor.fetchone()
                    
                    if not row:
                        # INSERT: Jika belum ada
                        cursor.execute('''INSERT INTO invoices (invoice_id, ref_number, contact_name, amount, products, created_time, raw_data)
                                          VALUES (?, ?, ?, ?, ?, ?, ?)''', (inv_id, ref_number, c_name, amount, products_str, created_at, raw_data_json))
                        total_inserted += 1
                    else:
                        # UPDATE: Jika sudah ada, bandingkan raw_data untuk memastikan kelengkapan
                        if row[0] != raw_data_json:
                            cursor.execute('''UPDATE invoices SET ref_number=?, contact_name=?, amount=?, products=?, created_time=?, raw_data=? 
                                              WHERE invoice_id=?''', (ref_number, c_name, amount, products_str, created_at, raw_data_json, inv_id))
                            total_updated += 1
                        
                db_conn.commit()
                
            except Exception as e:
                report_lines.append(f"📅 `{check_date}`: ❌ Error ({e})")
                
        db_conn.close()
        
        if total_inserted == 0 and total_updated == 0:
            return "✅ Database sudah sinkron. Tidak ada perubahan."
            
        return f"🔄 **SINKRONISASI SELESAI**\n\n✅ Baru: {total_inserted}\n✏️ Diperbarui: {total_updated}\n\nTotal sinkronisasi sukses."
        
    except Exception as e:
        return f"❌ Error sync: {e}"

def analyze_season_from_db(mode="peak"):
    """
    Analisis menggunakan jam dari log.action.created_at sesuai struktur JSON Kledo.
    """
    try:
        db_conn = init_db()
        # Mengambil raw_data agar bisa parsing JSON log
        query = "SELECT amount, raw_data FROM invoices"
        df = pd.read_sql(query, db_conn)
        db_conn.close()
        
        if df.empty:
            return "⚠️ Database masih kosong."

        # Fungsi helper untuk ekstrak waktu dari JSON raw_data
        def get_datetime_from_raw(raw_str):
            try:
                data = json.loads(raw_str)
                # Jalur ambil: log -> action -> created_at
                created_at_str = data.get("log", {}).get("action", {}).get("created_at")
                if created_at_str:
                    return pd.to_datetime(created_at_str)
                return None
            except:
                return None

        # Fungsi helper untuk hitung total porsi (qty)
        def get_total_items(raw_str):
            try:
                data = json.loads(raw_str)
                return sum(float(item.get('qty', 1)) for item in data.get('items', []))
            except:
                return 0

        # Terapkan ekstraksi
        df['dt'] = df['raw_data'].apply(get_datetime_from_raw)
        df = df.dropna(subset=['dt'])
        df['total_items'] = df['raw_data'].apply(get_total_items)
        
        # Ekstrak fitur waktu
        df['hour'] = df['dt'].dt.hour
        df['date'] = df['dt'].dt.date
        day_mapping = {
            'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
            'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu', 'Sunday': 'Minggu'
        }
        df['day_id'] = df['dt'].dt.day_name().map(day_mapping)
        
        # Agregasi (sama seperti sebelumnya)
        hour_summary = df.groupby('hour').agg(tx=('amount', 'count'), omzet=('amount', 'sum'), items=('total_items', 'sum')).reset_index()
        day_summary = df.groupby('day_id').agg(tx=('amount', 'count'), omzet=('amount', 'sum'), items=('total_items', 'sum')).reset_index()
        date_summary = df.groupby('date').agg(tx=('amount', 'count'), omzet=('amount', 'sum'), items=('total_items', 'sum')).reset_index()
        
        # Sorting mode
        asc_order = True if mode == "low" else False
        hour_summary = hour_summary[hour_summary['tx'] > 0].sort_values(by=['tx', 'omzet'], ascending=asc_order)
        day_summary = day_summary[day_summary['tx'] > 0].sort_values(by=['tx', 'omzet'], ascending=asc_order)
        date_summary = date_summary[date_summary['tx'] > 0].sort_values(by=['tx', 'omzet'], ascending=asc_order).head(5)
        
        # Susun laporan
        title = "🔥 PEAK SEASON (TERAMAI)" if mode == "peak" else "❄️ LOW SEASON (TERSEPI)"
        report = f"📊 **ANALISIS {title}**\n\n"
        
        report += f"🕒 **1. {'JAM SIBUK' if mode == 'peak' else 'JAM SEPI'}**\n"
        for _, r in hour_summary.iterrows():
            report += f"- Jam {int(r['hour']):02d}:00 ➔ {int(r['tx'])} Tx | {int(r['items'])} Porsi | Rp {r['omzet']:,.0f}\n".replace(",", ".")
            
        report += f"\n📅 **2. {'HARI SIBUK' if mode == 'peak' else 'HARI SEPI'}**\n"
        for _, r in day_summary.iterrows():
            report += f"- {r['day_id']} ➔ {int(r['tx'])} Tx | {int(r['items'])} Porsi | Rp {r['omzet']:,.0f}\n".replace(",", ".")
            
        report += f"\n📆 **3. TOP 5 {'TANGGAL TERAMAI' if mode == 'peak' else 'TANGGAL TERSEPI'}**\n"
        for _, r in date_summary.iterrows():
            tgl = r['date'].strftime("%d %b %Y")
            report += f"- {tgl} ➔ {int(r['tx'])} Tx | {int(r['items'])} Porsi | Rp {r['omzet']:,.0f}\n".replace(",", ".")
            
        return report
        
    except Exception as e:
        return f"❌ Error analisis: {e}"