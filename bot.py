import logging
import os
import aiohttp
import json
from pytoniq_core import Address
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

REFERRAL_PREFIX = "213213722_"
latest_hots_result = {"page": "", "timestamp": ""}
latest_bighots_result = {"page": "", "timestamp": ""}
pinned_hots_messages = {}
pinned_bighots_messages = {}
IGNORED_FILE = "ignored.json"


def address_to_base64url(address: str) -> str:
    return Address(address).to_str(
        is_user_friendly=True,
        is_bounceable=True,
        is_test_only=False,
        is_url_safe=True
    )

def load_ignored():
    try:
        with open(IGNORED_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_ignored(ignored):
    with open(IGNORED_FILE, "w") as f:
        json.dump(list(ignored), f)

ignored_addresses = load_ignored()


async def fetch_tokens(min_cap: float, max_cap: float):
    url = 'https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                tokens = data.get("jettons", [])
                filtered = []
                for token in tokens:
                    try:
                        change = float(token.get("stats", {}).get("price24hChange", 0))
                        cap = float(token.get("stats", {}).get("marketCap", 0))
                        address = token.get("address")
                        if abs(change) < 2:
                            continue
                        if address in ignored_addresses:
                            continue
                        if min_cap <= cap <= max_cap:
                            filtered.append((token, cap))
                    except:
                        continue
                result = []
                for idx, (token, cap) in enumerate(filtered[:10], 1):
                    name = token.get("name", "N/A")
                    symbol = token.get("ticker", "")
                    change = float(token.get("stats", {}).get("price24hChange", 0))
                    address = token.get("address")

                    mcap = f"${cap/1e6:.1f}M" if cap >= 1_000_000 else f"${cap/1e3:.1f}K"

                    try:
                        encoded_address = address_to_base64url(address)
                        link = f"https://t.me/dtrade?start={REFERRAL_PREFIX}{encoded_address}"
                        name_symbol = f'<a href="{link}">{symbol}</a>'
                    except:
                        name_symbol = f'{symbol}'

                    emoji = "💎" if change >= 100 else "🤑" if change >= 50 else "🚀" if change >= 25 else "💸" if change >= 10 else "📈" if change >= 5 else "🥹" if change > 0 else "🫥" if change > -1 else "📉" if change > -5 else "💔" if change > -10 else "😭" if change > -25 else "🤡"
                    growth_str = f"{emoji} {change:+.2f}%"
                    line = f"├{growth_str} • {name_symbol} • {mcap}"
                    result.append(line)

                timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
                return "\n".join(result), timestamp
    except Exception as e:
        logger.error(f"Ошибка получения токенов: {e}")
        return "", ""


async def send_hots(update: Update, context: ContextTypes.DEFAULT_TYPE, min_cap: float, max_cap: float, store: dict, pinned_store: dict, tag: str):
    chat_id = update.effective_chat.id
    old_msg_id = pinned_store.get(chat_id)
    if old_msg_id:
        try:
            await context.bot.unpin_chat_message(chat_id=chat_id, message_id=old_msg_id)
            await context.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить старое сообщение {tag}: {e}")

    page, timestamp = await fetch_tokens(min_cap, max_cap)
    if not page:
        return

    store["page"] = page
    store["timestamp"] = timestamp
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("\ud83d\udd04 Обновить", callback_data=f"refresh_{tag}")]])
    sent = await update.message.reply_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
    await context.bot.pin_chat_message(chat_id=chat_id, message_id=sent.message_id)
    pinned_store[chat_id] = sent.message_id


async def hots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_hots(update, context, 4_000, 250_000, latest_hots_result, pinned_hots_messages, "hots")


async def bighots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_hots(update, context, 250_000, 10_000_000, latest_bighots_result, pinned_bighots_messages, "bighots")


async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, min_cap: float, max_cap: float, store: dict, tag: str):
    query = update.callback_query
    await query.answer()
    page, timestamp = await fetch_tokens(min_cap, max_cap)
    if not page:
        return

    store["page"] = page
    store["timestamp"] = timestamp
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("\ud83d\udd04 Обновить", callback_data=f"refresh_{tag}")]])
    await query.edit_message_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)


async def refresh_hots_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await refresh_callback(update, context, 4_000, 250_000, latest_hots_result, "hots")


async def refresh_bighots_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await refresh_callback(update, context, 250_000, 10_000_000, latest_bighots_result, "bighots")


async def auto_update(context: ContextTypes.DEFAULT_TYPE, min_cap: float, max_cap: float, store: dict, pinned_store: dict, tag: str):
    page, timestamp = await fetch_tokens(min_cap, max_cap)
    if not page:
        return
    store["page"] = page
    store["timestamp"] = timestamp
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("\ud83d\udd04 Обновить", callback_data=f"refresh_{tag}")]])
    for chat_id, message_id in pinned_store.items():
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=message, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
        except Exception as e:
            logger.warning(f"Не удалось обновить сообщение {tag} в чате {chat_id}: {e}")


async def auto_update_hots(context: ContextTypes.DEFAULT_TYPE):
    await auto_update(context, 4_000, 250_000, latest_hots_result, pinned_hots_messages, "hots")


async def auto_update_bighots(context: ContextTypes.DEFAULT_TYPE):
    await auto_update(context, 250_000, 10_000_000, latest_bighots_result, pinned_bighots_messages, "bighots")


if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CommandHandler("bighots", bighots_command))
    app.add_handler(CallbackQueryHandler(refresh_hots_callback, pattern="^refresh_hots$"))
    app.add_handler(CallbackQueryHandler(refresh_bighots_callback, pattern="^refresh_bighots$"))
    app.job_queue.run_repeating(auto_update_hots, interval=10, first=10)
    app.job_queue.run_repeating(auto_update_bighots, interval=10, first=15)
    print("Бот запущен...")
    app.run_polling()
