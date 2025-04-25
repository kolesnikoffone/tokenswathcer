# ФАЙЛ: bot.py (с красивыми названиями токенов)

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

# Глобальная переменная для кэширования листингов
latest_listings = "Данные еще загружаются..."

# Кэш для токенов STON.fi
stonfi_assets = {}

async def load_stonfi_assets():
    global stonfi_assets
    try:
        response = requests.get("https://api.ston.fi/v1/assets", timeout=10)
        assets = response.json().get("assets", [])
        stonfi_assets = {asset["address"]: asset.get("symbol", "???") for asset in assets}
    except Exception as e:
        logging.error(f"Ошибка загрузки токенов STON.fi: {e}")
        stonfi_assets = {}

async def fetch_dedust():
    url = "https://api.dedust.io/v2/pools"
    try:
        response = requests.get(url, timeout=10)
        pools = response.json()

        for pool in pools:
            created_ts = pool.get("created_at")
            if created_ts:
                pool["created_dt"] = datetime.utcfromtimestamp(created_ts)
            else:
                pool["created_dt"] = datetime.utcnow()

        sorted_pools = sorted(pools, key=lambda x: x["created_dt"], reverse=True)
        latest = sorted_pools[:10]

        message = "🆕 Новые листинги DeDust:\n"
        for idx, pool in enumerate(latest, 1):
            token0 = pool.get("token0", {}).get("metadata", {}).get("symbol", "???")
            token1 = pool.get("token1", {}).get("metadata", {}).get("symbol", "???")
            date_str = pool["created_dt"].strftime("%d.%m.%Y")
            message += f"{idx}. {token0}/{token1} — {date_str}\n"
        return message

    except Exception as e:
        logging.error(f"Ошибка получения DeDust: {e}")
        return "Ошибка получения листингов DeDust."

async def fetch_stonfi():
    url = "https://api.ston.fi/v1/pools"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        pools = data.get("pool_list", [])

        latest = pools[-10:][::-1]

        message = "\n🆕 Новые листинги STON.fi:\n"
        for idx, pool in enumerate(latest, 1):
            token0_address = pool.get("token0_address", "")
            token1_address = pool.get("token1_address", "")
            token0 = stonfi_assets.get(token0_address, token0_address[-6:])
            token1 = stonfi_assets.get(token1_address, token1_address[-6:])
            message += f"{idx}. {token0}/{token1}\n"
        return message

    except Exception as e:
        logging.error(f"Ошибка получения STON.fi: {e}")
        return "Ошибка получения листингов STON.fi."

async def update_listings(context: ContextTypes.DEFAULT_TYPE):
    global latest_listings
    await load_stonfi_assets()
    dedust = await fetch_dedust()
    stonfi = await fetch_stonfi()
    latest_listings = dedust + "\n" + stonfi + f"\n\nОбновлено: {datetime.utcnow().strftime('%d.%m.%Y %H:%M UTC')}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я отслеживаю новые токены на DeDust и STON.fi.\nКоманда: /newlistings")

async def newlistings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(latest_listings)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newlistings", newlistings))

    job_queue = app.job_queue
    job_queue.run_repeating(update_listings, interval=1800, first=5)

    app.run_polling()

if __name__ == "__main__":
    main()
