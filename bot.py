import os
import asyncio
import logging
from telegram import Bot
from telegram.ext import Application, CommandHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise EnvironmentError("BOT_TOKEN or TELEGRAM_CHAT_ID not set in environment.")

API_URL = "https://prod-api.bigpump.app/api/v1/coins?sortType=new&limit=20"

async def fetch_new_listings():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(API_URL, headers={"accept": "*/*", "origin": "https://bigpump.app", "referer": "https://bigpump.app/"})
            response.raise_for_status()
            return response.json().get("data", [])
        except Exception as e:
            logger.error(f"Ошибка запроса к BigPump API: {e}")
            return []

async def update_listings():
    listings = await fetch_new_listings()
    if not listings:
        message = "Нет новых листингов с BigPump."
    else:
        message = "🆕 *Новые токены BigPump:*\n"
        for i, token in enumerate(listings[:10], 1):
            name = token.get("name", "Без названия")
            symbol = token.get("symbol", "-")
            address = token.get("address")
            tv_url = f"https://tonviewer.com/{address}"
            message += f"{i}. {name} ({symbol}) — [TonViewer]({tv_url})\n"

    bot = Bot(BOT_TOKEN)
    await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")

async def main():
    application = Application.builder().token(BOT_TOKEN).build()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(update_listings, "interval", minutes=30)
    scheduler.start()

    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await application.idle()

if __name__ == "__main__":
    asyncio.run(main())
