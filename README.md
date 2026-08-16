# 🤖 Telegram Financial Report Bot

Bot Telegram sederhana berbasis Python untuk mengelola dan menampilkan laporan keuangan harian (Saldo Efektif & Non-Efektif/Alokasi) secara cepat dan interaktif.

---

## 📂 Struktur Folder Project

```text
bot-keuangan/
├── .env              # Konfigurasi Token Bot & Chat ID (Rahasia)
├── requirements.txt  # Daftar library Python yang dibutuhkan
├── restart.sh        # Script otomatis untuk restart bot & kirim notifikasi
├── rbwisuda.py       # File utama program bot Telegram
└── README.md         # Dokumentasi project
```

---

## ⚙️ Persyaratan Sistem

Pastikan komputer/VPS Anda sudah terinstal:
* Python 3.8 atau versi terbaru
* `pip` (Python Package Manager)

---

## 🚀 Cara Instalasi

1. **Letakkan Project** di direktori kerja Anda.
2. **Install Library Pendukung:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Konfigurasi File `.env`:**
   Buat file bernama `.env` di root folder, lalu isi dengan format berikut:
   ```env
   TELEGRAM_TOKEN=masukkan_token_bot_anda_di_sini
   GROUP_CHAT_ID=-100xxxxxxxxxx
   ```
4. **Berikan Hak Akses Eksekusi pada Script Restart** (Linux / Mac / Git Bash):
   ```bash
   chmod +x restart.sh
   ```

---

## 🎮 Cara Kontrol & Maintenance Bot

Untuk menjalankan, merestart, atau memantau bot, Anda bisa menggunakan perintah-perintah berikut di terminal:

* **Menjalankan / Merestart Bot:**
  Script ini otomatis mematikan proses bot lama, menyalakan ulang bot di background, serta mengirim notifikasi status ke grup Telegram:
  ```bash
  ./restart.sh
  ```
* **Melihat Log Aktivitas Bot:**
  Untuk memantau aktivitas atau melihat error secara real-time:
  ```bash
  tail -f bot.log
  ```
* **Cek Status Proses Bot:**
  Memeriksa apakah bot sedang berjalan beserta nomor PID-nya:
  ```bash
  pgrep -f rbwisuda.py
  ```

---

## 📋 Daftar Perintah Bot (Commands)

Kirim perintah berikut langsung ke bot di Telegram:

* `/start` : Membuka menu utama interaktif.
* `/report` : Menampilkan laporan keuangan harian terbaru lengkap dengan menu utama.
* `/se <nama> <nominal>` : Update saldo efektif (Contoh: `/se Seabank 800000`).
* `/sne <nama> <nominal>` : Update saldo non-efektif/alokasi (Contoh: `/sne "Gaji Akmal" 100000`).
* `/resetdate <tanggal>` : Memperbarui tanggal laporan (Contoh: `/resetdate 17 August 2026`).