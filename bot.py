import logging
import os
from datetime import datetime, timedelta
import aiohttp
from pytoniq_core import Address
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

REFERRAL_PREFIX = "213213722_"
latest_hots_result = {"page": "", "timestamp": ""}
pinned_hots_messages = {}

def address_to_base64url(address: str) -> str:
    return Address(address).to_str(
        is_user_friendly=True,
        is_bounceable=True,
        is_test_only=False,
        is_url_safe=True
    )

async def fetch_tokens_from_blum():
    url = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                tokens = data.get("jettons", [])
                filtered = []

                for token in tokens[:10]:
                    name = token.get("name", "N/A")
                    symbol = token.get("ticker", "N/A")
                    change = float(token.get("stats", {}).get("price24hChange", 0))
                    cap = float(token.get("stats", {}).get("marketCap", 0))
                    address = token.get("address")

                    filtered.append({
                        "name": name,
                        "symbol": symbol,
                        "change": change,
                        "cap": cap,
                        "address": address
                    })

                lines = []
                for token in filtered:
                    growth = token["change"]
                    emoji = (
                        "💎" if growth >= 100 else
                        "🤑" if growth >= 50 else
                        "🚀" if growth >= 25 else
                        "💸" if growth >= 10 else
                        "📈" if growth >= 5 else
                        "🥹" if growth > 0 else
                        "🫥" if growth > -1 else
                        "📉" if growth > -5 else
                        "💔" if growth > -10 else
                        "😭" if growth > -25 else
                        "🤡"
                    )
                    growth_str = f"{emoji} {growth:+.2f}%"

                    cap_str = (
                        f"${token['cap']/1e6:.1f}M" if token["cap"] >= 1e6 else
                        f"${token['cap']/1e3:.1f}K" if token["cap"] >= 1e3 else
                        f"${token['cap']:.0f}"
                    )

                    try:
                        addr = address_to_base64url(token["address"])
                        link = f'<a href="https://t.me/dtrade?start={REFERRAL_PREFIX}{addr}">{token["symbol"]}</a>'
                    except:
                        link = token["symbol"]

                    line = f"├{growth_str} • {link} • {cap_str}"
                    lines.append(line)

                page = "\n".join(lines)
                timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
                return page, timestamp
    except Exception as e:
        logger.exception("Ошибка при получении hot токенов с Blum")
        return "", ""

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

    page, timestamp = await fetch_tokens_from_blum()
    if not page:
        return

    latest_hots_result = {"page": page, "timestamp": timestamp}
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]])
    sent = await update.message.reply_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)

    try:
        await context.bot.pin_chat_message(chat_id, sent.message_id)
        pinned_hots_messages[chat_id] = sent.message_id
    except Exception as e:
        logger.warning(f"Не удалось закрепить сообщение HOTS: {e}")

async def refresh_hots_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_hots_result
    query = update.callback_query
    await query.answer()
    page, timestamp = await fetch_tokens_from_blum()
    if not page:
        return
    latest_hots_result = {"page": page, "timestamp": timestamp}
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]])
    try:
        await query.edit_message_text(text=message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
    except Exception as e:
        logger.warning(f"Не удалось обновить HOTS сообщение: {e}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CallbackQueryHandler(refresh_hots_callback, pattern="^refresh_hots$"))
    print("Бот запущен...")
    app.run_polling()
