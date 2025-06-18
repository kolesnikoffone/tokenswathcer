import logging
import os
import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, JobQueue
from datetime import datetime, timedelta

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

async def fetch_tokens():
    url = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    tokens = data.get("items", [])

                    lines = []
                    for token in tokens[:15]:  # Ограничим до 15 верхних
                        symbol = token.get("symbol", "?")
                        market_cap = float(token.get("marketCap", 0))

                        if market_cap >= 1_000_000:
                            mcap = f"<b>${market_cap / 1_000_000:.1f}M</b>"
                        elif market_cap >= 1_000:
                            mcap = f"<b>${market_cap / 1_000:.1f}K</b>"
                        else:
                            mcap = f"<b>${market_cap:.2f}</b>"

                        line = f"├ {symbol} • {mcap}"
                        lines.append(line)

                    timestamp = datetime.utcnow() + timedelta(hours=3)
                    formatted_time = timestamp.strftime("%d.%m.%Y %H:%M:%S")
                    return ["\n".join(lines)], formatted_time
    except Exception as e:
        logger.warning(f"Ошибка при получении токенов из Bloom: {e}")
    return [], ""

async def hots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_hots_result, pinned_hots_messages
    chat_id = update.effective_chat.id

    old_msg_id = pinned_hots_messages.get(chat_id)
    if old_msg_id:
        try:
            await context.bot.unpin_chat_message(chat_id=chat_id, message_id=old_msg_id)
            await context.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
        except:
            pass

    pages, timestamp = await fetch_tokens()
    if pages and pages[0]:
        latest_hots_result = {
            "page": pages[0],
            "timestamp": timestamp
        }
    else:
        pages = [latest_hots_result.get("page")]
        timestamp = latest_hots_result.get("timestamp")
        if not pages or not pages[0]:
            return

    message = f"{pages[0]}\n\nОбновлено: {timestamp} (UTC+3)"
    buttons = [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]
    markup = InlineKeyboardMarkup([buttons])
    sent = await update.message.reply_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)

    try:
        await context.bot.pin_chat_message(chat_id=sent.chat_id, message_id=sent.message_id)
        pinned_hots_messages[sent.chat_id] = sent.message_id
    except:
        pass

async def refresh_hots_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_hots_result
    query = update.callback_query
    await query.answer()
    pages, timestamp = await fetch_tokens()
    if pages and pages[0]:
        latest_hots_result = {
            "page": pages[0],
            "timestamp": timestamp
        }
    else:
        pages = [latest_hots_result.get("page")]
        timestamp = latest_hots_result.get("timestamp")
        if not pages or not pages[0]:
            return

    message = f"{pages[0]}\n\nОбновлено: {timestamp} (UTC+3)"
    buttons = [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]
    markup = InlineKeyboardMarkup([buttons])
    try:
        await query.edit_message_text(text=message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
    except:
        pass

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CallbackQueryHandler(refresh_hots_callback, pattern="^refresh_hots$"))
    app.job_queue.run_repeating(refresh_hots_callback, interval=120, first=10)
    print("Бот запущен...")
    app.run_polling()
