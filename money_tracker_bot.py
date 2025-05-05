import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)
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
from datetime import datetime

# Logging
logging.basicConfig(level=logging.INFO)

# --- Google Sheets Setup ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("money-tracker-bot-458403-26377cc845ec.json", scope)
client = gspread.authorize(creds)

spreadsheet = client.open("Money Tracker Bot")
sheet = spreadsheet.sheet1  # atau gunakan: spreadsheet.worksheet("Sheet1")


# --- Command: /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


# --- Command: /menu ---
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Tambah Transaksi", callback_data='tambah')],
        [InlineKeyboardButton("📆 Summary Hari Ini", callback_data='summary_hari')],
        [InlineKeyboardButton("🗓️ Summary Bulan Ini", callback_data='summary_bulan')],
        [InlineKeyboardButton("📊 Per Kategori", callback_data='kategori')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Silakan pilih menu:", reply_markup=reply_markup)


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
        from collections import defaultdict
        bulan_ini = datetime.now().strftime("%Y-%m")

        kategori_total = defaultdict(int)
        for r in records:
            if r["Tanggal"].startswith(bulan_ini) and r["Tipe"].lower() == "pengeluaran":
                kategori = r["Kategori"].strip().title()  # <-- perbaikan di sini
                kategori_total[kategori] += int(r["Jumlah"])

        if not kategori_total:
            await query.edit_message_text("❌ Belum ada data pengeluaran bulan ini.")
            return

        result = "📊 *Pengeluaran per Kategori (Bulan Ini)*\n\n"
        for kategori, total in kategori_total.items():
            result += f"• *{kategori}*: Rp{total:,}\n".replace(",", ".")

        await query.edit_message_text(result, parse_mode="Markdown")


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


# --- Main ---
import os
TOKEN = os.getenv("BOT_TOKEN")

app = ApplicationBuilder().token(TOKEN).build()

# Handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("menu", menu))
app.add_handler(CommandHandler("summary_bulan", summary_bulan))
app.add_handler(CommandHandler("kategori", kategori))
app.add_handler(CallbackQueryHandler(handle_menu_selection))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Run
app.run_polling()
