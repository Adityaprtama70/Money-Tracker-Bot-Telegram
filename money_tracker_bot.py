import os
import json
import logging
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import re
from collections import defaultdict
from oauth2client.service_account import ServiceAccountCredentials

# --- Logging setup ---
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

# --- Fungsi Utama ---
def extract_amount(text):
    match = re.search(r'(\d+[\.,]?\d*)\s*(ribu|juta)?', text.lower())
    if match:
        amount = float(match.group(1).replace(',', '.'))
        if match.group(2) == 'ribu':
            amount *= 1_000
        elif match.group(2) == 'juta':
            amount *= 1_000_000
        return int(amount)
    return 0

def categorize(text):
    categories = {
        "Pemasukan": ["gaji", "bonus", "investasi", "tabungan"],
        "Pakaian": ["baju", "celana", "jaket", "sepatu"],
        "Minuman": ["kopi", "teh", "susu", "es", "minum"],
        "Makanan": ["nasi", "ayam", "mie", "makan", "soto", "bakso", "pizza", "burger"],
        "Tagihan": ["listrik", "pdam", "wifi", "pulsa", "token"],
        "Transportasi": ["gojek", "grab", "maxim", "tj", "mrt", "bensin", "angkot"]
    }
    for kategori, keywords in categories.items():
        for word in keywords:
            if word in text:
                return kategori
    return "Lainnya"

def update_balance(asset: str, amount: int, tipe: str):
    records = sheet.get_all_records()
    saldo = 0
    for row in records:
        if row['Asset'].lower() == asset.lower():
            if row['Tipe'].lower() == 'pemasukan':
                saldo += int(row['Jumlah'])
            elif row['Tipe'].lower() == 'pengeluaran':
                saldo -= int(row['Jumlah'])
    if tipe.lower() == 'pemasukan':
        saldo += amount
    elif tipe.lower() == 'pengeluaran':
        saldo -= amount
    return saldo

def parse_transaction(text):
    text = text.lower()
    tipe = 'pemasukan' if 'masuk' in text else 'pengeluaran'
    jumlah = extract_amount(text)
    asset_match = re.search(r"(bca|bri|mandiri|qris|ovo|gopay|dana|tunai)", text)
    asset = asset_match.group(1).capitalize() if asset_match else "Lainnya"

    words = text.split()
    deskripsi = []
    for w in words:
        if any(unit in w for unit in ["ribu", "juta"]):
            break
        deskripsi.append(w)
    deskripsi = " ".join(deskripsi)
    kategori = categorize(text)

    return tipe.capitalize(), deskripsi.title(), kategori.title(), jumlah, asset

# --- Handler Telegram ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ['+ Tambah Transaksi'],
        ['📅 Summary Hari Ini', '🗓 Summary Bulan Ini'],
        ['📊 Per Kategori'],
        ['/menu']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Selamat datang di Money Tracker!\n\nKetik transaksi seperti chat biasa.\nContoh:\n\ngajian Mei 7,5 juta masuk BCA\nbeli kopi tuku 23 ribu QRIS",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text.lower().startswith('+ tambah transaksi'):
        await update.message.reply_text("Silakan ketik transaksi Anda.")
        return

    if 'summary hari' in text.lower():
        await summary_hari(update)
        return
    elif 'summary bulan' in text.lower():
        await summary_bulan(update)
        return
    elif 'per kategori' in text.lower():
        await summary_kategori(update)
        return

    try:
        tipe, deskripsi, kategori, jumlah, asset = parse_transaction(text)

        if jumlah == 0:
            await update.message.reply_text("⚠️ Format jumlah tidak dikenali. Contoh: 300 ribu atau 8,5 juta")
            return

        tanggal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([tanggal, deskripsi, kategori, tipe, jumlah, asset])
        saldo = update_balance(asset, jumlah, tipe)

        await update.message.reply_text(
            f"✅ *Catatanmu berhasil disimpan!*\n\n"
            f"*Deskripsi* : {deskripsi}\n"
            f"*Tanggal*   : {datetime.now().strftime('%-d %B %Y')}\n"
            f"*Nominal*   : Rp. {jumlah:,}\n"
            f"*Kategori*  : {kategori}\n"
            f"*Asset*     : {asset}\n\n"
            f"*Saldo terbaru* : Rp. {saldo:,}".replace(",", "."),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error saat parsing transaksi: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ Gagal memproses transaksi.\nPastikan format seperti:\n\n"
            "`Gaji April 8,5 juta masuk BCA`\n`Beli kopi 300 ribu Qris`",
            parse_mode="Markdown"
        )

async def summary_hari(update: Update):
    today = datetime.now().strftime("%Y-%m-%d")
    records = sheet.get_all_records()
    pemasukan = sum(r['Jumlah'] for r in records if r['Tipe'] == 'Pemasukan' and r['Tanggal'].startswith(today))
    pengeluaran = sum(r['Jumlah'] for r in records if r['Tipe'] == 'Pengeluaran' and r['Tanggal'].startswith(today))
    await update.message.reply_text(
        f"📅 *Summary Hari Ini*\nPemasukan: Rp. {pemasukan:,}\nPengeluaran: Rp. {pengeluaran:,}",
        parse_mode='Markdown'
    )

async def summary_bulan(update: Update):
    now = datetime.now()
    month_prefix = now.strftime("%Y-%m")
    records = sheet.get_all_records()
    pemasukan = sum(r['Jumlah'] for r in records if r['Tipe'] == 'Pemasukan' and r['Tanggal'].startswith(month_prefix))
    pengeluaran = sum(r['Jumlah'] for r in records if r['Tipe'] == 'Pengeluaran' and r['Tanggal'].startswith(month_prefix))
    await update.message.reply_text(
        f"🗓 *Summary Bulan Ini*\nPemasukan: Rp. {pemasukan:,}\nPengeluaran: Rp. {pengeluaran:,}",
        parse_mode='Markdown'
    )

async def summary_kategori(update: Update):
    now = datetime.now()
    month_prefix = now.strftime("%Y-%m")
    records = sheet.get_all_records()
    kategori_total = defaultdict(int)
    for r in records:
        if r['Tanggal'].startswith(month_prefix):
            if r['Tipe'] == 'Pemasukan':
                kategori_total[r['Kategori']] += r['Jumlah']
            else:
                kategori_total[r['Kategori']] -= r['Jumlah']
    msg = '*📊 Summary Per Kategori Bulan Ini:*\n'
    for k, v in kategori_total.items():
        msg += f"{k}: Rp. {v:,}\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

# --- Main ---
if __name__ == '__main__':
    TOKEN = os.getenv("BOT_TOKEN")
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()
