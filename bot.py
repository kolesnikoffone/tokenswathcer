# ФАЙЛ: bot.py (BigPump + STON.fi токены)

import os
import logging
import aiohttp
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime

# Загрузка переменных окружения
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise Exception("Нет BOT_TOKEN! Проверь переменные окружения.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальный кэш
announced_tokens = set()
latest_listings = "Данные ещё загружаются..."

async def fetch_bigpump_tokens():
    url = "https://bigpump.app/api/v1/coins"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TelegramBot/1.0)"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"Ошибка BigPump API: {resp.status}")
            data = await resp.json()
            return data.get("coins", [])

async def fetch_stonfi_pools():
    url = "https://api.ston.fi/v1/stats/pool"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Ошибка STON.fi API: {resp.status}")
            data = await resp.json()
            return data.get("stats", [])

async def update_listings(context: ContextTypes.DEFAULT_TYPE = None):
    global latest_listings, announced_tokens
    try:
        bigpump_tokens = await fetch_bigpump_tokens()
        stonfi_pools = await fetch_stonfi_pools()

        stonfi_addresses = set()
        for pool in stonfi_pools:
            base = pool.get("base_address")
            quote = pool.get("quote_address")
            if base:
                stonfi_addresses.add(base)
            if quote:
                stonfi_addresses.add(quote)

        message = "🆕 *Новые токены BigPump с ликвидностью:*
"
        found = 0

        for token in bigpump_tokens:
            address = token.get("address")
            symbol = token.get("symbol") or "UNKNOWN"
            price = token.get("price", "-")
            if not address or address in announced_tokens:
                continue
            if address in stonfi_addresses:
                tonviewer_link = f"https://tonviewer.com/{address}"
                message += f"{found+1}. **{symbol}** — {price} — [Tonviewer]({tonviewer_link})\n"
                announced_tokens.add(address)
                found += 1
                if found >= 10:
                    break

        if found == 0:
            message += "\nНет новых токенов с ликвидностью."

        latest_listings = message + f"\n\n_Обновлено: {datetime.utcnow().strftime('%d.%m.%Y %H:%M UTC')}"

        if context:
            await context.bot.send_message(chat_id=context.job.data, text=latest_listings, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка обновления листингов: {e}")

async def newtokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(latest_listings, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("👋 *Добро пожаловать!*

Я отслеживаю новые токены BigPump с ликвидностью на STON.fi!

*Команды:*
/newtokens — Новые токены с ликвидностью", parse_mode='Markdown')
    context.job_queue.run_repeating(update_listings, interval=1800, first=5, data=chat_id)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newtokens", newtokens))

    job_queue = app.job_queue
    job_queue.run_repeating(update_listings, interval=1800, first=5)

    app.run_polling()

if __name__ == "__main__":
    main()
