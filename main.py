import os
import asyncio
import shlex
import datetime
from datetime import datetime as dt, timedelta
import pytz
import sqlite3
import json
import io
import logging
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

from config import TELEGRAM_TOKEN, GROUP_CHAT_ID
from data import financial_data, save_data

from kledo_api import fetch_invoices_to_json, insert_temp_json_to_db, analyze_season_from_db, sync_missing_invoices
from bot_ui import (
    get_main_keyboard, generate_report_text, parse_wallet_key, 
    generate_and_send_chart
)

# --- HELPER: PEMECAH TEKS PANJANG (Mencegah Message_too_long) ---
async def send_long_text(bot_or_update, chat_or_target, text, parse_mode="Markdown", reply_markup=None):
    """Memecah pesan teks jika melebihi batas maksimal Telegram (4000 karakter)"""
    max_length = 4000
    
    # Deteksi apakah argumen pertama adalah Update object atau Bot instance
    if hasattr(bot_or_update, "message") and bot_or_update.message:
        target_obj = bot_or_update.message
        chat_id = bot_or_update.effective_chat.id
        is_update = True
    else:
        bot = bot_or_update
        chat_id = chat_or_target
        is_update = False

    if len(text) <= max_length:
        if is_update:
            await target_obj.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode, reply_markup=reply_markup)
        return

    chunks = [text[i:i + max_length] for i in range(0, len(text), max_length)]
    for idx, chunk in enumerate(chunks):
        markup = reply_markup if idx == len(chunks) - 1 else None
        if is_update and idx == 0:
            await target_obj.reply_text(chunk, parse_mode=parse_mode, reply_markup=markup)
        else:
            if is_update:
                await bot_or_update.effective_chat.send_message(text=chunk, parse_mode=parse_mode, reply_markup=markup)
            else:
                await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=parse_mode, reply_markup=markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = "🤖 **BOT KEUANGAN & ANALISIS**\n\nSilakan pilih menu di bawah ini:"
    if update.message:
        await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(welcome_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(generate_report_text(), parse_mode="Markdown", reply_markup=get_main_keyboard())

async def set_efektif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        nama, nominal = context.args[0].lower(), int(context.args[1])
        if "seabank" in nama: financial_data["seabank"] = nominal
        elif "jago" in nama: financial_data["jago"] = nominal
        elif "cash" in nama or "tunai" in nama: financial_data["cash_tunai"] = nominal
        else:
            await update.message.reply_text("⚠️ Akun efektif tidak dikenal.", reply_markup=get_main_keyboard())
            return
        save_data(financial_data)
        await update.message.reply_text(f"✅ Saldo `{nama}` diupdate ke Rp {nominal:,}".replace(",", "."), parse_mode="Markdown", reply_markup=get_main_keyboard())
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Format: `/se Seabank 800000`", parse_mode="Markdown")

async def set_nonefektif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        nama, nominal = " ".join(context.args[:-1]), int(context.args[-1])
        matched_key = next((k for k in financial_data["alokasi"] if k.lower() == nama.lower()), None)
        if matched_key:
            financial_data["alokasi"][matched_key] = nominal
            save_data(financial_data)
            await update.message.reply_text(f"✅ Saldo `{matched_key}` diupdate ke Rp {nominal:,}".replace(",", "."), parse_mode="Markdown", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text(f"⚠️ Alokasi `{nama}` tidak ditemukan.", reply_markup=get_main_keyboard())
    except: await update.message.reply_text("⚠️ Format: `/sne Gaji Akmal 100000`", parse_mode="Markdown")

async def transfer_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw_text = " ".join(context.args).lower()
        if " to " in raw_text:
            sumber_str, rest = raw_text.split(" to ", 1)
        elif " ke " in raw_text:
            sumber_str, rest = raw_text.split(" ke ", 1)
        else:
            return await update.message.reply_text("⚠️ Format: `/tf seabank ke gaji akmal 500000`")
            
        parts_rest = rest.rsplit(" ", 1)
        tujuan_str = parts_rest[0].strip()
        nominal = int(parts_rest[1].replace(".", ""))

        def find_akun(query):
            if "seabank" in query: return "seabank", "efektif"
            if "jago" in query: return "jago", "efektif"
            if "cash" in query or "tunai" in query: return "cash_tunai", "efektif"
            matched = next((k for k in financial_data["alokasi"] if k.lower() == query), None)
            return (matched, "alokasi") if matched else (None, None)

        s_key, s_tipe = find_akun(sumber_str)
        t_key, t_tipe = find_akun(tujuan_str)
        if not s_key or not t_key: return await update.message.reply_text("⚠️ Akun tidak ditemukan!")

        if (financial_data[s_key] if s_tipe == "efektif" else financial_data["alokasi"][s_key]) < nominal:
            return await update.message.reply_text("⚠️ Saldo tidak cukup!")

        if s_tipe == "efektif": financial_data[s_key] -= nominal
        else: financial_data["alokasi"][s_key] -= nominal

        if t_tipe == "efektif": financial_data[t_key] += nominal
        else: financial_data["alokasi"][t_key] += nominal

        save_data(financial_data)
        await update.message.reply_text(f"🔄 **TRANSFER BERHASIL**\n📤 `{s_key}` ➔ 📥 `{t_key}`\n💰 Rp {nominal:,}".replace(",", "."), parse_mode="Markdown", reply_markup=get_main_keyboard())
    except: await update.message.reply_text("⚠️ Format: `/tf seabank to jago 500000`")

async def save_archive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = context.args[0].lower() if context.args else "all"
    current_date = financial_data["date"]
    keyboard = [[InlineKeyboardButton("✅ OKE SAVE", callback_data=f"confirm_save_{target}"), InlineKeyboardButton("❌ CANCEL", callback_data="cancel_save")]]
    await update.message.reply_text(f"📌 **KONFIRMASI ARSIP**\n🗓️ `{current_date}` | 📂 `{target.upper()}`\nSimpan?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    try:
        if data == "view_report":
            await query.edit_message_text(generate_report_text(), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]]), parse_mode="Markdown")
        
        elif data == "main_menu":
            await start(update, context)
            
        elif data == "menu_chart":
            keyboard = [[InlineKeyboardButton("📈 Grafik Balance", callback_data="chart_balance")], [InlineKeyboardButton("🛍️ Menu Grafik Sales", callback_data="menu_chart_sales")], [InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]]
            await query.edit_message_text("📊 **PILIH KATEGORI GRAFIK:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            
        elif data == "menu_chart_sales":
            keyboard = [
                [InlineKeyboardButton("💰 Rupiah", callback_data="chart_sales_rupiah"), InlineKeyboardButton("📦 Porsi", callback_data="chart_sales_porsi")],
                [InlineKeyboardButton("🧾 Nota", callback_data="chart_sales_nota"), InlineKeyboardButton("⬅️ Kembali", callback_data="menu_chart")]
            ]
            await query.edit_message_text("🛍️ **PILIH JENIS METRIK SALES (30 Hari Terakhir):**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            
        elif data == "chart_balance": 
            await generate_and_send_chart(query, context, "balance")
        
        elif data == "chart_sales_rupiah": 
            await generate_and_send_chart_from_db(query, context, "sales_rupiah", default_last_30=True)
        elif data == "chart_sales_porsi": 
            await generate_and_send_chart_from_db(query, context, "sales_porsi", default_last_30=True)
        elif data == "chart_sales_nota": 
            await generate_and_send_chart_from_db(query, context, "sales_nota", default_last_30=True)
        
        elif data in ["peak_season", "low_season"]:
            mode = "peak" if data == "peak_season" else "low"
            title = "Peak Season" if mode == "peak" else "Low Season"
            
            keyboard = [
                [InlineKeyboardButton("🌐 All Channel", callback_data=f"{mode}_ch_all"),
                InlineKeyboardButton("🏪 POS Customer", callback_data=f"{mode}_ch_POS Customer")],
                [InlineKeyboardButton("🛍️ Shopeefood", callback_data=f"{mode}_ch_Shopeefood"),
                InlineKeyboardButton("🛵 Grabfood", callback_data=f"{mode}_ch_Grabfood")],
                [InlineKeyboardButton("🚴 Gofood", callback_data=f"{mode}_ch_Gofood")],
                [InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]
            ]
            await query.edit_message_text(
                f"📊 **PILIH CHANNEL UNTUK {title.upper()}:**", 
                reply_markup=InlineKeyboardMarkup(keyboard), 
                parse_mode="Markdown"
            )

        elif data.startswith("peak_ch_") or data.startswith("low_ch_"):
            parts = data.split("_ch_", 1)
            mode = parts[0]
            channel = parts[1]
            
            title = "Peak Season" if mode == "peak" else "Low Season"
            await query.edit_message_text(f"⏳ Menganalisis {title} ({channel}) dari database...", parse_mode="Markdown")
            
            report = await asyncio.to_thread(analyze_season_from_db, mode, channel)
            
            await query.edit_message_text(
                report, 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]]), 
                parse_mode="Markdown"
            )
            
        elif data == "sync_data":
            await query.edit_message_text("⏳ Sedang menyinkronkan data 30 hari terakhir dari Kledo...", parse_mode="Markdown")
            report = await asyncio.to_thread(sync_missing_invoices)
            await query.edit_message_text(report, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]]), parse_mode="Markdown")

        elif data == "transfer_info":
            await query.edit_message_text("🔄 **MENU TRANSFER SALDO**\nContoh: `/tf seabank to jago 500000`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]]))
        
        elif data.startswith("confirm_save_"):
            target = data.replace("confirm_save_", "")
            current_date = financial_data["date"]
            if current_date not in financial_data["history"]: financial_data["history"][current_date] = {"balance": {}, "sales": {}}
            if target in ["balance", "all"]:
                tot_e = financial_data["seabank"] + financial_data["jago"] + financial_data["cash_tunai"]
                tot_ne = sum(financial_data["alokasi"].values())
                financial_data["history"][current_date]["balance"] = {"seabank": financial_data["seabank"], "jago": financial_data["jago"], "cash_tunai": financial_data["cash_tunai"], "total_efektif": tot_e, "total_non_efektif": tot_ne, "grand_total": tot_e + tot_ne}
            if target in ["sales", "overview", "all"]:
                financial_data["history"][current_date]["sales"] = {ch: d_val.copy() for ch, d_val in financial_data["sales"].items()}
            save_data(financial_data)
            await query.edit_message_text(f"✅ **ARSIP `{current_date}` DISIMPAN!**", parse_mode="Markdown")
            
        elif data == "cancel_save":
            await query.edit_message_text("❌ **Dibatalkan.**", parse_mode="Markdown")
        
        elif data == "confirm_insert":
            await query.edit_message_text("⏳ Memasukkan data...")
            saved, err = await asyncio.to_thread(insert_temp_json_to_db)
            await query.edit_message_text(err if err else f"✅ **{saved}** invoice disimpan.", parse_mode="Markdown", reply_markup=get_main_keyboard())
                
        elif data == "skip_insert":
            if os.path.exists("temp_invoices.json"): os.remove("temp_invoices.json")
            await query.edit_message_text("❌ Dibatalkan.", reply_markup=get_main_keyboard())
            
    except telegram.error.BadRequest as e:
        if "Message is not modified" not in str(e):
            print(f"Telegram error: {e}")
    except Exception as e:
        print(f"Unhandled error in callback: {e}")

async def get_invoice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("⚠️ Format salah!\nContoh: `/get_invoice 2026-08-09`", parse_mode="Markdown")
            return
            
        target_date = context.args[0]
        await update.message.reply_text(f"⏳ Sedang mengambil data invoice tanggal `{target_date}` dari Kledo...", parse_mode="Markdown")
        
        count, err = await asyncio.to_thread(fetch_invoices_to_json, target_date)
        if err:
            await update.message.reply_text(err)
            return
            
        keyboard = [
            [InlineKeyboardButton("📥 Insert to DB", callback_data="confirm_insert"),
             InlineKeyboardButton("❌ Skip / Ignore", callback_data="skip_insert")]
        ]
        await update.message.reply_text(
            f"✅ Berhasil menarik **{count}** invoice untuk tanggal `{target_date}` dan disimpan ke file sementara.\n\nApakah Anda ingin memasukkannya ke database?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Terjadi kesalahan: {e}")

async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Sedang mengecek & menyinkronkan data 30 hari terakhir dari Kledo ke database...", parse_mode="Markdown")
    report = await asyncio.to_thread(sync_missing_invoices)
    # Menggunakan send_long_text agar aman dari Message_too_long
    await send_long_text(update, None, report, parse_mode="Markdown", reply_markup=get_main_keyboard())

# --- CRON JOB HARIAN (Jam 07:00 WIB) ---
async def daily_sync_job(context: ContextTypes.DEFAULT_TYPE):
    print("Mengeksekusi Auto-Sync Harian (30 Hari Terakhir)...")
    report = await asyncio.to_thread(sync_missing_invoices)
    
    if GROUP_CHAT_ID:
        try:
            full_text = f"⏰ **AUTO-SYNC HARIAN (07:00 WIB)**\n\n{report}"
            await send_long_text(context.bot, GROUP_CHAT_ID, full_text, parse_mode="Markdown")
        except Exception as e:
            print(f"❌ Gagal mengirim notifikasi auto-sync ke grup: {e}")

def parse_shortcut_range_db(shortcut):
    today = dt.now()
    sc = shortcut.lower().strip()
    if sc == "this week": 
        start = today - timedelta(days=today.weekday())
        end = today
    elif sc == "last week": 
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
    elif sc == "this month": 
        start = today.replace(day=1)
        end = today
    elif sc == "last month": 
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    elif sc == "last 30 days": 
        start = today - timedelta(days=30)
        end = today
    elif sc == "this year": 
        start = today.replace(month=1, day=1)
        end = today
    elif sc == "last year": 
        start = today.replace(year=today.year-1, month=1, day=1)
        end = today.replace(year=today.year-1, month=12, day=31)
    else: 
        start = today - timedelta(days=30)
        end = today
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

async def generate_and_send_chart_from_db(update_or_query, context, target, start_date=None, end_date=None, default_last_30=True):
    try:
        conn = sqlite3.connect('kledo_invoices.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if not start_date or not end_date:
            if default_last_30:
                end_dt = dt.now()
                start_dt = end_dt - timedelta(days=30)
                start_date = start_dt.strftime("%Y-%m-%d")
                end_date = end_dt.strftime("%Y-%m-%d")
                cursor.execute("SELECT trans_date, amount, raw_data FROM invoices WHERE trans_date BETWEEN ? AND ? ORDER BY trans_date ASC", (start_date, end_date))
            else:
                cursor.execute("SELECT trans_date, amount, raw_data FROM invoices ORDER BY trans_date ASC")
        else:
            cursor.execute("SELECT trans_date, amount, raw_data FROM invoices WHERE trans_date BETWEEN ? AND ? ORDER BY trans_date ASC", (start_date, end_date))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            msg = f"⚠️ Tidak ada data invoice di database untuk rentang waktu tersebut ({start_date} s/d {end_date})."
            if hasattr(update_or_query, "message") and update_or_query.message:
                await update_or_query.message.reply_text(msg, parse_mode="Markdown")
            else:
                await update_or_query.edit_message_text(msg, parse_mode="Markdown")
            return

        daily_data = {}
        for row in rows:
            t_date = row["trans_date"]
            if not t_date:
                continue
            
            try:
                dt_obj = dt.strptime(t_date[:10], "%Y-%m-%d")
                date_key = dt_obj.strftime("%d %b %y")
            except:
                date_key = t_date

            if date_key not in daily_data:
                daily_data[date_key] = {"rupiah": 0, "nota": 0, "porsi": 0}

            amount = float(row["amount"] or 0)
            daily_data[date_key]["rupiah"] += amount
            daily_data[date_key]["nota"] += 1

            try:
                raw_json = json.loads(row["raw_data"])
                items = raw_json.get("items", [])
                total_qty = sum(float(item.get("qty", 0)) for item in items)
                daily_data[date_key]["porsi"] += total_qty
            except:
                pass

        if not daily_data:
            msg = "⚠️ Tidak ada data transaksi yang valid untuk dibuat grafik."
            if hasattr(update_or_query, "message") and update_or_query.message:
                await update_or_query.message.reply_text(msg, parse_mode="Markdown")
            else:
                await update_or_query.edit_message_text(msg, parse_mode="Markdown")
            return

        filtered_dates = list(daily_data.keys())
        metric_name = target.replace("sales_", "")
        
        vals = [daily_data[d].get(metric_name, 0) for d in filtered_dates]

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        plt.figure(figsize=(10, 5))
        plt.plot(filtered_dates, vals, marker='o', color='g', linewidth=2)
        plt.title(f"Grafik Penjualan ({metric_name.capitalize()})\nPeriode: {start_date} s/d {end_date}")
        plt.ylabel("Rupiah (Rp)" if metric_name == "rupiah" else "Jumlah")
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
            caption=f"📈 **Grafik Analisis Sales ({metric_name.upper()})**\n🗓️ Periode: {start_date} s/d {end_date}", 
            parse_mode="Markdown"
        )

    except Exception as e:
        msg = f"⚠️ Gagal membuat grafik dari database: {e}"
        logging.error(f"Error DB Chart: {e}")
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update_or_query.edit_message_text(msg, parse_mode="Markdown")

async def send_chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if not args:
            await generate_and_send_chart_from_db(update, context, "sales_rupiah", default_last_30=True)
            return

        target = args[0].lower()
        start_date, end_date = None, None
        args_text = " ".join(args[1:]).strip()

        if args_text:
            shortcut_keywords = ["this week", "last week", "this month", "last month", "last 30 days", "this year", "last year"]
            matched_shortcut = next((sc for sc in shortcut_keywords if sc in args_text.lower()), None)
            
            if matched_shortcut:
                start_date, end_date = parse_shortcut_range_db(matched_shortcut)
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
            await generate_and_send_chart_from_db(update, context, f"sales_{metric}", start_date, end_date, default_last_30=False)
        else:
            await generate_and_send_chart_from_db(update, context, "sales_rupiah", start_date, end_date, default_last_30=True)

    except Exception as e:
        await update.message.reply_text(
            "⚠️ Format perintah salah.\n\n"
            "**Contoh Shortcut:**\n"
            "`/chart rupiah \"last 30 days\"`\n"
            "`/chart rupiah \"this month\"`\n\n"
            "**Contoh Rentang Tanggal:**\n"
            "`/chart rupiah \"2026-08-01\" to \"2026-08-23\"`", 
            parse_mode="Markdown"
        )

def main():
    if not TELEGRAM_TOKEN: raise ValueError("❌ TELEGRAM_TOKEN tidak ditemukan di .env")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    wib_timezone = pytz.timezone('Asia/Jakarta')
    target_time = datetime.time(hour=7, minute=0, second=0, tzinfo=wib_timezone)
    app.job_queue.run_daily(daily_sync_job, time=target_time)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("se", set_efektif))
    app.add_handler(CommandHandler("sne", set_nonefektif))
    app.add_handler(CommandHandler("tf", transfer_saldo))
    app.add_handler(CommandHandler("save", save_archive_command))
    app.add_handler(CommandHandler("get_invoice", get_invoice_command))
    app.add_handler(CommandHandler("sync", sync_command))
    app.add_handler(CommandHandler("chart", send_chart_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Telegram Keuangan & Analisis Kledo sedang berjalan...")
    print("⏰ Cron Job Sinkronisasi Harian disetel pada pukul 07:00 WIB.")
    app.run_polling()

if __name__ == "__main__":
    main()