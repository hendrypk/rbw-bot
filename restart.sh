#!/bin/bash

echo "🔄 Sedang merestart bot Telegram (Lokal)..."

# 1. Matikan proses python yang menjalankan bot jika ada
PID=$(pgrep -f main.py)
if [ -n "$PID" ]; then
    kill $PID
    echo "🛑 Bot lama dengan PID $PID dimatikan."
else
    echo "⚠️ Tidak ada bot yang sedang berjalan."
fi

# 2. Muat variabel dari file .env lokal
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# 3. Jalankan bot di background
nohup python3 main.py > bot.log 2>&1 &

echo "✅ Bot berhasil dijalankan ulang di background!"

# 4. Kirim notifikasi uji coba ke Telegram (Bypass jika TELEGRAM_TOKEN atau GROUP_CHAT_ID kosong)
if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$GROUP_CHAT_ID" ]; then
    MESSAGE="💻 [LOCAL] Bot Laporan Keuangan berhasil direstart dan aktif!"
    curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/sendMessage" \
        -d "chat_id=$GROUP_CHAT_ID" \
        -d "text=$MESSAGE" > /dev/null
    echo "📨 Notifikasi uji coba terkirim ke Telegram!"
else
    echo "ℹ️ Notifikasi Telegram dilewati (GROUP_CHAT_ID atau TOKEN kosong)."
fi