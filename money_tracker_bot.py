import os
import json
import logging
from collections import defaultdict
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Logging setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(_name_)

# --- Google Sheets Setup ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
service_account_info = json.loads(os.environ['GOOGLE_CREDENTIALS_JSON'])
creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
client = gspread.authorize(creds)
spreadsheet = client.open("Money Tracker Bot")
sheet = spreadsheet.sheet1

# --- Helper Functions ---
def get_daily_expenses(date=None):
    date = date or datetime.now().strftime("%Y-%m-%d")
    records = sheet.get_all_records()
    return [r for r in records if r["Tanggal"].startswith(date) and r["Tipe"].lower() == "pengeluaran"]

def get_monthly_expenses(month=None):
    month = month or datetime.now().strftime("%Y-%m")
    records = sheet.get_all_records()
    return [r for r in records if r["Tanggal"].startswith(month) and r["Tipe"].lower() == "pengeluaran"]

def get_monthly_expenses_by_category(month=None):
    expenses = get_monthly_expenses(month)
    kategori_total = defaultdict(int)
    for r in expenses:
        kategori_total[r["Kategori"].strip().title()] += int(r["Jumlah"])
    return kategori_total

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["➕ Tambah Transaksi"],
        ["📆 Summary Hari Ini", "🗓 Summary Bulan Ini"],
        ["📊 Per Kategori"],
        ["/menu"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "Selamat datang di Money Tracker! 🧾\n\n"
        "Ketik transaksi dalam format:\n"
        "Deskripsi, Kategori, Tipe, Jumlah\n\n"
        "Contoh:\n"
        "Makan siang, Makanan, Pengeluaran, 25000",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["➕ Tambah Transaksi"],
        ["📆 Summary Hari Ini", "🗓 Summary Bulan Ini"],
        ["📊 Per Kategori"],
        ["/start"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "📋 Menu Utama:\nSilakan pilih aksi dari tombol di bawah ini.",
        reply_markup=reply_markup
    )

async def kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        kategori_total = get_monthly_expenses_by_category()
        if not kategori_total:
            await update.message.reply_text("❌ Belum ada data pengeluaran bulan ini.")
            return

        result = "📊 Pengeluaran per Kategori (Bulan Ini)\n\n"
        for kategori, total in sorted(kategori_total.items(), key=lambda x: x[1], reverse=True):
            result += f"• {kategori}: Rp{total:,}\n".replace(",", ".")
        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in kategori: {str(e)}", exc_info=True)
        await update.message.reply_text("❌ Terjadi kesalahan saat mengambil data kategori.")

# --- Message Handler: Transaksi & Tombol ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()

    if text == "➕ tambah transaksi":
        await update.message.reply_text(
            "📥 Silakan kirim transaksi dalam format:\n"
            "Deskripsi, Kategori, Tipe, Jumlah",
            parse_mode="Markdown"
        )
        return

    elif text == "📆 summary hari ini":
        expenses = get_daily_expenses()
        total = sum(int(r["Jumlah"]) for r in expenses)
        await update.message.reply_text(f"📆 Pengeluaran hari ini: Rp{total:,}".replace(",", "."))
        return

    elif text == "🗓 summary bulan ini":
        expenses = get_monthly_expenses()
        total = sum(int(r["Jumlah"]) for r in expenses)
        await update.message.reply_text(f"🗓 Pengeluaran bulan ini: Rp{total:,}".replace(",", "."))
        return

    elif text == "📊 per kategori":
        kategori_total = get_monthly_expenses_by_category()
        if not kategori_total:
            await update.message.reply_text("❌ Belum ada data pengeluaran bulan ini.")
        else:
            result = "📊 Pengeluaran per Kategori (Bulan Ini)\n\n"
            for kategori, total in sorted(kategori_total.items(), key=lambda x: x[1], reverse=True):
                result += f"• {kategori}: Rp{total:,}\n".replace(",", ".")
            await update.message.reply_text(result, parse_mode="Markdown")
        return

    # Jika bukan tombol, asumsikan sebagai transaksi
    try:
        deskripsi, kategori, tipe, jumlah = [x.strip() for x in text.split(",", 3)]
        tanggal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([tanggal, deskripsi, kategori, tipe, jumlah])
        await update.message.reply_text("✅ Data berhasil disimpan!")
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}", exc_info=True)
        await update.message.reply_text("❌ Format salah. Gunakan:\nDeskripsi, Kategori, Tipe, Jumlah")

# --- Command: /summary_bulan [YYYY-MM] ---
async def summary_bulan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) != 1:
            await update.message.reply_text("❌ Format salah. Gunakan: /summary_bulan 2025-04")
            return

        bulan_input = context.args[0]
        expenses = get_monthly_expenses(bulan_input)
        total = sum(int(r['Jumlah']) for r in expenses)
        await update.message.reply_text(
            f"📆 Total pengeluaran bulan {bulan_input}: Rp{total:,}".replace(",", "."),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in summary_bulan: {str(e)}", exc_info=True)
        await update.message.reply_text("❌ Gagal mengambil summary.")

# --- Main App ---
def main():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        logger.error("BOT_TOKEN environment variable not set!")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("kategori", kategori))
    app.add_handler(CommandHandler("summary_bulan", summary_bulan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started")
    app.run_polling()

if _name_ == '_main_':
    main()
