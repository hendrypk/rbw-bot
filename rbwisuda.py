"""
======================================================================
🤖 BOT TELEGRAM: LAPORAN KEUANGAN HARIAN (LOCAL VERSION)
======================================================================
"""

import os
import logging
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# Muat variabel environment dari file .env lokal
load_dotenv()

# 1. Konfigurasi Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# 2. State Sederhana untuk Penyimpanan Data Sementara
financial_data = {
    "date": "17 August 2026",
    "seabank": 761190,
    "cash_tunai": 1878000,
    "alokasi": {
        "Gaji Akmal": 80000,
        "Gaji Owner": 59000,
        "Sewa Lapak": 700000,
        "Sewa Kontainer": 300000,
        "BMT": 330731,
        "Cabang 2": 459447,
    },
}

# --- FUNGSI UTAMA LAPORAN ---
def generate_report_text():
    total_efektif = financial_data["seabank"] + financial_data["cash_tunai"]
    total_non_efektif = sum(financial_data["alokasi"].values())
    grand_total = total_efektif + total_non_efektif
    ratio = (
        (total_efektif / grand_total) * 100 if grand_total > 0 else 0
    )

    text = f"""==================================
📊 **DAILY FINANCIAL REPORT (LOCAL)**
🗓️ Per Tanggal: {financial_data['date']}
==================================

💵 **1. SALDO EFEKTIF (READY CASH)**
----------------------------------
├ Seabank         : Rp {financial_data['seabank']:,}
├ Cash (Tunai)    : Rp {financial_data['cash_tunai']:,}
└ 🟩 **TOTAL EFEKTIF: Rp {total_efektif:,}**

🔒 **2. SALDO NON-EFEKTIF (ALOKASI)**
----------------------------------"""

    for k, v in financial_data["alokasi"].items():
        text += f"\n├ {k:<15} : Rp {v:,}"

    text += f"""
└ 🟥 **TOTAL NON-EFEKTIF: Rp {total_non_efektif:,}**

==================================
💰 **SUMMARY & LIQUIDITY**
----------------------------------
💎 Grand Total Cash : Rp {grand_total:,}
📊 Ratio Likuiditas : {ratio:.1f}% (Ready Use)
=================================="""
    return text.replace(",", ".")


# --- HELPER: Keyboard Menu Utama ---
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 Lihat Laporan", callback_data="view_report")],
        [InlineKeyboardButton("📖 Cara Pakai", callback_data="help_menu")],
    ])


# --- HANDLER: Perintah Teks (Command) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "🤖 **BOT LAPORAN KEUANGAN HARIAN (LOCAL)**\n\n"
        "Halo! Silakan pilih menu di bawah ini:"
    )

    if update.message:
        await update.message.reply_text(
            welcome_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown"
        )
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            welcome_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown"
        )


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        generate_report_text(), 
        parse_mode="Markdown", 
        reply_markup=get_main_keyboard()
    )


async def set_efektif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        nama = context.args[0].lower()
        nominal = int(context.args[1])
        if "seabank" in nama:
            financial_data["seabank"] = nominal
        elif "cash" in nama or "tunai" in nama:
            financial_data["cash_tunai"] = nominal
        else:
            await update.message.reply_text(
                "⚠️ Akun efektif tidak dikenal. Gunakan: Seabank atau Cash",
                reply_markup=get_main_keyboard()
            )
            return
        
        await update.message.reply_text(
            f"✅ Saldo efektif `{nama}` berhasil diupdate ke Rp {nominal:,}".replace(",", "."),
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    except (IndexError, ValueError):
        await update.message.reply_text(
            "⚠️ Format salah!\nContoh: `/se Seabank 800000`", 
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )


async def set_nonefektif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 2:
            raise ValueError
        
        nama = " ".join(context.args[:-1])
        nominal = int(context.args[-1])
        
        matched_key = None
        for key in financial_data["alokasi"].keys():
            if key.lower() == nama.lower():
                matched_key = key
                break

        if matched_key:
            financial_data["alokasi"][matched_key] = nominal
            await update.message.reply_text(
                f"✅ Saldo non-efektif `{matched_key}` diupdate ke Rp {nominal:,}".replace(",", "."),
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                f"⚠️ Nama alokasi `{nama}` tidak ditemukan di daftar.",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
    except (IndexError, ValueError):
        await update.message.reply_text(
            "⚠️ Format salah!\nContoh: `/sne \"Gaji Akmal\" 100000`", 
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )


async def reset_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        tanggal_baru = " ".join(context.args)
        financial_data["date"] = tanggal_baru
        await update.message.reply_text(
            f"✅ Tanggal laporan berhasil diubah ke: **{tanggal_baru}**", 
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "⚠️ Format salah!\nContoh: `/resetdate 17 August 2026`", 
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )


# --- HANDLER: Tombol Interaktif ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "view_report":
        report = generate_report_text()
        keyboard = [
            [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="main_menu")],
        ]
        await query.edit_message_text(
            report,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )

    elif data == "main_menu":
        await start(update, context)

    elif data == "help_menu":
        help_text = (
            "🤖 **CARA PAKAI BOT (LOCAL)**\n\n"
            "• `/report` : Tampilkan Laporan.\n"
            "• `/se <nama> <nominal>` : Update saldo efektif.\n"
            "• `/sne <nama> <nominal>` : Update saldo non-efektif.\n"
            "• `/resetdate <tanggal>` : Update tanggal laporan.\n"
        )
        keyboard = [
            [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )


# --- MAIN FUNCTION ---
def main():
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TOKEN:
        raise ValueError("❌ TELEGRAM_TOKEN tidak ditemukan di file .env!")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("se", set_efektif))
    app.add_handler(CommandHandler("sne", set_nonefektif))
    app.add_handler(CommandHandler("resetdate", reset_date))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Telegram Laporan Keuangan (Local) sedang berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()