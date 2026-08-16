"""
======================================================================
🤖 BOT TELEGRAM: LAPORAN KEUANGAN, REKAP PENJUALAN & ANALISIS KLEDO
======================================================================
"""

import os
import json
import logging
import io

import requests
from datetime import datetime, timedelta
from collections import Counter
from dotenv import load_dotenv
from telegram.ext import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Update
)

# Muat variabel environment dari file .env lokal
load_dotenv()

# 1. Konfigurasi Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- KONFIGURASI API KLEDO & DATA ---
DATA_FILE = "data.json"
API_HOST = os.getenv("KLEDO_BASE_HOST", "http://rotibakarwisuda.api.kledo.com/api/v1")
X_APP = os.getenv("X_APP", "finance")
EMAIL = os.getenv("KLEDO_EMAIL")
PASSWORD = os.getenv("KLEDO_PASSWORD")

default_financial_data = {
    "date": "17 Aug 26",
    "seabank": 0,
    "jago": 0,
    "cash_tunai": 0,
    "alokasi": {
        "Gaji Akmal": 0,
        "Gaji Owner": 0,
        "Sewa Lapak": 0,
        "Sewa Kontainer": 0,
        "BMT": 0,
        "Cabang 2": 0,
        "Saving": 0,
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

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(financial_data, f, indent=4)

financial_data = load_data()


# --- FUNGSI INTEGRASI KLEDO ---
def create_kledo_session():
    session = requests.Session()
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
        "Content-Type": "application/json",
        "Accept": "*/*",
        "app-client": "web",
        "X-App": X_APP
    }
    try:
        response = session.post(f"{API_HOST}/authentication/singleLogin", json=payload, headers=headers)
        response.raise_for_status()
        return session
    except Exception as e:
        logging.error(f"Kledo Login Error: {e}")
        return None

def run_kledo_analysis():
    session = create_kledo_session()
    if not session:
        return "❌ Gagal login ke Kledo. Periksa kembali email/password di .env!"
    
    url = f"{API_HOST}/finance/invoices?date_from=2026-08-01&date_to=2026-08-30&per_page=100"
    try:
        resp = session.get(url, headers={"Accept": "application/json", "X-App": X_APP})
        resp.raise_for_status()
        data = resp.json().get("data", {}).get("data", [])
        
        if not data:
            return "⚠️ Tidak ada data invoice ditemukan dalam rentang tanggal tersebut."
        
        hour_list = []
        for inv in data:
            created_at = (
                inv.get("created_at")
                or inv.get("log", {}).get("action", {}).get("created_at")
                or inv.get("trans_date")
            )
            if created_at:
                try:
                    if " " in created_at:
                        dt_str = created_at[:19]
                        fmt = "%Y-%m-%d %H:%M:%S" if len(dt_str) == 19 else "%Y-%m-%d %H:%M"
                        dt = datetime.strptime(dt_str, fmt)
                        hour_list.append(dt.hour)
                except ValueError:
                    continue
        
        counts = Counter(hour_list).most_common()
        report = "📊 **PEAK HOURS ANALYTICS (KLEDO)**\n\n"
        if counts:
            for h, c in sorted(counts):
                report += f"├ Jam {h:02d}:00 ➔ {c} Transaksi\n"
        else:
            report += "⚠️ Belum ada data jam transaksi spesifik yang valid."
        return report
    except Exception as e:
        return f"❌ Error saat mengambil data Kledo: {e}"


# --- FUNGSI HELPER & KEYBOARD ---
def parse_wallet_key(query):
    query = query.lower().strip()
    if "seabank" in query: return "seabank"
    if "jago" in query: return "jago"
    if "cash" in query or "tunai" in query: return "cash_tunai"
    return None

def generate_report_text():
    total_efektif = financial_data["seabank"] + financial_data["jago"] + financial_data["cash_tunai"]
    total_non_efektif = sum(financial_data["alokasi"].values())
    grand_total = total_efektif + total_non_efektif
    ratio = (
        (total_efektif / grand_total) * 100 if grand_total > 0 else 0
    )

    sales = financial_data["sales"]
    total_nota = sum(ch["nota"] for ch in sales.values())
    total_porsi = sum(ch["porsi"] for ch in sales.values())
    total_rupiah = sum(ch["rupiah"] for ch in sales.values())

    text = f"""==================================
📊 **DAILY FINANCIAL REPORT**
🗓️ Per Tanggal: {financial_data['date']}
==================================

💵 **1. SALDO EFEKTIF (READY CASH)**
----------------------------------
├ Seabank         : Rp {financial_data['seabank']:,}
├ Wallet Jago     : Rp {financial_data['jago']:,}
├ Cash (Tunai)    : Rp {financial_data['cash_tunai']:,}
└ 🟩 **TOTAL EFEKTIF: Rp {total_efektif:,}**

🔒 **2. SALDO NON-EFEKTIF (ALOKASI)**
----------------------------------"""

    for k, v in financial_data["alokasi"].items():
        text += f"\n├ {k:<15} : Rp {v:,}"

    text += f"""
└ 🟥 **TOTAL NON-EFEKTIF: Rp {total_non_efektif:,}**

==================================
🛍️ **3. REKAP PENJUALAN & WALLET**
----------------------------------"""

    for ch_name, ch_data in sales.items():
        w_label = ch_data['wallet'].replace('_', ' ').title()
        text += f"\n├ {ch_name.capitalize():<10} : {ch_data['nota']} Nota | {ch_data['porsi']} Porsi | Rp {ch_data['rupiah']:,} ➔ *{w_label}*"

    text += f"""
└ 📦 **TOTAL : {total_nota} Nota | {total_porsi} Porsi | Rp {total_rupiah:,}**

==================================
💰 **SUMMARY & LIQUIDITY**
----------------------------------
💎 Grand Total Cash : Rp {grand_total:,}
📊 Ratio Likuiditas : {ratio:.1f}% (Ready Use)
=================================="""
    return text.replace(",", ".")

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 Lihat Laporan", callback_data="view_report")],
        [InlineKeyboardButton("📊 Menu Grafik", callback_data="menu_chart")],
        [InlineKeyboardButton("🔍 Analyze Peak Hours", callback_data="kledo_analysis")],
        [InlineKeyboardButton("🔄 Transfer Saldo", callback_data="transfer_info")],
        [InlineKeyboardButton("📖 Cara Pakai", callback_data="help_menu")],
    ])


# --- HANDLER: Perintah Teks (Command) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = "🤖 **BOT KEUANGAN & ANALISIS**\n\nSilakan pilih menu di bawah ini:"
    if update.message:
        await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(welcome_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(generate_report_text(), parse_mode="Markdown", reply_markup=get_main_keyboard())

async def set_efektif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        nama = context.args[0].lower()
        nominal = int(context.args[1])
        if "seabank" in nama: financial_data["seabank"] = nominal
        elif "jago" in nama: financial_data["jago"] = nominal
        elif "cash" in nama or "tunai" in nama: financial_data["cash_tunai"] = nominal
        else:
            await update.message.reply_text("⚠️ Akun efektif tidak dikenal. Gunakan: Seabank, Jago, atau Cash", reply_markup=get_main_keyboard())
            return
        save_data()
        await update.message.reply_text(f"✅ Saldo efektif `{nama}` diupdate ke Rp {nominal:,}".replace(",", "."), parse_mode="Markdown", reply_markup=get_main_keyboard())
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Format salah!\nContoh: `/se Seabank 800000`", parse_mode="Markdown", reply_markup=get_main_keyboard())

async def set_nonefektif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 2: raise ValueError
        nama = " ".join(context.args[:-1])
        nominal = int(context.args[-1])
        matched_key = next((k for k in financial_data["alokasi"] if k.lower() == nama.lower()), None)
        if matched_key:
            financial_data["alokasi"][matched_key] = nominal
            save_data()
            await update.message.reply_text(f"✅ Saldo non-efektif `{matched_key}` diupdate ke Rp {nominal:,}".replace(",", "."), parse_mode="Markdown", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text(f"⚠️ Nama alokasi `{nama}` tidak ditemukan.", parse_mode="Markdown", reply_markup=get_main_keyboard())
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Format salah!\nContoh: `/sne \"Gaji Akmal\" 100000`", parse_mode="Markdown", reply_markup=get_main_keyboard())

async def set_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 4: raise ValueError
        channel_input = context.args[0].lower()
        nota = int(context.args[1])
        porsi = int(context.args[2])
        rupiah = int(context.args[3].replace(".", "").replace(",", ""))

        channel_map = {"offline": "offline", "shopee": "shopeefood", "shopeefood": "shopeefood", "gofood": "gofood", "go": "gofood", "grab": "grabfood", "grabfood": "grabfood"}
        matched_channel = channel_map.get(channel_input)
        if not matched_channel:
            await update.message.reply_text("⚠️ Channel tidak dikenal!", reply_markup=get_main_keyboard())
            return

        old_rupiah = financial_data["sales"][matched_channel]["rupiah"]
        selisih_rupiah = rupiah - old_rupiah

        financial_data["sales"][matched_channel]["nota"] = nota
        financial_data["sales"][matched_channel]["porsi"] = porsi
        financial_data["sales"][matched_channel]["rupiah"] = rupiah

        target_wallet = financial_data["sales"][matched_channel]["wallet"]
        financial_data[target_wallet] += selisih_rupiah
        save_data()

        wallet_label = target_wallet.replace("_", " ").title()
        await update.message.reply_text(f"✅ Rekap `{matched_channel.capitalize()}` diupdate (Masuk ke **{wallet_label}** +Rp {selisih_rupiah:,})".replace(",", "."), parse_mode="Markdown", reply_markup=get_main_keyboard())
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Format salah!\nContoh: `/sales offline 15 25 750000`", parse_mode="Markdown", reply_markup=get_main_keyboard())

async def set_channel_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 2: raise ValueError
        channel_input = context.args[0].lower()
        wallet_input = context.args[1].lower()
        channel_map = {"offline": "offline", "shopee": "shopeefood", "shopeefood": "shopeefood", "gofood": "gofood", "grab": "grabfood", "grabfood": "grabfood"}
        matched_channel = channel_map.get(channel_input)
        target_wallet = parse_wallet_key(wallet_input)
        if not matched_channel or not target_wallet:
            await update.message.reply_text("⚠️ Channel/Wallet tidak valid.", reply_markup=get_main_keyboard())
            return
        financial_data["sales"][matched_channel]["wallet"] = target_wallet
        save_data()
        await update.message.reply_text(f"✅ Channel **{matched_channel.capitalize()}** diatur ke wallet: **{target_wallet.replace('_', ' ').title()}**", parse_mode="Markdown", reply_markup=get_main_keyboard())
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Format salah!\nContoh: `/setchannel offline seabank`", parse_mode="Markdown", reply_markup=get_main_keyboard())

async def reset_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        tanggal_baru = " ".join(context.args)
        financial_data["date"] = tanggal_baru
        save_data()
        await update.message.reply_text(f"✅ Tanggal aktif diubah ke: **{tanggal_baru}**", parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text("⚠️ Format salah!\nContoh: `/resetdate 17 Aug 26`", parse_mode="Markdown", reply_markup=get_main_keyboard())

async def save_archive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target = context.args[0].lower() if context.args else "all"
        if target not in ["balance", "sales", "overview", "all"]:
            await update.message.reply_text("⚠️ Target tidak valid.", reply_markup=get_main_keyboard())
            return

        current_date = financial_data["date"]
        keyboard = [
            [
                InlineKeyboardButton("✅ OKE SAVE", callback_data=f"confirm_save_{target}"),
                InlineKeyboardButton("❌ CANCEL", callback_data="cancel_save")
            ]
        ]
        await update.message.reply_text(
            f"📌 **KONFIRMASI PENYIMPANAN ARSIP**\n\n🗓️ Tanggal: `{current_date}`\n📂 Data: `{target.upper()}`\n\nSimpan/Timpa arsip ini?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}", reply_markup=get_main_keyboard())


# --- UTILS TANGGAL & SHORTCUT ---
def parse_shortcut_range(shortcut):
    today = datetime(2026, 8, 17)
    sc = shortcut.lower().strip()
    if sc == "this week": start = today - timedelta(days=today.weekday()); end = today
    elif sc == "last week": start = today - timedelta(days=today.weekday() + 7); end = start + timedelta(days=6)
    elif sc == "this month": start = today.replace(day=1); end = today
    elif sc == "last month": end = today.replace(day=1) - timedelta(days=1); start = end.replace(day=1)
    elif sc == "last 30 days": start = today - timedelta(days=30); end = today
    elif sc == "this year": start = today.replace(month=1, day=1); end = today
    elif sc == "last year": start = today.replace(year=today.year-1, month=1, day=1); end = today.replace(year=today.year-1, month=12, day=31)
    else: return None, None
    return start.strftime("%d %b %y"), end.strftime("%d %b %y")


# --- GENERATE GRAFIK (MATPLOTLIB) ---
async def generate_and_send_chart(update_or_query, context, target, start_date=None, end_date=None):
    try:
        if not financial_data["history"]:
            msg = "⚠️ Belum ada data history! Gunakan `/save all` terlebih dahulu."
            if hasattr(update_or_query, "message") and update_or_query.message:
                await update_or_query.message.reply_text(msg, parse_mode="Markdown")
            else:
                await update_or_query.edit_message_text(msg, parse_mode="Markdown")
            return

        all_dates = list(financial_data["history"].keys())
        filtered_dates = all_dates
        
        if start_date and end_date:
            try:
                start_idx = next((i for i, d in enumerate(all_dates) if start_date.lower() in d.lower()), 0)
                end_idx = next((i for i, d in enumerate(all_dates) if end_date.lower() in d.lower()), len(all_dates)-1)
                filtered_dates = all_dates[min(start_idx, end_idx):max(start_idx, end_idx)+1]
            except: pass

        if not filtered_dates:
            msg = "⚠️ Tidak ada data history dalam rentang tanggal tersebut."
            if hasattr(update_or_query, "message") and update_or_query.message:
                await update_or_query.message.reply_text(msg, parse_mode="Markdown")
            else:
                await update_or_query.edit_message_text(msg, parse_mode="Markdown")
            return

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        plt.figure(figsize=(10, 5))

        if target == "balance":
            vals = [financial_data["history"][d].get("balance", {}).get("grand_total", 0) for d in filtered_dates]
            plt.plot(filtered_dates, vals, marker='o', color='b', linewidth=2)
            plt.title("Grafik Grand Total Balance")
            plt.ylabel("Rupiah (Rp)")
        else:
            metric = target.replace("sales_", "")
            channels = ["offline", "shopeefood", "gofood", "grabfood"]
            for ch in channels:
                vals = [financial_data["history"][d].get("sales", {}).get(ch, {}).get(metric, 0) for d in filtered_dates]
                plt.plot(filtered_dates, vals, marker='o', label=ch.capitalize(), linewidth=2)
            plt.title(f"Grafik Penjualan ({metric.capitalize()}) per Channel")
            plt.ylabel("Jumlah" if metric != "rupiah" else "Rupiah (Rp)")
            plt.legend()

        plt.xticks(rotation=45)
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        chat_id = update_or_query.effective_chat.id if hasattr(update_or_query, "effective_chat") else update_or_query.message.chat_id
        await context.bot.send_photo(
            chat_id=chat_id, 
            photo=buf, 
            caption=f"📈 **Grafik Analisis ({target.upper()})**\n🗓️ Periode: {filtered_dates[0]} s/d {filtered_dates[-1]}", 
            parse_mode="Markdown"
        )

    except Exception as e:
        msg = f"⚠️ Gagal membuat grafik: {e}"
        logging.error(f"Error Chart: {e}")
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update_or_query.edit_message_text(msg, parse_mode="Markdown")

async def send_chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if not args:
            await generate_and_send_chart(update, context, "sales_rupiah")
            return

        target = args[0].lower()
        start_date, end_date = None, None
        args_text = " ".join(args[1:]).strip()

        if args_text:
            shortcut_keywords = ["this week", "last week", "this month", "last month", "last 30 days", "this year", "last year"]
            matched_shortcut = next((sc for sc in shortcut_keywords if sc in args_text.lower()), None)
            
            if matched_shortcut:
                start_date, end_date = parse_shortcut_range(matched_shortcut)
            else:
                if " to " in args_text.lower():
                    parts = args_text.lower().split(" to ")
                    start_date, end_date = parts[0].strip('"\''), parts[1].strip('"\'')
                elif " ke " in args_text.lower():
                    parts = args_text.lower().split(" ke ")
                    start_date, end_date = parts[0].strip('"\''), parts[1].strip('"\'')

        if target == "balance":
            await generate_and_send_chart(update, context, "balance", start_date, end_date)
        elif target in ["porsi", "nota", "rupiah", "sales_rupiah", "sales_porsi", "sales_nota"]:
            metric = target.replace("sales_", "")
            await generate_and_send_chart(update, context, f"sales_{metric}", start_date, end_date)
        else:
            await generate_and_send_chart(update, context, "sales_rupiah", start_date, end_date)

    except Exception as e:
        await update.message.reply_text(
            "⚠️ Format perintah salah.\n\n"
            "**Contoh Shortcut:**\n"
            "`/chart balance \"this week\"`\n"
            "`/chart rupiah \"last month\"`\n\n"
            "**Contoh Rentang Tanggal:**\n"
            "`/chart balance \"10 Aug 26\" to \"17 Aug 26\"`", 
            parse_mode="Markdown"
        )


# --- BULK & TRANSFER ---
async def bulk_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = update.message.text.split('\n')[1:]
    if not lines:
        await update.message.reply_text("⚠️ Format salah!", reply_markup=get_main_keyboard())
        return

    success_updates = []
    errors = []
    for line in lines:
        line = line.strip()
        if not line: continue
        parts = line.rsplit(' ', 1)
        if len(parts) != 2:
            errors.append(f"Format salah: `{line}`")
            continue
        nama_input, nominal_str = parts[0].lower().strip(), parts[1].replace(".", "")
        try:
            nominal = int(nominal_str)
        except ValueError:
            errors.append(f"Nominal tidak valid: `{line}`")
            continue
        
        if "seabank" in nama_input: financial_data["seabank"] = nominal; success_updates.append(f"✅ Seabank: Rp {nominal:,}".replace(",", "."))
        elif "jago" in nama_input: financial_data["jago"] = nominal; success_updates.append(f"✅ Jago: Rp {nominal:,}".replace(",", "."))
        elif "cash" in nama_input or "tunai" in nama_input: financial_data["cash_tunai"] = nominal; success_updates.append(f"✅ Cash: Rp {nominal:,}".replace(",", "."))
        else:
            matched_key = next((k for k in financial_data["alokasi"] if k.lower() == nama_input), None)
            if matched_key:
                financial_data["alokasi"][matched_key] = nominal
                success_updates.append(f"✅ {matched_key}: Rp {nominal:,}".replace(",", "."))
            else:
                errors.append(f"Nama tidak ditemukan: `{nama_input}`")

    if success_updates: save_data()
    response_text = "📊 **BULK UPDATE:**\n\n" + ("\n".join(success_updates) + "\n\n" if success_updates else "")
    if errors: response_text += "⚠️ **Gagal:**\n" + "\n".join(errors)
    await update.message.reply_text(response_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def transfer_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args_text = " ".join(context.args)
        import shlex
        parts = shlex.split(args_text)
        if len(parts) < 3: raise ValueError
        if parts[1].lower() in ["to", "ke"]:
            if len(parts) < 4: raise ValueError
            sumber_input, tujuan_input, nominal_raw = parts[0].lower(), parts[2].lower(), parts[3]
        else:
            sumber_input, tujuan_input, nominal_raw = parts[0].lower(), parts[1].lower(), parts[2]
        
        nominal = int(nominal_raw.replace(".", "").replace(",", ""))
        if nominal <= 0: return

        def find_akun(query):
            query = query.lower()
            if "seabank" in query: return "seabank", "efektif"
            if "jago" in query: return "jago", "efektif"
            if "cash" in query or "tunai" in query: return "cash_tunai", "efektif"
            matched = next((k for k in financial_data["alokasi"] if k.lower() == query), None)
            return (matched, "alokasi") if matched else (None, None)

        sumber_key, sumber_tipe = find_akun(sumber_input)
        tujuan_key, tujuan_tipe = find_akun(tujuan_input)

        if not sumber_key or not tujuan_key:
            await update.message.reply_text("⚠️ Akun tidak ditemukan!", reply_markup=get_main_keyboard())
            return

        saldo_sumber = financial_data[sumber_key] if sumber_tipe == "efektif" else financial_data["alokasi"][sumber_key]
        if saldo_sumber < nominal:
            await update.message.reply_text(f"⚠️ Saldo `{sumber_key}` tidak cukup!", parse_mode="Markdown", reply_markup=get_main_keyboard())
            return

        if sumber_tipe == "efektif": financial_data[sumber_key] -= nominal
        else: financial_data["alokasi"][sumber_key] -= nominal

        if tujuan_tipe == "efektif": financial_data[tujuan_key] += nominal
        else: financial_data["alokasi"][tujuan_key] += nominal

        save_data()
        await update.message.reply_text(f"🔄 **TRANSFER BERHASIL**\n📤 `{sumber_key}` ➔ 📥 `{tujuan_key}`\n💰 Rp {nominal:,}".replace(",", "."), parse_mode="Markdown", reply_markup=get_main_keyboard())
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ Format salah! Contoh: `/tf seabank to jago 500000`", parse_mode="Markdown", reply_markup=get_main_keyboard())


# --- HANDLER: Tombol Interaktif (Callback Query) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "view_report":
        report = generate_report_text()
        keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="main_menu")]]
        await query.edit_message_text(report, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif data == "main_menu":
        await start(update, context)

    elif data == "menu_chart":
        keyboard = [
            [InlineKeyboardButton("📈 Grafik Balance", callback_data="chart_balance")],
            [InlineKeyboardButton("🛍️ Menu Grafik Sales", callback_data="menu_chart_sales")],
            [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="main_menu")]
        ]
        await query.edit_message_text("📊 **PILIH KATEGORI GRAFIK:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "menu_chart_sales":
        keyboard = [
            [InlineKeyboardButton("💰 Rupiah", callback_data="chart_sales_rupiah"), InlineKeyboardButton("📦 Porsi", callback_data="chart_sales_porsi")],
            [InlineKeyboardButton("🧾 Nota", callback_data="chart_sales_nota"), InlineKeyboardButton("⬅️ Kembali", callback_data="menu_chart")]
        ]
        await query.edit_message_text("🛍️ **PILIH JENIS METRIK SALES:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "chart_balance":
        await generate_and_send_chart(query, context, "balance")
    elif data == "chart_sales_rupiah":
        await generate_and_send_chart(query, context, "sales_rupiah")
    elif data == "chart_sales_porsi":
        await generate_and_send_chart(query, context, "sales_porsi")
    elif data == "chart_sales_nota":
        await generate_and_send_chart(query, context, "sales_nota")
        
    elif data == "kledo_analysis":
        await query.edit_message_text("⏳ Sedang menyambungkan ke Kledo & menganalisis data...", parse_mode="Markdown")
        result_text = run_kledo_analysis()
        keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="main_menu")]]
        await query.edit_message_text(result_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "transfer_info":
        help_tf = (
            "🔄 **MENU TRANSFER SALDO**\n\n"
            "Untuk melakukan transfer, gunakan perintah berikut di chat:\n\n"
            "`/tf <sumber> to <tujuan> <nominal>`\n\n"
            "**Contoh:**\n"
            "`/tf seabank to jago 500000`\n\n"
            "Akun yang tersedia: Seabank, Jago, Cash, atau nama alokasi Anda."
        )
        keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="main_menu")]]
        await query.edit_message_text(help_tf, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "help_menu":
        help_text = (
            "🤖 **CARA PAKAI BOT**\n\n"
            "• `/report` : Laporan harian.\n"
            "• `/se <nama> <nominal>` : Update saldo efektif.\n"
            "• `/sne <nama> <nominal>` : Update saldo alokasi.\n"
            "• `/tf <sumber> [to/ke] <tujuan> <nominal>` : Transfer dana.\n"
            "• `/sales <channel> <nota> <porsi> <rupiah>` : Rekap penjualan.\n"
            "• `/bulk` : Update banyak saldo (Baris baru).\n"
            "• `/resetdate 17 Aug 26` : Ubah tanggal aktif.\n"
            "• `/save all` : Simpan/timpa arsip tanggal.\n"
            "• `/chart balance \"this week\"` : Lihat grafik interaktif.\n"
            "• `/kledo` : Analisis jam ramai langsung via chat.\n"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="main_menu")]]
        await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("confirm_save_"):
        target = data.replace("confirm_save_", "")
        current_date = financial_data["date"]

        if current_date not in financial_data["history"]:
            financial_data["history"][current_date] = {"balance": {}, "sales": {}}

        if target in ["balance", "all"]:
            total_efektif = financial_data["seabank"] + financial_data["jago"] + financial_data["cash_tunai"]
            total_non_efektif = sum(financial_data["alokasi"].values())
            financial_data["history"][current_date]["balance"] = {
                "seabank": financial_data["seabank"],
                "jago": financial_data["jago"],
                "cash_tunai": financial_data["cash_tunai"],
                "total_efektif": total_efektif,
                "total_non_efektif": total_non_efektif,
                "grand_total": total_efektif + total_non_efektif
            }

        if target in ["sales", "overview", "all"]:
            sales_summary = {ch: d_val.copy() for ch, d_val in financial_data["sales"].items()}
            financial_data["history"][current_date]["sales"] = sales_summary

        save_data()
        await query.edit_message_text(f"✅ **ARSIP TANGGAL `{current_date}` BERHASIL DISIMPAN!**", parse_mode="Markdown")

    elif data == "cancel_save":
        await query.edit_message_text("❌ **Penyimpanan arsip dibatalkan.**", parse_mode="Markdown")


# Command khusus untuk trigger analisis kledo lewat chat text (/kledo)
async def kledo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Sedang menyambungkan ke Kledo & menganalisis data...")
    result_text = run_kledo_analysis()
    await update.message.reply_text(result_text, parse_mode="Markdown", reply_markup=get_main_keyboard())


# --- MAIN FUNCTION ---
def main():
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TOKEN: 
        raise ValueError("❌ TELEGRAM_TOKEN tidak ditemukan di file .env!")

    app = ApplicationBuilder().token(TOKEN).build()

    # Daftarkan seluruh Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("se", set_efektif))
    app.add_handler(CommandHandler("sne", set_nonefektif))
    app.add_handler(CommandHandler("resetdate", reset_date))
    app.add_handler(CommandHandler("bulk", bulk_update))
    app.add_handler(CommandHandler("tf", transfer_saldo))
    app.add_handler(CommandHandler("transfer", transfer_saldo))
    app.add_handler(CommandHandler("sales", set_sales))
    app.add_handler(CommandHandler("setchannel", set_channel_wallet))
    app.add_handler(CommandHandler("save", save_archive_command))
    app.add_handler(CommandHandler("chart", send_chart_command))
    app.add_handler(CommandHandler("kledo", kledo_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Telegram Keuangan & Analisis Kledo sedang berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()