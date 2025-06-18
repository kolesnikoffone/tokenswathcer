import os
import logging
import aiohttp
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from pytoniq_core import Address

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise EnvironmentError("TELEGRAM_BOT_TOKEN не установлен")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REFERRAL_PREFIX = "213213722_"

latest_results = {
    "hots": {"page": "", "timestamp": ""},
    "bighots": {"page": "", "timestamp": ""},
}
pinned_messages = {}
ignored_addresses = {}


def address_to_base64url(address: str) -> str:
    return Address(address).to_str(
        is_user_friendly=True,
        is_bounceable=True,
        is_test_only=False,
        is_url_safe=True
    )


async def fetch_tokens(min_cap: float, max_cap: float):
    url = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                tokens = data.get("jettons", [])
                result = []
                for idx, token in enumerate(tokens):
                    cap = float(token.get("marketCap", 0))
                    change = float(token.get("price24hChange", 0))
                    if cap < min_cap or cap > max_cap:
                        continue
                    if abs(change) < 2:
                        continue

                    name = token.get("name", "N/A")
                    symbol = token.get("symbol", "")
                    address = token.get("address")
                    if not address:
                        continue

                    try:
                        encoded = address_to_base64url(address)
                        ref = f"https://t.me/dtrade?start={REFERRAL_PREFIX}{encoded}"
                    except:
                        continue

                    emoji = (
                        "💎" if change > 100 else
                        "🚀" if change > 50 else
                        "💸" if change > 10 else
                        "📈" if change > 5 else
                        "🥹" if change > 0 else
                        "📉"
                    )
                    cap_str = f"${cap/1e6:.1f}M" if cap > 1_000_000 else f"${cap/1e3:.1f}K"
                    line = f"├{emoji} +{change:.2f}% • {symbol} ({ref}) • {cap_str}"
                    result.append((cap, line))

                result.sort(key=lambda x: -x[0])
                lines = [line for _, line in result[:10]]
                page = "\n".join(lines)
                timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
                return page, timestamp
    except Exception as e:
        logger.error(f"Ошибка при получении токенов: {e}")
        return "", ""


async def send_hot_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, min_cap: float, max_cap: float):
    chat_id = update.effective_chat.id
    old_msg_id = pinned_messages.get((chat_id, key))
    if old_msg_id:
        try:
            await context.bot.unpin_chat_message(chat_id, old_msg_id)
            await context.bot.delete_message(chat_id, old_msg_id)
        except:
            pass

    page, timestamp = await fetch_tokens(min_cap, max_cap)
    if not page:
        return

    for ignored in ignored_addresses.get(chat_id, set()):
        page = "\n".join([line for line in page.splitlines() if ignored not in line])

    latest_results[key] = {"page": page, "timestamp": timestamp}
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{key}")]])
    sent = await update.message.reply_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
    await context.bot.pin_chat_message(chat_id, sent.message_id)
    pinned_messages[(chat_id, key)] = sent.message_id


async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.replace("refresh_", "")
    min_cap, max_cap = (4_000, 250_000) if key == "hots" else (250_000, 10_000_000)
    page, timestamp = await fetch_tokens(min_cap, max_cap)
    if not page:
        return

    chat_id = query.message.chat.id
    for ignored in ignored_addresses.get(chat_id, set()):
        page = "\n".join([line for line in page.splitlines() if ignored not in line])

    latest_results[key] = {"page": page, "timestamp": timestamp}
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{key}")]])
    await query.edit_message_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)


async def ignore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /ignore <contract_address>")
        return

    addr = context.args[0]
    ignored_addresses.setdefault(chat_id, set()).add(addr)
    await update.message.reply_text(f"Контракт {addr} добавлен в игнор-лист.")


async def hots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_hot_tokens(update, context, "hots", 4_000, 250_000)


async def bighots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_hot_tokens(update, context, "bighots", 250_000, 10_000_000)


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CommandHandler("bighots", bighots_command))
    app.add_handler(CommandHandler("ignore", ignore_command))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern="^refresh_"))
    app.run_polling()
