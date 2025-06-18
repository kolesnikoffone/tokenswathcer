import os
import logging
from datetime import datetime, timedelta
import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise EnvironmentError("Нужен TELEGRAM_BOT_TOKEN")

latest_result = {"page": "", "timestamp": ""}
pinned_messages = {}

async def fetch_hot_tokens():
    url = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                tokens = data.get("jettons", [])
                result = []
                for idx, token in enumerate(tokens[:10], 1):
                    name = token.get("name", "N/A")
                    ticker = token.get("ticker", "")
                    stats = token.get("stats", {})
                    cap = float(stats.get("marketCap", 0))
                    change = float(stats.get("price24hChange", 0))
                    emoji = "💎" if change > 100 else "🚀" if change > 50 else "📈" if change > 0 else "📉"
                    growth_str = f"{emoji} {change:+.2f}%"
                    cap_str = f"${cap/1e6:.1f}M" if cap > 1_000_000 else f"${cap/1e3:.1f}K"
                    line = f"{idx}. {growth_str} | {cap_str} | {name} ({ticker})"
                    result.append(line)

                page = "\n".join(result)
                timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
                return page, timestamp
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return "", ""

async def hots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_result, pinned_messages
    chat_id = update.effective_chat.id

    old_msg_id = pinned_messages.get(chat_id)
    if old_msg_id:
        try:
            await context.bot.unpin_chat_message(chat_id, old_msg_id)
            await context.bot.delete_message(chat_id, old_msg_id)
        except:
            pass

    page, timestamp = await fetch_hot_tokens()
    if not page:
        return

    latest_result = {"page": page, "timestamp": timestamp}
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]])
    sent = await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=markup)
    await context.bot.pin_chat_message(chat_id, sent.message_id)
    pinned_messages[chat_id] = sent.message_id

async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_result
    query = update.callback_query
    await query.answer()
    page, timestamp = await fetch_hot_tokens()
    if not page:
        return
    latest_result = {"page": page, "timestamp": timestamp}
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]])
    await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=markup)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern="refresh_hots"))
    app.run_polling()
