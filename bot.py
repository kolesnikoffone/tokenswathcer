import os
import logging
import json
from datetime import datetime, timedelta
import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise EnvironmentError("Нужна переменная TELEGRAM_BOT_TOKEN")

REFERRAL_PREFIX = "213213722_"
IGNORE_FILE = "ignored_tokens.json"
latest_result = {}
pinned_messages = {}

# Игнорируемые адреса по чатам
if os.path.exists(IGNORE_FILE):
    with open(IGNORE_FILE, "r") as f:
        ignored_by_chat = json.load(f)
else:
    ignored_by_chat = {}

def save_ignore_list():
    with open(IGNORE_FILE, "w") as f:
        json.dump(ignored_by_chat, f)

def address_to_base64url(address: str) -> str:
    from pytoniq_core import Address
    return Address(address).to_str(
        is_user_friendly=True,
        is_bounceable=True,
        is_test_only=False,
        is_url_safe=True
    )

async def fetch_blum_tokens(min_cap: float, max_cap: float, chat_id: str):
    url = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                tokens = data.get("jettons", [])
                result = []
                ignored = set(ignored_by_chat.get(str(chat_id), []))
                for token in tokens:
                    cap = float(token.get("marketCap", 0))
                    change = float(token.get("price24hChange", 0))
                    address = token.get("address", "")

                    if address in ignored:
                        continue

                    if not (min_cap <= cap <= max_cap):
                        continue

                    if abs(change) < 2:
                        continue

                    name = token.get("symbol", "N/A")
                    emoji = (
                        "💎" if change > 100 else
                        "🤑" if change > 50 else
                        "🚀" if change > 25 else
                        "💸" if change > 10 else
                        "📈" if change > 5 else
                        "🥹" if change > 0 else
                        "🫥" if change > -1 else
                        "📉" if change > -5 else
                        "💔" if change > -10 else
                        "😭" if change > -25 else
                        "🤡"
                    )
                    cap_str = f"${cap/1e6:.1f}M" if cap >= 1_000_000 else f"${cap/1e3:.1f}K"
                    try:
                        encoded_address = address_to_base64url(address)
                        link = f"https://t.me/dtrade?start={REFERRAL_PREFIX}{encoded_address}"
                        line = f"├{emoji} {name} (<a href=\"{link}\">ссылка</a>) • {cap_str}"
                    except:
                        line = f"├{emoji} {name} • {cap_str}"
                    result.append(line)

                page = "\n".join(result[:20])
                timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
                return page, timestamp
    except Exception as e:
        logger.error(f"Ошибка получения данных с Blum: {e}")
        return "", ""

async def show_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE, min_cap: float, max_cap: float):
    global latest_result, pinned_messages
    chat_id = update.effective_chat.id

    old_msg_id = pinned_messages.get(chat_id)
    if old_msg_id:
        try:
            await context.bot.unpin_chat_message(chat_id, old_msg_id)
            await context.bot.delete_message(chat_id, old_msg_id)
        except:
            pass

    page, timestamp = await fetch_blum_tokens(min_cap, max_cap, chat_id)
    if not page:
        return

    latest_result = {"page": page, "timestamp": timestamp}
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]])
    sent = await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=markup)
    await context.bot.pin_chat_message(chat_id, sent.message_id)
    pinned_messages[chat_id] = sent.message_id

async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_result
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    page, timestamp = await fetch_blum_tokens(4_000, 250_000, chat_id)
    if not page:
        return
    latest_result = {"page": page, "timestamp": timestamp}
    message = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]])
    await query.edit_message_text(message, parse_mode=ParseMode.HTML, reply_markup=markup)

async def hots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_tokens(update, context, 4_000, 250_000)

async def bighots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_tokens(update, context, 250_000, 10_000_000)

async def ignore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Укажите адрес токена.")
        return
    address = context.args[0]
    ignored = ignored_by_chat.setdefault(chat_id, [])
    if address not in ignored:
        ignored.append(address)
        save_ignore_list()
        await update.message.reply_text("Токен добавлен в игнор-лист.")
    else:
        await update.message.reply_text("Токен уже в игноре.")

async def deignore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Укажите адрес токена.")
        return
    address = context.args[0]
    ignored = ignored_by_chat.setdefault(chat_id, [])
    if address in ignored:
        ignored.remove(address)
        save_ignore_list()
        await update.message.reply_text("Токен удалён из игнора.")
    else:
        await update.message.reply_text("Токен не найден в игноре.")

async def ignorelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    ignored = ignored_by_chat.get(chat_id, [])
    if not ignored:
        await update.message.reply_text("Игнор-лист пуст.")
    else:
        await update.message.reply_text("Игнор-лист:\n" + "\n".join(ignored))

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CommandHandler("bighots", bighots_command))
    app.add_handler(CommandHandler("ignore", ignore_command))
    app.add_handler(CommandHandler("deignore", deignore_command))
    app.add_handler(CommandHandler("ignorelist", ignorelist_command))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern="refresh_hots"))
    app.run_polling()
