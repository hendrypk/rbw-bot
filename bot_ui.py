import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from data import financial_data

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 Lihat Laporan", callback_data="view_report")],
        [InlineKeyboardButton("📊 Menu Grafik", callback_data="menu_chart")],
        [
            InlineKeyboardButton("🔥 Peak Season", callback_data="peak_season"),
            InlineKeyboardButton("❄️ Low Season", callback_data="low_season")
        ],
        [
            InlineKeyboardButton("🔄 Transfer Saldo", callback_data="transfer_info"),
            InlineKeyboardButton("⚙️ Sync Data Kledo", callback_data="sync_data")
        ],
        [InlineKeyboardButton("📖 Cara Pakai", callback_data="help_menu")],
    ])

def generate_report_text():
    total_efektif = financial_data["seabank"] + financial_data["jago"] + financial_data["cash_tunai"]
    total_non_efektif = sum(financial_data["alokasi"].values())
    grand_total = total_efektif + total_non_efektif
    ratio = ((total_efektif / grand_total) * 100 if grand_total > 0 else 0)

    sales = financial_data["sales"]
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

    text += f"\n└ 🟥 **TOTAL NON-EFEKTIF: Rp {total_non_efektif:,}**\n\n==================================\n🛍️ **3. REKAP PENJUALAN & WALLET**\n----------------------------------"
    
    for ch_name, ch_data in sales.items():
        w_label = ch_data['wallet'].replace('_', ' ').title()
        text += f"\n├ {ch_name.capitalize():<10} : {ch_data['nota']} Nota | {ch_data['porsi']} Porsi | Rp {ch_data['rupiah']:,} ➔ *{w_label}*"

    text += f"\n==================================\n💰 **SUMMARY & LIQUIDITY**\n----------------------------------\n💎 Grand Total Cash : Rp {grand_total:,}\n📊 Ratio Likuiditas : {ratio:.1f}% (Ready Use)\n=================================="
    return text.replace(",", ".")

def parse_wallet_key(query):
    query = query.lower().strip()
    if "seabank" in query: return "seabank"
    if "jago" in query: return "jago"
    if "cash" in query or "tunai" in query: return "cash_tunai"
    return None

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

async def generate_and_send_chart(update_or_query, context, target, start_date=None, end_date=None):
    try:
        if not financial_data["history"]:
            msg = "⚠️ Belum ada data history! Gunakan `/save all` terlebih dahulu."
            if hasattr(update_or_query, "message") and update_or_query.message: await update_or_query.message.reply_text(msg, parse_mode="Markdown")
            else: await update_or_query.edit_message_text(msg, parse_mode="Markdown")
            return

        all_dates = list(financial_data["history"].keys())
        filtered_dates = all_dates
        if start_date and end_date:
            try:
                start_idx = next((i for i, d in enumerate(all_dates) if start_date.lower() in d.lower()), 0)
                end_idx = next((i for i, d in enumerate(all_dates) if end_date.lower() in d.lower()), len(all_dates)-1)
                filtered_dates = all_dates[min(start_idx, end_idx):max(start_idx, end_idx)+1]
            except: pass

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
        
        # Hilangkan underscore agar tidak dianggap format italic oleh Telegram
        safe_target = target.replace('_', ' ').upper()
        caption_text = f"📈 *Grafik Analisis ({safe_target})*\n🗓️ Periode: {filtered_dates[0]} s/d {filtered_dates[-1]}"
        
        await context.bot.send_photo(chat_id=chat_id, photo=buf, caption=caption_text, parse_mode="Markdown")

    except Exception as e:
        msg = f"⚠️ Gagal membuat grafik: {e}"
        if hasattr(update_or_query, "message") and update_or_query.message: await update_or_query.message.reply_text(msg, parse_mode="Markdown")
        else: await update_or_query.edit_message_text(msg, parse_mode="Markdown")