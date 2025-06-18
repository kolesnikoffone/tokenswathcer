import logging
import os
import aiohttp
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    JobQueue,
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REFERRAL_PREFIX = "213213722_"

# Глобальные хранилища для обновлений
latest_hots_result = {"page": "", "timestamp": ""}
latest_bighots_result = {"page": "", "timestamp": ""}

pinned_hots_messages = {}
pinned_bighots_messages = {}

async def fetch_filtered_hots(min_cap_usd: float, max_cap_usd: float):
    url = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                tokens = data.get("jettons", [])
                filtered = []
                for token in tokens:
                    cap = float(token.get("stats", {}).get("marketCap", 0))
                    if min_cap_usd <= cap <= max_cap_usd:
                        filtered.append(token)
                return filtered
    except Exception as e:
        logger.error(f"Ошибка при получении токенов: {e}")
        return []

def format_hot_tokens(tokens):
    result = []
    for idx, token in enumerate(tokens[:10], 1):
        cap = float(token.get("stats", {}).get("marketCap", 0))
        change = float(token.get("stats", {}).get("price24hChange", 0))
        name = token.get("ticker", "N/A")
        address = token.get("address", "")

        link = f"https://t.me/dtrade?start={REFERRAL_PREFIX}{address}"
        emoji = (
            "💎" if change >= 100 else
            "🤑" if change >= 50 else
            "🚀" if change >= 25 else
            "💸" if change >= 10 else
            "📈" if change >= 5 else
            "🥹" if change > 0 else
            "🫥" if change > -1 else
            "📉" if change > -5 else
            "💔" if change > -10 else
            "😭" if change > -25 else "🤡"
        )

        change_str = f"{emoji} {change:+.2f}%"
        cap_str = f"${cap / 1_000_000:.1f}M" if cap >= 1_000_000 else f"${cap / 1_000:.1f}K"
        line = f"├{change_str} • <a href=\"{link}\">{name}</a> • <b>{cap_str}</b>"
        result.append(line)
    return "\n".join(result)

async def send_token_list(update: Update, context: ContextTypes.DEFAULT_TYPE, min_cap, max_cap, store_dict, label):
    tokens = await fetch_filtered_hots(min_cap, max_cap)
    timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
    text = format_hot_tokens(tokens)
    message = f"{text}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F504 Обновить", callback_data=f"refresh_{label}")]])

    chat_id = update.effective_chat.id
    old_msg_id = store_dict.get(chat_id)
    if old_msg_id:
        try:
            await context.bot.unpin_chat_message(chat_id=chat_id, message_id=old_msg_id)
            await context.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
        except:
            pass

    sent = await update.message.reply_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
    try:
        await context.bot.pin_chat_message(chat_id=sent.chat_id, message_id=sent.message_id)
        store_dict[sent.chat_id] = sent.message_id
    except:
        pass

    return text, timestamp

async def hots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_hots_result
    text, timestamp = await send_token_list(update, context, 0, 200_000, pinned_hots_messages, "hots")
    latest_hots_result = {"page": text, "timestamp": timestamp}

async def bighots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_bighots_result
    text, timestamp = await send_token_list(update, context, 0, 10_000_000, pinned_bighots_messages, "bighots")
    latest_bighots_result = {"page": text, "timestamp": timestamp}

async def refresh_generic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, label, min_cap, max_cap, store_dict, result_store):
    query = update.callback_query
    await query.answer()
    tokens = await fetch_filtered_hots(min_cap, max_cap)
    timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
    text = format_hot_tokens(tokens)
    result_store["page"] = text
    result_store["timestamp"] = timestamp
    message = f"{text}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F504 Обновить", callback_data=f"refresh_{label}")]])

    try:
        await query.edit_message_text(text=message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение {label}: {e}")

async def refresh_hots_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await refresh_generic_callback(update, context, "hots", 0, 200_000, pinned_hots_messages, latest_hots_result)

async def refresh_bighots_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await refresh_generic_callback(update, context, "bighots", 0, 10_000_000, pinned_bighots_messages, latest_bighots_result)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CommandHandler("bighots", bighots_command))
    app.add_handler(CallbackQueryHandler(refresh_hots_callback, pattern="refresh_hots"))
    app.add_handler(CallbackQueryHandler(refresh_bighots_callback, pattern="refresh_bighots"))
    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()
