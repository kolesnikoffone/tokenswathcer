import logging
import os
import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, JobQueue
)
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

latest_hots_result = {"page": "", "timestamp": ""}
pinned_hots_messages = {}

async def fetch_blum_hots():
    url = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
    headers = {
        "accept": "application/json, text/plain, */*",
        "lang": "ru",
        "origin": "https://telegram.blum.codes",
        "x-requested-with": "org.telegram.messenger",
        "user-agent": "Mozilla/5.0 (Telegram)"
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            result = []
            for token in items[:10]:
                symbol = token.get("symbol", "N/A")
                line = f"├ {symbol}"
                result.append(line)
            timestamp = datetime.utcnow() + timedelta(hours=3)
            formatted_time = timestamp.strftime("%d.%m.%Y %H:%M:%S")
            return "\n".join(result), formatted_time
    except Exception as e:
        logger.warning(f"BLUM API fetch error: {e}")
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
            logger.warning(f"Не удалось удалить предыдущее сообщение: {e}")

    page, timestamp = await fetch_blum_hots()
    if page:
        latest_hots_result = {"page": page, "timestamp": timestamp}
    else:
        page = latest_hots_result.get("page")
        timestamp = latest_hots_result.get("timestamp")
        if not page:
            return

    text = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    buttons = [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]
    markup = InlineKeyboardMarkup([buttons])
    sent = await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)

    try:
        await context.bot.pin_chat_message(chat_id=sent.chat_id, message_id=sent.message_id)
        pinned_hots_messages[sent.chat_id] = sent.message_id
    except Exception as e:
        logger.warning(f"Не удалось закрепить сообщение: {e}")

async def refresh_hots_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_hots_result
    query = update.callback_query
    await query.answer()
    page, timestamp = await fetch_blum_hots()
    if page:
        latest_hots_result = {"page": page, "timestamp": timestamp}
    else:
        page = latest_hots_result.get("page")
        timestamp = latest_hots_result.get("timestamp")
        if not page:
            return

    text = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    buttons = [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]
    markup = InlineKeyboardMarkup([buttons])
    try:
        await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
    except Exception as e:
        logger.warning(f"Ошибка при обновлении сообщения: {e}")

async def auto_update_hots(context: ContextTypes.DEFAULT_TYPE):
    global latest_hots_result, pinned_hots_messages
    page, timestamp = await fetch_blum_hots()
    if not page:
        return
    latest_hots_result = {"page": page, "timestamp": timestamp}
    text = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    buttons = [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]
    markup = InlineKeyboardMarkup([buttons])
    for chat_id, message_id in pinned_hots_messages.items():
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=markup
            )
        except Exception as e:
            logger.warning(f"Ошибка автообновления в чате {chat_id}: {e}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CallbackQueryHandler(refresh_hots_callback, pattern="^refresh_hots$"))
    app.job_queue.run_repeating(auto_update_hots, interval=120, first=10)
    print("Бот запущен...")
    app.run_polling()
