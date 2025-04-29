import os
import asyncio
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise EnvironmentError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in environment.")

API_URL = "https://prod-api.bigpump.app/api/v1/coins?sortType=new&limit=20"

async def fetch_latest_coins():
    headers = {
        'accept': '*/*',
        'origin': 'https://bigpump.app',
        'referer': 'https://bigpump.app/',
        'user-agent': 'Mozilla/5.0'
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(API_URL, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching data: {e}")
            return []

def format_coin_message(coins):
    if not coins:
        return "Нет новых токенов с BigPump."
    
    message = "🆕 *Новые токены BigPump:*\n"
    for coin in coins[:20]:
        name = coin.get("name", "Без названия")
        symbol = coin.get("symbol", "")
        tv_link = f"https://tonviewer.com/{coin.get('address', '')}"
        message += f"• {name} ({symbol}) — [Смотреть]({tv_link})\n"
    return message

async def send_updates(context: ContextTypes.DEFAULT_TYPE):
    coins = await fetch_latest_coins()
    message = format_coin_message(coins)
    await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")

async def top_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coins = await fetch_latest_coins()
    message = format_coin_message(coins)
    await update.message.reply_text(message, parse_mode="Markdown")

async def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("top", top_handler))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_updates, "interval", minutes=30, args=[application.bot])
    scheduler.start()

    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await application.updater.idle()

if __name__ == "__main__":
    asyncio.run(main())
