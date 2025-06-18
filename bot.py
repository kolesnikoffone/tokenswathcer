import os
import logging
import aiohttp
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, JobQueue

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BLUM_BEARER_TOKEN = os.getenv("BLUM_BEARER_TOKEN")

if not BOT_TOKEN or not BLUM_BEARER_TOKEN:
    raise ValueError("Переменные окружения TELEGRAM_BOT_TOKEN и BLUM_BEARER_TOKEN обязательны")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pinned_hots_messages = {}
latest_hots_result = {"page": "", "timestamp": ""}

async def fetch_blum_hots():
    url = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=blum"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {BLUM_BEARER_TOKEN}",
        "lang": "ru",
        "origin": "https://telegram.blum.codes",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    jettons = data.get("jettons", [])
                    jettons = sorted(jettons, key=lambda x: float(x.get("stats", {}).get("volume24h", 0)), reverse=True)[:10]

                    result_lines = []
                    for i, jetton in enumerate(jettons, 1):
                        ticker = jetton.get("ticker", "N/A")
                        market_cap = float(jetton.get("stats", {}).get("marketCap", 0))
                        if market_cap >= 1_000_000:
                            cap_str = f"<b>${market_cap / 1_000_000:.1f}M</b>"
                        elif market_cap >= 1_000:
                            cap_str = f"<b>${market_cap / 1_000:.1f}K</b>"
                        else:
                            cap_str = f"<b>${market_cap:.2f}</b>"
                        result_lines.append(f"{i}. {cap_str} | {ticker}")

                    timestamp = datetime.utcnow() + timedelta(hours=3)
                    formatted_time = timestamp.strftime("%d.%m.%Y %H:%M:%S")
                    return "\n".join(result_lines), formatted_time
                else:
                    logger.warning(f"Blum API error: {response.status}")
    except Exception as e:
        logger.error(f"Ошибка при получении данных Blum: {e}")
    return "", ""

async def hots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_hots_result, pinned_hots_messages
    chat_id = update.effective_chat.id

    old_msg_id = pinned_hots_messages.get(chat_id)
    if old_msg_id:
        try:
            await context.bot.unpin_chat_message(chat_id, old_msg_id)
            await context.bot.delete_message(chat_id, old_msg_id)
        except Exception:
            pass

    text, timestamp = await fetch_blum_hots()
    if not text:
        return
    latest_hots_result = {"page": text, "timestamp": timestamp}
    message = f"{text}\n\nОбновлено: {timestamp} (UTC+3)"
    buttons = [InlineKeyboardButton("\ud83d\udd04 Обновить", callback_data="refresh_hots")]
    markup = InlineKeyboardMarkup([buttons])
    sent = await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=markup)

    try:
        await context.bot.pin_chat_message(sent.chat_id, sent.message_id)
        pinned_hots_messages[sent.chat_id] = sent.message_id
    except Exception:
        pass

async def refresh_hots_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text, timestamp = await fetch_blum_hots()
    if not text:
        return
    latest_hots_result.update({"page": text, "timestamp": timestamp})
    message = f"{text}\n\nОбновлено: {timestamp} (UTC+3)"
    buttons = [InlineKeyboardButton("\ud83d\udd04 Обновить", callback_data="refresh_hots")]
    markup = InlineKeyboardMarkup([buttons])
    try:
        await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=markup)
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение HOTS: {e}")

async def auto_update_hots(context: ContextTypes.DEFAULT_TYPE):
    global latest_hots_result, pinned_hots_messages
    text, timestamp = await fetch_blum_hots()
    if not text:
        return
    latest_hots_result.update({"page": text, "timestamp": timestamp})
    message = f"{text}\n\nОбновлено: {timestamp} (UTC+3)"
    buttons = [InlineKeyboardButton("\ud83d\udd04 Обновить", callback_data="refresh_hots")]
    markup = InlineKeyboardMarkup([buttons])
    for chat_id, msg_id in pinned_hots_messages.items():
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=message, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception as e:
            logger.warning(f"Ошибка автообновления: {e}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CallbackQueryHandler(refresh_hots_callback, pattern="^refresh_hots$"))
    app.job_queue.run_repeating(auto_update_hots, interval=60, first=10)
    app.run_polling()
