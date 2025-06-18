import logging
import os
from datetime import datetime, timedelta
import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    JobQueue,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

latest_hots_result = {"page": "", "timestamp": ""}
pinned_hots_messages = {}


async def fetch_hots():
    url = 'https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all'
    headers = {
        'accept': 'application/json, text/plain, */*',
        'lang': 'ru',
        'origin': 'https://telegram.blum.codes',
        'user-agent': 'Mozilla/5.0'
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    tokens = data.get("data", [])
                    result = []
                    for token in tokens:
                        symbol = token.get("symbol", "N/A")
                        cap = float(token.get("marketCap", 0))

                        if cap >= 1_000_000:
                            mcap = f"<b>${cap / 1_000_000:.1f}M</b>"
                        elif cap >= 1_000:
                            mcap = f"<b>${cap / 1_000:.1f}K</b>"
                        else:
                            mcap = f"<b>${cap:.2f}</b>"

                        line = f"├ {symbol} • {mcap}"
                        result.append(line)

                    timestamp = datetime.utcnow() + timedelta(hours=3)
                    formatted_time = timestamp.strftime("%d.%m.%Y %H:%M:%S")
                    return "\n".join(result), formatted_time
    except Exception as e:
        logger.exception("Ошибка при обращении к Blum API")
    return "", ""


async def hots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_hots_result, pinned_hots_messages
    chat_id = update.effective_chat.id

    old_msg_id = pinned_hots_messages.get(chat_id)
    if old_msg_id:
        try:
            await context.bot.unpin_chat_message(chat_id=chat_id, message_id=old_msg_id)
            await context.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить старое сообщение HOTS: {e}")

    page, timestamp = await fetch_hots()
    if page:
        latest_hots_result = {
            "page": page,
            "timestamp": timestamp
        }
    else:
        page = latest_hots_result.get("page")
        timestamp = latest_hots_result.get("timestamp")
        if not page:
            return

    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    buttons = [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]
    markup = InlineKeyboardMarkup([buttons])
    sent = await update.message.reply_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)

    try:
        await context.bot.pin_chat_message(chat_id=sent.chat_id, message_id=sent.message_id)
        pinned_hots_messages[sent.chat_id] = sent.message_id
    except Exception as e:
        logger.warning(f"Не удалось закрепить сообщение HOTS: {e}")


async def refresh_hots_callback(update: Update = None, context: ContextTypes.DEFAULT_TYPE = None):
    global latest_hots_result
    page, timestamp = await fetch_hots()
    if page:
        latest_hots_result = {
            "page": page,
            "timestamp": timestamp
        }
    else:
        page = latest_hots_result.get("page")
        timestamp = latest_hots_result.get("timestamp")
        if not page:
            return

    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    buttons = [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]
    markup = InlineKeyboardMarkup([buttons])

    if update:
        query = update.callback_query
        await query.answer()
        try:
            await query.edit_message_text(text=message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
        except Exception as e:
            logger.warning(f"Не удалось обновить HOTS сообщение: {e}")
    else:
        for chat_id, message_id in pinned_hots_messages.items():
            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
            except Exception as e:
                logger.warning(f"Ошибка автообновления в чате {chat_id}: {e}")


if __name__ == '__main__':
    from telegram.ext import Application
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CallbackQueryHandler(refresh_hots_callback, pattern="^refresh_hots$"))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(refresh_hots_callback, 'interval', minutes=2, args=[None, app.bot])
    scheduler.start()

    print("Бот запущен...")
    app.run_polling()
