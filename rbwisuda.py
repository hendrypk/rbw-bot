"""
======================================================================
🤖 BOT TELEGRAM: LAPORAN KEUANGAN HARIAN
======================================================================
"""

import os
import json
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

# --- SISTEM PENYIMPANAN DATA (JSON) ---
DATA_FILE = "data.json"

default_financial_data = {
    "date": "17 August 2026",
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
        "Saving": 0,          # <--- ALOKASI SAVING DITAMBAHKAN
    },
}

def load_data():
    """Membaca data dari file JSON. Jika file belum ada, gunakan default."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            
            # PENTING: Sinkronisasi jika ada alokasi baru (misal 'Saving') 
            # yang belum ada di file data.json versi lama.
            if "alokasi" in data:
                for key, default_val in default_financial_data["alokasi"].items():
                    if key not in data["alokasi"]:
                        data["alokasi"][key] = default_val
            return data
            
    return default_financial_data.copy()

def save_data():
    """Menyimpan data saat ini ke file JSON."""
    with open(DATA_FILE, "w") as f:
        json.dump(financial_data, f, indent=4)

# Inisialisasi data saat bot menyala
financial_data = load_data()


# --- FUNGSI UTAMA LAPORAN ---
def generate_report_text():
    total_efektif = financial_data["seabank"] + financial_data["jago"] + financial_data["cash_tunai"]
    total_non_efektif = sum(financial_data["alokasi"].values())
    grand_total = total_efektif + total_non_efektif
    ratio = (
        (total_efektif / grand_total) * 100 if grand_total > 0 else 0
    )

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
        "🤖 **BOT LAPORAN KEUANGAN HARIAN**\n\n"
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
        elif "jago" in nama:
            financial_data["jago"] = nominal
        elif "cash" in nama or "tunai" in nama:
            financial_data["cash_tunai"] = nominal
        else:
            await update.message.reply_text(
                "⚠️ Akun efektif tidak dikenal. Gunakan: Seabank, Jago, atau Cash",
                reply_markup=get_main_keyboard()
            )
            return
        
        save_data()
        
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
            save_data()
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
        save_data()
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


async def bulk_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = update.message.text.split('\n')[1:]
    
    if not lines:
        contoh = (
            "⚠️ **Format salah!**\nContoh penggunaan:\n\n"
            "`/bulk`\n"
            "`seabank 1500000`\n"
            "`jago 500000`\n"
            "`cash 200000`\n"
            "`saving 300000`\n"
            "`sewa lapak 700000`"
        )
        await update.message.reply_text(contoh, parse_mode="Markdown", reply_markup=get_main_keyboard())
        return

    success_updates = []
    errors = []

    for line in lines:
        line = line.strip()
        if not line: continue
        
        parts = line.rsplit(' ', 1)
        if len(parts) != 2:
            errors.append(f"Format baris salah: `{line}`")
            continue
            
        nama_input, nominal_str = parts[0].lower().strip(), parts[1].replace(".", "")
        try:
            nominal = int(nominal_str)
        except ValueError:
            errors.append(f"Nominal tidak valid: `{line}`")
            continue
        
        # 1. Cek Saldo Efektif
        if "seabank" in nama_input:
            financial_data["seabank"] = nominal
            success_updates.append(f"✅ Seabank: Rp {nominal:,}".replace(",", "."))
        elif "jago" in nama_input:
            financial_data["jago"] = nominal
            success_updates.append(f"✅ Wallet Jago: Rp {nominal:,}".replace(",", "."))
        elif "cash" in nama_input or "tunai" in nama_input:
            financial_data["cash_tunai"] = nominal
            success_updates.append(f"✅ Cash/Tunai: Rp {nominal:,}".replace(",", "."))
        
        # 2. Cek Saldo Non-Efektif (Alokasi)
        else:
            matched_key = None
            for key in financial_data["alokasi"].keys():
                if key.lower() == nama_input:
                    matched_key = key
                    break
            
            if matched_key:
                financial_data["alokasi"][matched_key] = nominal
                success_updates.append(f"✅ {matched_key}: Rp {nominal:,}".replace(",", "."))
            else:
                errors.append(f"Nama tidak ditemukan: `{nama_input}`")

    # Simpan semua perubahan bulk ke file
    if success_updates:
        save_data()

    # 3. Buat Laporan Hasil Update
    response_text = "📊 **HASIL BULK UPDATE:**\n\n"
    if success_updates:
        response_text += "\n".join(success_updates) + "\n\n"
    if errors:
        response_text += "⚠️ **Gagal Update (Cek Penulisan):**\n" + "\n".join(errors)
        
    await update.message.reply_text(
        response_text, 
        parse_mode="Markdown", 
        reply_markup=get_main_keyboard()
    )

async def transfer_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Format input didukung:
    /tf <sumber> to <tujuan> <nominal>
    /tf <sumber> ke <tujuan> <nominal>
    /tf <sumber> <tujuan> <nominal>
    Contoh: /tf seabank to jago 500000
    Contoh: /tf cash ke "gaji akmal" 100000
    """
    try:
        args_text = " ".join(context.args)
        import shlex
        parts = shlex.split(args_text)
        
        if len(parts) < 3:
            raise ValueError
            
        # Jika kata kedua adalah "to" atau "ke", kita abaikan dan geser index-nya
        if parts[1].lower() in ["to", "ke"]:
            if len(parts) < 4:
                raise ValueError
            sumber_input = parts[0].lower()
            tujuan_input = parts[2].lower()
            nominal_raw = parts[3]
        else:
            sumber_input = parts[0].lower()
            tujuan_input = parts[1].lower()
            nominal_raw = parts[2]
        
        # Bersihkan format titik/koma pada nominal
        nominal_str = nominal_raw.replace(".", "").replace(",", "")
        nominal = int(nominal_str)
        
        if nominal <= 0:
            await update.message.reply_text("⚠️ Nominal transfer harus lebih besar dari 0!", reply_markup=get_main_keyboard())
            return

        # --- FUNGSI HELPER PENCARI AKUN ---
        def find_akun(query):
            query = query.lower()
            if "seabank" in query: return "seabank", "efektif"
            if "jago" in query: return "jago", "efektif"
            if "cash" in query or "tunai" in query: return "cash_tunai", "efektif"
            
            # Cek di alokasi non-efektif
            for key in financial_data["alokasi"].keys():
                if key.lower() == query:
                    return key, "alokasi"
            return None, None

        sumber_key, sumber_tipe = find_akun(sumber_input)
        tujuan_key, tujuan_tipe = find_akun(tujuan_input)

        if not sumber_key:
            await update.message.reply_text(f"⚠️ Akun sumber `{sumber_input}` tidak ditemukan!", parse_mode="Markdown", reply_markup=get_main_keyboard())
            return
        if not tujuan_key:
            await update.message.reply_text(f"⚠️ Akun tujuan `{tujuan_input}` tidak ditemukan!", parse_mode="Markdown", reply_markup=get_main_keyboard())
            return
            
        if sumber_key == tujuan_key:
            await update.message.reply_text("⚠️ Akun sumber dan tujuan tidak boleh sama!", reply_markup=get_main_keyboard())
            return

        # Ambil saldo saat ini
        saldo_sumber = financial_data["seabank"] if sumber_tipe == "efektif" and sumber_key == "seabank" else \
                       financial_data["jago"] if sumber_tipe == "efektif" and sumber_key == "jago" else \
                       financial_data["cash_tunai"] if sumber_tipe == "efektif" and sumber_key == "cash_tunai" else \
                       financial_data["alokasi"][sumber_key]

        if saldo_sumber < nominal:
            await update.message.reply_text(
                f"⚠️ **Saldo tidak mencukupi!**\nSaldo `{sumber_key}` saat ini hanya Rp {saldo_sumber:,}".replace(",", "."),
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
            return

        # --- EKSEKUSI TRANSFER ---
        if sumber_tipe == "efektif":
            financial_data[sumber_key] -= nominal
        else:
            financial_data["alokasi"][sumber_key] -= nominal

        if tujuan_tipe == "efektif":
            financial_data[tujuan_key] += nominal
        else:
            financial_data["alokasi"][tujuan_key] += nominal

        save_data()

        nama_sumber_label = sumber_key.replace("_", " ").title() if sumber_tipe == "efektif" else sumber_key
        nama_tujuan_label = tujuan_key.replace("_", " ").title() if tujuan_tipe == "efektif" else tujuan_key

        pesan_sukses = (
            f"🔄 **TRANSFER BERHASIL**\n\n"
            f"📤 Dari : `{nama_sumber_label}`\n"
            f"📥 Ke   : `{nama_tujuan_label}`\n"
            f"💰 Nominal: **Rp {nominal:,}**\n".replace(",", ".")
        )
        
        await update.message.reply_text(pesan_sukses, parse_mode="Markdown", reply_markup=get_main_keyboard())

    except (ValueError, IndexError):
        contoh = (
            "⚠️ **Format salah!**\n"
            "Gunakan format:\n"
            "`/tf <sumber> to <tujuan> <nominal>`\n"
            "*(atau tanpa 'to' juga bisa)*\n\n"
            "Contoh:\n"
            "`/tf seabank to jago 500000`\n"
            "`/tf cash ke \"gaji akmal\" 100000`\n"
            "`/tf seabank saving 250000`"
        )
        await update.message.reply_text(contoh, parse_mode="Markdown", reply_markup=get_main_keyboard())

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
            "🤖 **CARA PAKAI BOT**\n\n"
            "• `/report` : Tampilkan Laporan.\n"
            "• `/se <nama> <nominal>` : Update saldo efektif tunggal.\n"
            "• `/sne <nama> <nominal>` : Update saldo non-efektif tunggal.\n"
            "• `/bulk` : Update banyak saldo sekaligus (Gunakan *Enter/Baris Baru*).\n"
            "• `/tf <sumber> <tujuan> <nominal>` : Transfer dana antar akun.\n"
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
    app.add_handler(CommandHandler("bulk", bulk_update))
    app.add_handler(CommandHandler("transfer_saldo", bulk_update))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Telegram Laporan Keuangan sedang berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()