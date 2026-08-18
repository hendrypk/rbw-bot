import asyncio
import shlex
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

from config import TELEGRAM_TOKEN
from data import financial_data, save_data
from kledo_api import fetch_invoices_to_json, insert_temp_json_to_db, analyze_peak_hours_from_db
from bot_ui import (
    get_main_keyboard, generate_report_text, parse_wallet_key, 
    parse_shortcut_range, generate_and_send_chart
)

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
        parts = shlex.split(" ".join(context.args))
        if parts[1].lower() in ["to", "ke"]:
            sumber, tujuan, nominal = parts[0].lower(), parts[2].lower(), int(parts[3].replace(".", ""))
        else:
            sumber, tujuan, nominal = parts[0].lower(), parts[1].lower(), int(parts[2].replace(".", ""))

        def find_akun(query):
            if "seabank" in query: return "seabank", "efektif"
            if "jago" in query: return "jago", "efektif"
            if "cash" in query or "tunai" in query: return "cash_tunai", "efektif"
            matched = next((k for k in financial_data["alokasi"] if k.lower() == query), None)
            return (matched, "alokasi") if matched else (None, None)

        s_key, s_tipe = find_akun(sumber)
        t_key, t_tipe = find_akun(tujuan)
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

async def kledo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Sedang menyambungkan ke Kledo, mengambil data & menganalisis...")
    result_text = await asyncio.to_thread(run_kledo_analysis_pipeline)
    await update.message.reply_text(result_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "view_report":
        await query.edit_message_text(generate_report_text(), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]]), parse_mode="Markdown")
    elif data == "main_menu":
        await start(update, context)
    elif data == "menu_chart":
        keyboard = [[InlineKeyboardButton("📈 Grafik Balance", callback_data="chart_balance")], [InlineKeyboardButton("🛍️ Menu Grafik Sales", callback_data="menu_chart_sales")], [InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]]
        await query.edit_message_text("📊 **PILIH KATEGORI GRAFIK:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data == "menu_chart_sales":
        keyboard = [[InlineKeyboardButton("💰 Rupiah", callback_data="chart_sales_rupiah"), InlineKeyboardButton("📦 Porsi", callback_data="chart_sales_porsi")], [InlineKeyboardButton("🧾 Nota", callback_data="chart_sales_nota"), InlineKeyboardButton("⬅️ Kembali", callback_data="menu_chart")]]
        await query.edit_message_text("🛍️ **PILIH JENIS METRIK SALES:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data == "chart_balance": await generate_and_send_chart(query, context, "balance")
    elif data == "chart_sales_rupiah": await generate_and_send_chart(query, context, "sales_rupiah")
    elif data == "chart_sales_porsi": await generate_and_send_chart(query, context, "sales_porsi")
    elif data == "chart_sales_nota": await generate_and_send_chart(query, context, "sales_nota")
    
    elif data == "kledo_analysis":
        await query.edit_message_text("⏳ Sedang menyambungkan ke Kledo & menganalisis data...", parse_mode="Markdown")
        result_text = await asyncio.to_thread(run_kledo_analysis_pipeline)
        await query.edit_message_text(result_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]]), parse_mode="Markdown")

    elif data == "transfer_info":
        await query.edit_message_text("🔄 **MENU TRANSFER SALDO**\nContoh: `/tf seabank to jago 500000`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="main_menu")]]))
    
    elif data.startswith("confirm_save_"):
        target, current_date = data.replace("confirm_save_", ""), financial_data["date"]
        if current_date not in financial_data["history"]: financial_data["history"][current_date] = {"balance": {}, "sales": {}}
        if target in ["balance", "all"]:
            tot_e = financial_data["seabank"] + financial_data["jago"] + financial_data["cash_tunai"]
            tot_ne = sum(financial_data["alokasi"].values())
            financial_data["history"][current_date]["balance"] = {"seabank": financial_data["seabank"], "jago": financial_data["jago"], "cash_tunai": financial_data["cash_tunai"], "total_efektif": tot_e, "total_non_efektif": tot_ne, "grand_total": tot_e + tot_ne}
        if target in ["sales", "overview", "all"]:
            financial_data["history"][current_date]["sales"] = {ch: d_val.copy() for ch, d_val in financial_data["sales"].items()}
        save_data(financial_data)
        await query.edit_message_text(f"✅ **ARSIP TANGGAL `{current_date}` BERHASIL DISIMPAN!**", parse_mode="Markdown")
    elif data == "cancel_save":
        await query.edit_message_text("❌ **Penyimpanan arsip dibatalkan.**", parse_mode="Markdown")
    
    elif data == "confirm_insert":
        await query.edit_message_text("⏳ Memasukkan data ke database SQLite...")
        saved, err = await asyncio.to_thread(insert_temp_json_to_db)
        if err:
            await query.edit_message_text(err)
        else:
            await query.edit_message_text(f"✅ Berhasil! **{saved}** invoice telah disimpan ke database.", parse_mode="Markdown", reply_markup=get_main_keyboard())
            
    elif data == "skip_insert":
        import os
        if os.path.exists("temp_invoices.json"):
            os.remove("temp_invoices.json")
        await query.edit_message_text("❌ Proses dibatalkan. File JSON sementara dihapus.", reply_markup=get_main_keyboard())

# Tambahkan import fungsi baru di bagian atas main.py:

# 1. Command untuk ambil data ke JSON
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
            
        # Jika sukses, berikan tombol konfirmasi
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

# 2. Command untuk melihat Analisis Peak Hour dari Database
async def peak_hour_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Menganalisis peak hours dari database...")
    report = await asyncio.to_thread(analyze_peak_hours_from_db)
    await update.message.reply_text(report, reply_markup=get_main_keyboard())

def main():
    if not TELEGRAM_TOKEN: raise ValueError("❌ TELEGRAM_TOKEN tidak ditemukan di .env")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("se", set_efektif))
    app.add_handler(CommandHandler("sne", set_nonefektif))
    app.add_handler(CommandHandler("tf", transfer_saldo))
    app.add_handler(CommandHandler("save", save_archive_command))
    app.add_handler(CommandHandler("kledo", kledo_command))
    app.add_handler(CommandHandler("get_invoice", get_invoice_command))
    app.add_handler(CommandHandler("peak", peak_hour_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Telegram Keuangan & Analisis Kledo sedang berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()