import json
import time
import sqlite3
import requests
import logging
import os
from google import genai
import pandas as pd
from datetime import datetime, timedelta
from config import API_HOST, X_APP, EMAIL, PASSWORD, KLEDO_COOKIE_NAME, KLEDO_COOKIE_VALUE, GEMINI_API_KEY
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

def sync_missing_invoices(query=None):
    """Sinkronisasi data dengan laporan progres real-time ke Telegram."""
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
            if resp.status_code != 200:
                break
                
            res = resp.json()
            pagination = res.get("data", {})
            data_list = pagination.get("data", [])
            last_page = pagination.get("last_page", 1)
            
            if not data_list: break
            
            # Live Update ke Telegram di setiap halaman agar user tahu proses sedang berjalan
            if query and current_page % 2 == 0:  # Update tiap 2 halaman agar tidak kena limit Telegram
                try:
                    # Karena fungsi ini berjalan di thread terpisah, kita gunakan loop atau abaikan jika asynchronous murni.
                    pass 
                except:
                    pass

            cursor.execute("BEGIN TRANSACTION;")
            
            for inv_list in data_list:
                inv_id = inv_list.get("id")
                updated_at_kledo = inv_list.get("updated_at")
                
                cursor.execute("SELECT updated_at FROM invoices WHERE invoice_id = ?", (inv_id,))
                row = cursor.fetchone()
                
                if not row or row[0] != updated_at_kledo:
                    detail_resp = session.get(f"{API_HOST}/finance/invoices/{inv_id}", headers={"Accept": "application/json", "X-App": X_APP})
                    
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
            
            db_conn.commit()
            time.sleep(0.2)
            
            current_page += 1
            if current_page > last_page: break
            
        db_conn.close()
        return f"🔄 **SYNC SELESAI (BATCH)**\n✅ Total Baru: {total_inserted}\n✏️ Total Update: {total_updated}"
    except Exception as e:
        return f"❌ Error Sync: {escape_markdown(str(e))}"

def analyze_season_from_db(mode="peak", channel="all"):
    try:
        db_conn = init_db()
        df = pd.read_sql("SELECT contact_name, amount, raw_data FROM invoices", db_conn)
        db_conn.close()
        
        if df.empty:
            return "⚠️ Database kosong."

        # Filter berdasarkan channel jika bukan "all"
        if channel != "all":
            df = df[df['contact_name'].str.lower() == channel.lower()]
            if df.empty:
                return f"⚠️ Tidak ada data untuk channel `{channel.capitalize()}`."

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
        
        total_unique_days = df['date'].nunique() or 1
        asc = (mode == "low")
        
        h_sum = df.groupby('hour').agg(
            tx=('amount', 'count'), 
            omzet=('amount', 'sum'), 
            items=('total_items', 'sum'),
            active_days=('date', 'nunique')
        ).query('tx > 0').sort_values(['tx', 'omzet'], ascending=asc).reset_index()
        
        d_sum = df.groupby('day_id').agg(
            tx=('amount', 'count'), 
            omzet=('amount', 'sum'), 
            items=('total_items', 'sum'),
            active_weeks=('date', lambda x: x.nunique() / 7)
        ).query('tx > 0').sort_values(['tx', 'omzet'], ascending=asc).reset_index()
        
        c_sum = df.groupby('contact_name').agg(
            tx=('amount', 'count'), 
            omzet=('amount', 'sum'), 
            items=('total_items', 'sum')
        ).sort_values('omzet', ascending=False).reset_index()

        title = "🔥 PEAK SEASON (TERAMAI)" if mode == "peak" else "❄️ LOW SEASON (TERSEPI)"
        ch_label = channel.capitalize() if channel != "all" else "Semua Channel"
        report = f"📊 **ANALISIS {title}**\n📌 Filter: *{ch_label}*\n\n"
        
        # Tampilkan rekap per channel hanya jika mode "all"
        if channel == "all":
            report += "🛍️ **1. REKAP PER CHANNEL PENJUALAN**\n"
            for _, r in c_sum.iterrows():
                c_name = r['contact_name'] or "Lainnya"
                report += f"🔹 *{c_name}* ➔ {int(r['tx'])} Tx | {int(r['items'])} Porsi | Rp {int(r['omzet']):,}\n".replace(",", ".")
            report += "\n"

        report += f"🕒 **{'1' if channel != 'all' else '2'}. JAM SIBUK & RATA-RATA**\n"
        for _, r in h_sum.head(5).iterrows():
            divisor = r['active_days'] if r['active_days'] > 0 else 1
            avg_tx = r['tx'] / divisor
            avg_porsi = r['items'] / divisor
            avg_omzet = r['omzet'] / divisor
            
            report += f"• **Jam {int(r['hour']):02d}:00**\n"
            report += f"  Total: {int(r['tx'])} Tx | {int(r['items'])} Porsi | Rp {int(r['omzet']):,}\n".replace(",", ".")
            report += f"  Rata-rata: ⚡ {avg_tx:.1f} Tx | 📦 {avg_porsi:.1f} Porsi | 💰 Rp {int(avg_omzet):,}\n".replace(",", ".")
            
        report += f"\n📅 **{'2' if channel != 'all' else '3'}. HARI SIBUK & RATA-RATA**\n"
        for _, r in d_sum.head(3).iterrows():
            divisor = max(r['active_weeks'], 1)
            avg_tx = r['tx'] / divisor
            avg_porsi = r['items'] / divisor
            avg_omzet = r['omzet'] / divisor
            
            report += f"• **{r['day_id']}**\n"
            report += f"  Total: {int(r['tx'])} Tx | {int(r['items'])} Porsi | Rp {int(r['omzet']):,}\n".replace(",", ".")
            report += f"  Rata-rata: ⚡ {avg_tx:.1f} Tx/hari | 📦 {avg_porsi:.1f} Porsi/hari | 💰 Rp {int(avg_omzet):,}\n".replace(",", ".")
        
        base_report = report

        ai_insights = get_ai_recommendation(base_report, mode)
        
        return base_report + "\n" + ai_insights
        
    except Exception as e:
        return f"❌ Error: {escape_markdown(str(e))}"

def get_ai_recommendation(analysis_report, mode="peak"):
    """Menggunakan Gemini AI dengan sistem cadangan (fallback) otomatis jika terjadi gangguan."""
    if not GEMINI_API_KEY:
        return "💡 *Rekomendasi AI:* (API Key Gemini belum disetel di file .env)"
    
    # Daftar model urutan prioritas (Model utama, lalu model cadangan)
    models_to_try = ['gemini-3.7-flash', 'gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-3.5-flash-lite']
    models_to_try = [
        'gemini-3.7-flash',
        'gemini-3.6-flash',
        'gemini-3.5-flash',
        'gemini-3.5-flash-lite',
        'gemini-3.6-flash-high', 
        'gemini-3.6-flash-medium', 
        'gemini-3.6-flash-low', 
        'gemini-3.5-flash-low', 
        'gemini-3-flash'
    ]
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Anda adalah seorang konsultan bisnis F&B (Kuliner) yang ahli. 
    Berikut adalah data analisis operasional harian berdasarkan database toko kami:
    
    {analysis_report}
    
    Berikan 3 rekomendasi taktis, singkat, dan actionable (dapat langsung dieksekusi) untuk pemilik usaha berdasarkan data di atas. Fokuskan pada efisiensi staf, stok bahan baku, atau strategi promosi di jam/hari sibuk/sepi. Gunakan bahasa Indonesia yang santai tapi profesional, format dengan bullet points, dan jangan terlalu panjang.
    """
    
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            if response and response.text:
                return f"\n🤖 **AI BUSINESS INSIGHTS & RECOMMENDATION:**\n{response.text}"
        except Exception as e:
            # Jika model ini gagal/sibuk, lanjut mencoba model cadangan berikutnya
            continue
            
    return "\n⚠️ Gagal memuat rekomendasi AI: Semua model cadangan sedang sibuk (503 Unavailable). Silakan coba beberapa saat lagi."