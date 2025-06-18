import logging
import os
from datetime import datetime, timedelta

import aiohttp
from pytoniq_core import Address
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, JobQueue
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REFERRAL_PREFIX = "213213722_"
pinned_hots_messages = {}
pinned_bighots_messages = {}
latest_results = {
    "hots": {"page": "", "timestamp": ""},
    "bighots": {"page": "", "timestamp": ""}
}

def address_to_base64url(address: str) -> str:
    return Address(address).to_str(True, True, False, True)

async def fetch_tokens_blum(min_cap, max_cap, limit=100):
    url = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                tokens = data.get("jettons", [])
                result = []
                for token in tokens:
                    cap = float(token.get("stats", {}).get("marketCap", 0))
                    if not (min_cap <= cap <= max_cap):
                        continue

                    name = token.get("name", "N/A")
                    ticker = token.get("ticker", "")
                    address = token.get("address", "")
                    change = float(token.get("stats", {}).get("price24hChange", 0))

                    if cap >= 1e6:
                        cap_str = f"${cap/1e6:.1f}M"
                    else:
                        cap_str = f"${cap/1e3:.1f}K"

                    emoji = "💎" if change >= 100 else "🤑" if change >= 50 else "🚀" if change >= 25 else "💸" if change >= 10 else "📈" if change >= 5 else "🥹" if change > 0 else "🫥" if change > -1 else "📉" if change > -5 else "💔" if change > -10 else "😭" if change > -25 else "🤡"
                    growth = f"{emoji} {change:+.2f}%"

                    try:
                        link = f"https://t.me/dtrade?start={REFERRAL_PREFIX}{address_to_base64url(address)}"
                        name_ticker = f'<a href="{link}">{ticker}</a>'
                    except:
                        name_ticker = ticker

                    result.append(f"├{growth} • {name_ticker} • <b>{cap_str}</b>")

                    if len(result) >= 10:
                        break

                timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
                return "\n".join(result), timestamp
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return "", ""

async def send_or_refresh(command: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_results, pinned_hots_messages, pinned_bighots_messages

    chat_id = update.effective_chat.id
    msg_dict = pinned_hots_messages if command == "hots" else pinned_bighots_messages
    min_cap, max_cap = (4000, 250_000) if command == "hots" else (250_000, 10_000_000)

    old_msg_id = msg_dict.get(chat_id)
    if old_msg_id:
        try:
            await context.bot.unpin_chat_message(chat_id, old_msg_id)
            await context.bot.delete_message(chat_id, old_msg_id)
        except:
            pass

    page, timestamp = await fetch_tokens_blum(min_cap, max_cap)
    if not page:
        return

    latest_results[command] = {"page": page, "timestamp": timestamp}
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{command}")]])
    sent = await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=markup)

    await context.bot.pin_chat_message(chat_id, sent.message_id)
    msg_dict[chat_id] = sent.message_id

async def auto_update(context: ContextTypes.DEFAULT_TYPE, command: str, msg_dict: dict):
    min_cap, max_cap = (4000, 250_000) if command == "hots" else (250_000, 10_000_000)
    page, timestamp = await fetch_tokens_blum(min_cap, max_cap)
    if not page:
        return
    latest_results[command] = {"page": page, "timestamp": timestamp}
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{command}")]])

    for chat_id, msg_id in msg_dict.items():
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=message, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception as e:
            logger.warning(f"[{command}] Ошибка обновления в чате {chat_id}: {e}")

async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if "hots" in query.data:
        command = "hots" if query.data == "refresh_hots" else "bighots"
        min_cap, max_cap = (4000, 250_000) if command == "hots" else (250_000, 10_000_000)
        page, timestamp = await fetch_tokens_blum(min_cap, max_cap)
        if page:
            latest_results[command] = {"page": page, "timestamp": timestamp}
        else:
            page = latest_results[command]["page"]
            timestamp = latest_results[command]["timestamp"]
        message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{command}")]])
        try:
            await query.edit_message_text(text=message, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception as e:
            logger.warning(f"Ошибка обновления кнопкой: {e}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", lambda u, c: send_or_refresh("hots", u, c)))
    app.add_handler(CommandHandler("bighots", lambda u, c: send_or_refresh("bighots", u, c)))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern="^refresh_hots$"))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern="^refresh_bighots$"))
    app.job_queue.run_repeating(lambda c: auto_update(c, "hots", pinned_hots_messages), interval=10, first=5)
    app.job_queue.run_repeating(lambda c: auto_update(c, "bighots", pinned_bighots_messages), interval=10, first=6)
    print("Бот запущен.")
    app.run_polling()
