import logging
import aiohttp
import os
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

latest_dyor_result = {"hots": "", "listings": "", "timestamp": ""}

async def fetch_dyor_data(sort_type: str, limit: int = 10):
    url = "https://api.dyor.io/v1/jettons"
    headers = {
        "accept": "application/json",
        "content-type": "application/json"
    }
    payload = {
        "chain": "mainnet",
        "sortBy": "priceChange.day.changePercent" if sort_type == "hot" else "createdAt",
        "sortDirection": "desc",
        "limit": limit,
        "excludeScam": True
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                logger.info(f"DYOR API responded with status {response.status}")
                if response.status == 200:
                    data = await response.json()
                    tokens = data.get("items", [])
                    results = []
                    for idx, token in enumerate(tokens, 1):
                        name = token.get("name", "N/A")
                        symbol = token.get("symbol", "N/A")
                        address = token.get("address", "")
                        price_change = token.get("priceChange", {}).get("day", {}).get("changePercent", 0)
                        mcap = token.get("marketCap", {}).get("usd", 0)

                        growth_str = f"{price_change:+.2f}%"
                        emoji = "🚀" if price_change > 25 else "📈" if price_change > 5 else "🫥" if price_change > 0 else "📉"

                        if mcap >= 1_000_000:
                            mcap_str = f"<b>${mcap/1_000_000:.1f}M</b>"
                        elif mcap >= 1_000:
                            mcap_str = f"<b>${mcap/1_000:.1f}K</b>"
                        else:
                            mcap_str = f"<b>${mcap:.2f}</b>"

                        link = f"https://dyor.io/token/{address}"
                        line = f"{idx}. {emoji} {growth_str} • {mcap_str} • <a href='{link}'>{name} ({symbol})</a>"
                        results.append(line)
                    timestamp = datetime.utcnow() + timedelta(hours=3)
                    return "\n".join(results), timestamp.strftime("%d.%m.%Y %H:%M:%S")
                else:
                    return "", ""
    except Exception as e:
        logger.warning(f"Ошибка запроса к DYOR API: {e}")
        return "", ""

async def hots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_dyor_result
    text, timestamp = await fetch_dyor_data("hot")
    if not text:
        text = latest_dyor_result.get("hots")
        timestamp = latest_dyor_result.get("timestamp")
    else:
        latest_dyor_result["hots"] = text
        latest_dyor_result["timestamp"] = timestamp

    message = f"<b>🔥 Топ за 24ч:</b>\n{text}\n\nОбновлено: {timestamp} (UTC+3)"
    await update.message.reply_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def listings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_dyor_result
    text, timestamp = await fetch_dyor_data("listings")
    if not text:
        text = latest_dyor_result.get("listings")
        timestamp = latest_dyor_result.get("timestamp")
    else:
        latest_dyor_result["listings"] = text
        latest_dyor_result["timestamp"] = timestamp

    message = f"<b>🆕 Новые листинги:</b>\n{text}\n\nОбновлено: {timestamp} (UTC+3)"
    await update.message.reply_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CommandHandler("listings", listings_command))
    print("DYOR бот запущен...")
    app.run_polling()
