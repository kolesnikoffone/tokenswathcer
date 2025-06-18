import logging
import os
import aiohttp
from pytoniq_core import Address
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    JobQueue,
)
from datetime import datetime, timedelta

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

REFERRAL_PREFIX = "213213722_"
latest_results = {
    "hots": {"page": "", "timestamp": "", "pinned": {}},
    "bighots": {"page": "", "timestamp": "", "pinned": {}}
}

def address_to_base64url(address: str) -> str:
    return Address(address).to_str(
        is_user_friendly=True,
        is_bounceable=True,
        is_test_only=False,
        is_url_safe=True
    )

async def fetch_all_tokens():
    url = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return (await response.json()).get("jettons", [])
    except Exception as e:
        logger.warning(f"Ошибка получения токенов: {e}")
    return []

def format_token_line(token):
    try:
        change = float(token.get("stats", {}).get("price24hChange", 0))
        cap = float(token.get("stats", {}).get("marketCap", 0))
        symbol = token.get("ticker")
        name = token.get("name")
        addr = token.get("address")

        emoji = "💎" if change >= 100 else "🤑" if change >= 50 else "🚀" if change >= 25 else "💸" if change >= 10 else "📈" if change >= 5 else "🥹" if change > 0 else "🫥" if change > -1 else "📉" if change > -5 else "💔" if change > -10 else "😭" if change > -25 else "🤡"
        growth_str = f"{emoji} {change:+.2f}%"
        cap_str = f"${cap/1e6:.1f}M" if cap >= 1_000_000 else f"${cap/1e3:.1f}K"

        encoded_address = address_to_base64url(addr)
        link = f"https://t.me/dtrade?start={REFERRAL_PREFIX}{encoded_address}"
        name_link = f"<a href=\"{link}\">{symbol}</a>"

        return f"├{growth_str} • {name_link} • <b>{cap_str}</b>"
    except Exception as e:
        logger.warning(f"Ошибка при форматировании токена: {e}")
        return ""

async def generate_token_page(min_cap, max_cap):
    tokens = await fetch_all_tokens()
    filtered = []
    for token in tokens:
        try:
            cap = float(token.get("stats", {}).get("marketCap", 0))
            if min_cap <= cap <= max_cap:
                filtered.append(token)
        except:
            continue
    result_lines = [format_token_line(t) for t in filtered[:10]]
    timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
    return "\n".join(result_lines), timestamp

async def post_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, min_cap: float, max_cap: float):
    global latest_results
    chat_id = update.effective_chat.id
    pinned = latest_results[key]["pinned"]

    if chat_id in pinned:
        try:
            await context.bot.unpin_chat_message(chat_id, pinned[chat_id])
            await context.bot.delete_message(chat_id, pinned[chat_id])
        except:
            pass

    page, timestamp = await generate_token_page(min_cap, max_cap)
    latest_results[key].update({"page": page, "timestamp": timestamp})
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{key}")]])
    sent = await update.message.reply_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
    await context.bot.pin_chat_message(chat_id, sent.message_id)
    pinned[chat_id] = sent.message_id

async def hots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await post_tokens(update, context, "hots", 4000, 250000)

async def bighots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await post_tokens(update, context, "bighots", 250000, 10_000_000)

async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_results
    query = update.callback_query
    chat_id = query.message.chat_id
    await query.answer()

    key = "hots" if "refresh_hots" in query.data else "bighots"
    min_cap, max_cap = (4000, 250000) if key == "hots" else (250000, 10_000_000)

    page, timestamp = await generate_token_page(min_cap, max_cap)
    latest_results[key].update({"page": page, "timestamp": timestamp})
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{key}")]])

    try:
        await query.edit_message_text(text=message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
    except Exception as e:
        logger.warning(f"Ошибка обновления сообщения: {e}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CommandHandler("bighots", bighots_command))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern="^refresh_(hots|bighots)$"))
    print("Бот запущен...")
    app.run_polling()
