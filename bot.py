# ФАЙЛ: bot.py (ТОЛЬКО Ton.fun токены)

import requests
import logging
import asyncio
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime

# Загружаем переменные окружения
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise Exception("Нет BOT_TOKEN! Проверь переменные окружения.")

# Настройка логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Глобальный кэш Ton.fun токенов
latest_listings = "Данные ещё загружаются..."
tonfun_tokens = {}

async def load_tonfun_tokens():
    global tonfun_tokens
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TelegramBot/1.0)"}
        response = requests.get("https://ton.fun/api/coins/list?page=1&limit=1000", timeout=10, headers=headers)
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}")
        data = response.json()
        coins = data.get("data", [])
        tonfun_tokens = {}
        for coin in coins:
            symbol = coin.get("symbol") or coin.get("name") or "UNKNOWN"
            address = coin.get("jetton_address")
            if address:
                tonfun_tokens[address] = symbol
    except Exception as e:
        logging.error(f"Ошибка загрузки токенов Ton.fun: {e}")
        tonfun_tokens = {}

async def fetch_tonfun():
    message = "🆕 *Новые токены Ton.fun:*\n"
    try:
        if not tonfun_tokens:
            await load_tonfun_tokens()

        if not tonfun_tokens:
            message += "\nНет новых токенов."
        else:
            shown = 0
            for address, symbol in list(tonfun_tokens.items())[:10]:
                link = f"https://ton.fun/token/{address}"
                shown += 1
                message += f"{shown}. {symbol} [Смотреть]({link})\n"

    except Exception as e:
        logging.error(f"Ошибка получения токенов Ton.fun: {e}")
        message += "\nОшибка получения токенов."

    return message

async def update_listings(context: ContextTypes.DEFAULT_TYPE):
    global latest_listings
    await load_tonfun_tokens()
    tonfun = await fetch_tonfun()
    latest_listings = tonfun + f"\n\n_Обновлено: {datetime.utcnow().strftime('%d.%m.%Y %H:%M UTC')}_"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я отслеживаю новые токены с Ton.fun\nКоманда: /newlistings")

async def newlistings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(latest_listings, parse_mode='Markdown')

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newlistings", newlistings))

    job_queue = app.job_queue
    job_queue.run_repeating(update_listings, interval=1800, first=5)

    app.run_polling()

if __name__ == "__main__":
    main()
