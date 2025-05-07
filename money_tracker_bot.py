import os
import json
import logging
from collections import defaultdict
from datetime import datetime
from telegram import ReplyKeyboardMarkup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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

def get_current_balance():
    try:
        records = sheet.get_all_records()
        balance = 0
        for r in records:
            try:
                jumlah = int(r["Jumlah"])
                if r["Tipe"].strip().lower() == "pemasukan":
                    balance += jumlah
                elif r["Tipe"].strip().lower() == "pengeluaran":
                    balance -= jumlah
            except:
                continue
        return balance
    except Exception as e:
        logger.error(f"Error calculating balance: {str(e)}", exc_info=True)
        return 0

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["➕ Tambah Transaksi"],
        ["📆 Summary Hari Ini", "🗓️ Summary Bulan Ini"],
        ["📊 Per Kategori"],
        ["/menu"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "Selamat datang di Money Tracker! 🧾\n\n"
        "Ketik transaksi seperti chat biasa.\n"
        "Contoh:\n"
        "`gajian April 8,5 juta masuk mandiri`\n"
        "`beli sepatu 300 ribu Qris Mandiri`",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["➕ Tambah Transaksi"],
        ["📆 Summary Hari Ini", "🗓️ Summary Bulan Ini"],
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

        result = "📊 *Pengeluaran per Kategori (Bulan Ini)*\n\n"
        for kategori, total in sorted(kategori_total.items(), key=lambda x: x[1], reverse=True):
            result += f"• *{kategori}*: Rp{total:,}\n".replace(",", ".")

        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in kategori: {str(e)}", exc_info=True)
        await update.message.reply_text("❌ Terjadi kesalahan saat mengambil data kategori.")

async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        saldo_terbaru = get_current_balance()
        await update.message.reply_text(
            f"💰 *Saldo saat ini*: Rp. {saldo_terbaru:,}".replace(",", "."),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in /saldo: {str(e)}", exc_info=True)
        await update.message.reply_text("❌ Gagal mengambil saldo.")

# --- Callback Handler ---
async def handle_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "tambah":
        await query.edit_message_text(
            "📥 Ketik transaksi seperti chat biasa.\nContoh:\n`gajian April 8,5 juta masuk mandiri`",
            parse_mode="Markdown"
        )
    elif data == "summary_hari":
        expenses = get_daily_expenses()
        total = sum(int(r["Jumlah"]) for r in expenses)
        await query.edit_message_text(f"📆 Pengeluaran hari ini: Rp{total:,}".replace(",", "."))
    elif data == "summary_bulan":
        expenses = get_monthly_expenses()
        total = sum(int(r["Jumlah"]) for r in expenses)
        await query.edit_message_text(f"🗓️ Pengeluaran bulan ini: Rp{total:,}".replace(",", "."))
    elif data == "kategori":
        kategori_total = get_monthly_expenses_by_category()

        if not kategori_total:
            await query.edit_message_text("❌ Belum ada data pengeluaran bulan ini.")
            return

        result = "📊 *Pengeluaran per Kategori (Bulan Ini)*\n\n"
        for kategori, total in sorted(kategori_total.items(), key=lambda x: x[1], reverse=True):
            result += f"• *{kategori}*: Rp{total:,}\n".replace(",", ".")

        await query.edit_message_text(result, parse_mode="Markdown")

# --- Message Handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.lower()
        tanggal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if "masuk" in text:
            tipe = "Pemasukan"
        else:
            tipe = "Pengeluaran"

        words = text.split()
        jumlah = next((w for w in words if any(x in w for x in ["ribu", "juta", ".", ","])), None)
        if not jumlah:
            raise ValueError("Jumlah tidak ditemukan.")

        deskripsi = words[0] + " " + words[1]
        asset = words[-1]

        # Konversi jumlah ke angka
        angka = jumlah.replace(".", "").replace(",", ".")
        angka = angka.replace("ribu", "000").replace("juta", "000000")
        angka = int(float(angka))

        # Simpan ke sheet
        sheet.append_row([tanggal, deskripsi.title(), asset.title(), tipe, angka])

        saldo = get_current_balance()
        await update.message.reply_text(
            f"Hallo,\nCatatanmu berhasil disimpan\n\n"
            f"{deskripsi.title()}\n"
            f"Tanggal {datetime.now().strftime('%-d %B %Y')}\n"
            f"Nominal : Rp. {angka:,}\n"
            f"Asset : {asset.title()}\n\n"
            f"Saldo terbaru: Rp. {saldo:,}".replace(",", "."),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ Gagal membaca format transaksi.\n"
            "Contoh: `beli sepatu 300 ribu Qris Mandiri`",
            parse_mode="Markdown"
        )

async def summary_bulan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) != 1:
            await update.message.reply_text("❌ Format salah. Gunakan: /summary_bulan 2025-04")
            return

        bulan_input = context.args[0]
        expenses = get_monthly_expenses(bulan_input)
        total = sum(int(r['Jumlah']) for r in expenses)
        await update.message.reply_text(
            f"📆 Total pengeluaran bulan *{bulan_input}*: Rp{total:,}".replace(",", "."),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in summary_bulan: {str(e)}", exc_info=True)
        await update.message.reply_text("❌ Gagal mengambil summary.")

# --- Main ---
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
    app.add_handler(CommandHandler("saldo", saldo))
    app.add_handler(CallbackQueryHandler(handle_menu_selection))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started")
    app.run_polling()

if __name__ == '__main__':
    main()
