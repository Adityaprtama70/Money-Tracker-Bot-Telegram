import os
import json
import logging
from collections import defaultdict
from datetime import datetime
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
def get_monthly_expenses_by_category(month=None):
    """Helper function to get expenses by category"""
    records = sheet.get_all_records()
    month = month or datetime.now().strftime("%Y-%m")
    
    kategori_total = defaultdict(int)
    for r in records:
        if r["Tanggal"].startswith(month) and r["Tipe"].lower() == "pengeluaran":
            kategori_total[r["Kategori"].strip().title()] += int(r["Jumlah"])
    
    return kategori_total

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command"""
    keyboard = [
        [InlineKeyboardButton("➕ Tambah Transaksi", callback_data='tambah')],
        [InlineKeyboardButton("📆 Summary Hari Ini", callback_data='summary_hari')],
        [InlineKeyboardButton("🗓️ Summary Bulan Ini", callback_data='summary_bulan')],
        [InlineKeyboardButton("📊 Per Kategori", callback_data='kategori')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Selamat datang di Money Tracker!\n\n"
        "Gunakan format ini untuk mencatat pengeluaran/pemasukan:\n"
        "`Deskripsi, Kategori, Tipe, Jumlah`\n\n"
        "Contoh:\n"
        "`Makan siang, Makanan, Pengeluaran, 25000`",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /menu command"""
    keyboard = [
        [InlineKeyboardButton("➕ Tambah Transaksi", callback_data='tambah')],
        [InlineKeyboardButton("📆 Summary Hari Ini", callback_data='summary_hari')],
        [InlineKeyboardButton("🗓️ Summary Bulan Ini", callback_data='summary_bulan')],
        [InlineKeyboardButton("📊 Per Kategori", callback_data='kategori')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Silakan pilih menu:", reply_markup=reply_markup)

async def kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /kategori command"""
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


# --- Callback Button Handler ---
async def handle_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    records = sheet.get_all_records()

    if data == "tambah":
        await query.edit_message_text(
            "📥 Kirim transaksi dalam format:\n`Deskripsi, Kategori, Tipe, Jumlah`",
            parse_mode="Markdown"
        )
    elif data == "summary_hari":
        tanggal_hari_ini = datetime.now().strftime("%Y-%m-%d")
        hari_ini = [r for r in records if r["Tanggal"].startswith(tanggal_hari_ini) and r["Tipe"].lower() == "pengeluaran"]
        total = sum(int(r["Jumlah"]) for r in hari_ini)
        await query.edit_message_text(f"📆 Pengeluaran hari ini: Rp{total:,}".replace(",", "."))
    elif data == "summary_bulan":
        bulan_ini = datetime.now().strftime("%Y-%m")
        bulan_records = [r for r in records if r["Tanggal"].startswith(bulan_ini) and r["Tipe"].lower() == "pengeluaran"]
        total = sum(int(r["Jumlah"]) for r in bulan_records)
        await query.edit_message_text(f"🗓️ Pengeluaran bulan ini: Rp{total:,}".replace(",", "."))

    elif data == "kategori":
    kategori_total = get_monthly_expenses_by_category()
    # ... kode tampilan yang sama ...

# --- Message Handler: Transaksi ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        deskripsi, kategori, tipe, jumlah = [x.strip() for x in text.split(",", 3)]
        tanggal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([tanggal, deskripsi, kategori, tipe, jumlah])
        await update.message.reply_text("✅ Data berhasil disimpan!")
    except Exception as e:
        logging.error(str(e))
        await update.message.reply_text("❌ Format salah. Gunakan:\nDeskripsi, Kategori, Tipe, Jumlah")


# --- Command: /summary_bulan 2025-04 ---
async def summary_bulan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) != 1:
            await update.message.reply_text("❌ Format salah. Gunakan: /summary_bulan 2025-04")
            return

        bulan_input = context.args[0]
        records = sheet.get_all_records()
        bulan_ini = [
            r for r in records
            if r['Tipe'].lower() == 'pengeluaran' and r['Tanggal'].startswith(bulan_input)
        ]
        total = sum(int(r['Jumlah']) for r in bulan_ini)
        await update.message.reply_text(
            f"📆 Total pengeluaran bulan *{bulan_input}*: Rp{total:,}".replace(",", "."),
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(str(e))
        await update.message.reply_text("❌ Gagal mengambil summary.")

# [Tambahkan ini sebelum bagian Main]
async def kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /kategori"""
    try:
        records = sheet.get_all_records()
        from collections import defaultdict
        
        bulan_ini = datetime.now().strftime("%Y-%m")
        kategori_total = defaultdict(int)
        
        for r in records:
            if r["Tanggal"].startswith(bulan_ini) and r["Tipe"].lower() == "pengeluaran":
                kategori = r["Kategori"].strip().title()
                kategori_total[kategori] += int(r["Jumlah"])

        if not kategori_total:
            await update.message.reply_text("❌ Belum ada data pengeluaran bulan ini.")
            return

        result = "📊 *Pengeluaran per Kategori (Bulan Ini)*\n\n"
        for kategori, total in sorted(kategori_total.items(), key=lambda x: x[1], reverse=True):
            result += f"• *{kategori}*: Rp{total:,}\n".replace(",", ".")

        await update.message.reply_text(result, parse_mode="Markdown")
        
    except Exception as e:
        logging.error(f"Error in kategori: {str(e)}")
        await update.message.reply_text("❌ Gagal mengambil data kategori.")

def main():
    """Start the bot."""
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        logger.error("BOT_TOKEN environment variable not set!")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("kategori", kategori))
    app.add_handler(CommandHandler("summary_bulan", summary_bulan))
    app.add_handler(CallbackQueryHandler(handle_menu_selection))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started")
    app.run_polling()

if __name__ == '__main__':
    main()
