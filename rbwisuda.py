"""
======================================================================
🤖 BOT TELEGRAM: LAPORAN KEUANGAN, REKAP PENJUALAN & GRAFIK INTERAKTIF
======================================================================
"""

import os
import json
import logging
import io
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


# --- FUNGSI HELPER ---
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
        [InlineKeyboardButton("📖 Cara Pakai", callback_data="help_menu")],
    ])


# --- HANDLER: Perintah Teks (Command) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = "🤖 **BOT LAPORAN KEUANGAN HARIAN**\n\nSilakan pilih menu di bawah ini:"
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
            await update.message.reply_text("⚠️ Akun efektif tidak dikenal.", reply_markup=get_main_keyboard())
            return
        save_data()
        await update.message.reply_text(f"✅ Saldo efektif `{nama}` diupdate ke Rp {nominal:,}".replace(",", "."), parse_mode="Markdown", reply_markup=get_main_keyboard())
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Format salah! Contoh: `/se Seabank 800000`", parse_mode="Markdown", reply_markup=get_main_keyboard())


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
        await update.message.reply_text("⚠️ Format salah! Contoh: `/sne \"Gaji Akmal\" 100000`", parse_mode="Markdown", reply_markup=get_main_keyboard())


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
        await update.message.reply_text("⚠️ Format salah! Contoh: `/sales offline 15 25 750000`", parse_mode="Markdown", reply_markup=get_main_keyboard())


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
        await update.message.reply_text("⚠️ Format salah! Contoh: `/setchannel offline seabank`", parse_mode="Markdown", reply_markup=get_main_keyboard())


async def reset_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        tanggal_baru = " ".join(context.args)
        financial_data["date"] = tanggal_baru
        save_data()
        await update.message.reply_text(f"✅ Tanggal aktif diubah ke: **{tanggal_baru}**", parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text("⚠️ Format salah! Contoh: `/resetdate 17 Aug 26`", parse_mode="Markdown", reply_markup=get_main_keyboard())


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


# --- GENERATE GRAFIK (MATPLOTLIB) ---
async def generate_and_send_chart(update_or_query, context, target):
    try:
        if not financial_data["history"]:
            msg = "⚠️ Belum ada data history! Gunakan `/save all` terlebih dahulu."
            if hasattr(update_or_query, "message") and update_or_query.message:
                await update_or_query.message.reply_text(msg, parse_mode="Markdown")
            else:
                await update_or_query.edit_message_text(msg, parse_mode="Markdown")
            return

        dates = list(financial_data["history"].keys())

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        plt.figure(figsize=(10, 5))

        if target == "balance":
            grand_totals = [d_val.get("balance", {}).get("grand_total", 0) for d_val in financial_data["history"].values()]
            plt.plot(dates, grand_totals, marker='o', color='b', linestyle='-', linewidth=2)
            plt.title("Grafik Grand Total Balance per Tanggal")
            plt.ylabel("Rupiah (Rp)")
        else:
            metric = target.replace("sales_", "")
            channels = ["offline", "shopeefood", "gofood", "grabfood"]
            for ch in channels:
                values = [d_val.get("sales", {}).get(ch, {}).get(metric, 0) for d_val in financial_data["history"].values()]
                plt.plot(dates, values, marker='o', label=ch.capitalize(), linewidth=2)
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

        chat_id = update_or_query.effective_chat.id
        await context.bot.send_photo(chat_id=chat_id, photo=buf, caption=f"📈 **Grafik Analisis ({target.upper()})**", parse_mode="Markdown")

    except Exception as e:
        msg = f"⚠️ Gagal membuat grafik: {e}"
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update_or_query.edit_message_text(msg, parse_mode="Markdown")


async def send_chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = context.args[0].lower() if context.args else "sales_rupiah"
    if target == "balance":
        await generate_and_send_chart(update, context, "balance")
    elif target in ["porsi", "nota", "rupiah"]:
        await generate_and_send_chart(update, context, f"sales_{target}")
    else:
        await generate_and_send_chart(update, context, "sales_rupiah")


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
        try: nominal = int(nominal_str)
        except ValueError: errors.append(f"Nominal tidak valid: `{line}`"); continue
        
        if "seabank" in nama_input: financial_data["seabank"] = nominal; success_updates.append(f"✅ Seabank: Rp {nominal:,}".replace(",", "."))
        elif "jago" in nama_input: financial_data["jago"] = nominal; success_updates.append(f"✅ Jago: Rp {nominal:,}".replace(",", "."))
        elif "cash" in nama_input or "tunai" in nama_input: financial_data["cash_tunai"] = nominal; success_updates.append(f"✅ Cash: Rp {nominal:,}".replace(",", "."))
        else:
            matched_key = next((k for k in financial_data["alokasi"] if k.lower() == nama_input), None)
            if matched_key: financial_data["alokasi"][matched_key] = nominal; success_updates.append(f"✅ {matched_key}: Rp {nominal:,}".replace(",", "."))
            else: errors.append(f"Nama tidak ditemukan: `{nama_input}`")

    if success_updates: save_data()
    await update.message.reply_text("📊 **BULK UPDATE SELESAI**", reply_markup=get_main_keyboard())


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
        if not sumber_key or not tujuan_key: return

        saldo_sumber = financial_data[sumber_key] if sumber_tipe == "efektif" else financial_data["alokasi"][sumber_key]
        if saldo_sumber < nominal: return

        if sumber_tipe == "efektif": financial_data[sumber_key] -= nominal
        else: financial_data["alokasi"][sumber_key] -= nominal

        if tujuan_tipe == "efektif": financial_data[tujuan_key] += nominal
        else: financial_data["alokasi"][tujuan_key] += nominal

        save_data()
        await update.message.reply_text(f"🔄 **TRANSFER BERHASIL**\n💰 Rp {nominal:,}".replace(",", "."), reply_markup=get_main_keyboard())
    except (ValueError, IndexError):
        pass


# --- HANDLER: Tombol Interaktif ---
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
            [InlineKeyboardButton("🛍️ Grafik Sales", callback_data="menu_chart_sales")],
            [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="main_menu")]
        ]
        await query.edit_message_text("📊 **PILIH KATEGORI GRAFIK:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "menu_chart_sales":
        keyboard = [
            [InlineKeyboardButton("💰 Grafik Rupiah", callback_data="chart_sales_rupiah")],
            [InlineKeyboardButton("📦 Grafik Porsi", callback_data="chart_sales_porsi")],
            [InlineKeyboardButton("🧾 Grafik Nota", callback_data="chart_sales_nota")],
            [InlineKeyboardButton("⬅️ Kembali ke Menu Grafik", callback_data="menu_chart")]
        ]
        await query.edit_message_text("🛍️ **PILIH JENIS GRAFIK SALES:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "chart_balance":
        await generate_and_send_chart(query, context, "balance")
    elif data == "chart_sales_rupiah":
        await generate_and_send_chart(query, context, "sales_rupiah")
    elif data == "chart_sales_porsi":
        await generate_and_send_chart(query, context, "sales_porsi")
    elif data == "chart_sales_nota":
        await generate_and_send_chart(query, context, "sales_nota")
        
    elif data == "help_menu":
        help_text = (
            "🤖 **CARA PAKAI BOT**\n\n"
            "• `/report` : Laporan harian.\n"
            "• `/resetdate 17 Aug 26` : Ubah tanggal aktif.\n"
            "• `/save all` : Simpan/timpa arsip tanggal.\n"
            "• Tombol Interaktif : Akses menu grafik dengan mudah.\n"
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
                "grand_total": total_efektif + total_non_efektif
            }

        if target in ["sales", "overview", "all"]:
            sales_summary = {ch: d_val.copy() for ch, d_val in financial_data["sales"].items()}
            financial_data["history"][current_date]["sales"] = sales_summary

        save_data()
        await query.edit_message_text(f"✅ **ARSIP TANGGAL `{current_date}` BERHASIL DISIMPAN!**", parse_mode="Markdown")

    elif data == "cancel_save":
        await query.edit_message_text("❌ **Penyimpanan dibatalkan.**", parse_mode="Markdown")


# --- MAIN FUNCTION ---
def main():
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TOKEN: raise ValueError("❌ TELEGRAM_TOKEN tidak ditemukan!")

    app = ApplicationBuilder().token(TOKEN).build()

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
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Telegram Laporan Keuangan sedang berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()