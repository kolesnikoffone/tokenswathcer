import os
import logging
from datetime import datetime, timedelta
import aiohttp
import json
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REFERRAL_PREFIX = "213213722_"
IGNORE_FILE = "ignorelist.json"

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set")

pinned_messages = {}
latest_pages = {
    "hots": {"page": "", "timestamp": ""},
    "bighots": {"page": "", "timestamp": ""},
}

def load_ignore_list():
    if not os.path.exists(IGNORE_FILE):
        return set()
    with open(IGNORE_FILE, "r") as f:
        return set(json.load(f))

def save_ignore_list(ignore_set):
    with open(IGNORE_FILE, "w") as f:
        json.dump(list(ignore_set), f)

def address_to_base64url(address: str) -> str:
    return Address(address).to_str(
        is_user_friendly=True,
        is_bounceable=True,
        is_test_only=False,
        is_url_safe=True
    )

async def fetch_tokens(min_cap: float, max_cap: float):
    url = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
    ignore_set = load_ignore_list()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                tokens = data.get("jettons", [])
                result = []
                for token in tokens:
                    try:
                        address = token.get("address")
                        if not address or address in ignore_set:
                            continue

                        cap = float(token.get("marketCap", 0))
                        if not (min_cap <= cap <= max_cap):
                            continue

                        change = float(token.get("price24hChange", 0))
                        if abs(change) < 2:
                            continue

                        symbol = token.get("symbol", "")
                        encoded = address_to_base64url(address)
                        link = f"https://t.me/dtrade?start={REFERRAL_PREFIX}{encoded}"

                        emoji = "💎" if change >= 100 else "🤑" if change >= 50 else "🚀" if change >= 25 else "💸" if change >= 10 else "📈" if change >= 5 else "🥹" if change > 0 else "🫥" if change > -1 else "📉" if change > -5 else "💔" if change > -10 else "😭" if change > -25 else "🤡"
                        growth = f"{emoji} {change:+.2f}%"
                        cap_str = f"${cap/1e6:.1f}M" if cap >= 1_000_000 else f"${cap/1e3:.1f}K"

                        result.append(f"├{growth} • <a href=\"{link}\">{symbol}</a> • {cap_str}")
                    except:
                        continue

                page = "\n".join(result)
                timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
                return page, timestamp
    except Exception as e:
        logger.error(f"Fetch error: {e}")
        return "", ""

async def show_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE, cmd: str, min_cap: float, max_cap: float):
    chat_id = update.effective_chat.id
    old_msg_id = pinned_messages.get((chat_id, cmd))
    if old_msg_id:
        try:
            await context.bot.unpin_chat_message(chat_id, old_msg_id)
            await context.bot.delete_message(chat_id, old_msg_id)
        except:
            pass

    page, timestamp = await fetch_tokens(min_cap, max_cap)
    if not page:
        return
    latest_pages[cmd] = {"page": page, "timestamp": timestamp}
    text = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{cmd}")]])
    sent = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    await context.bot.pin_chat_message(chat_id, sent.message_id)
    pinned_messages[(chat_id, cmd)] = sent.message_id

async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cmd = query.data.replace("refresh_", "")
    await query.answer()

    cap_ranges = {
        "hots": (4000, 250_000),
        "bighots": (250_000, 10_000_000)
    }
    min_cap, max_cap = cap_ranges.get(cmd, (0, 10_000_000))
    page, timestamp = await fetch_tokens(min_cap, max_cap)
    if not page:
        return
    latest_pages[cmd] = {"page": page, "timestamp": timestamp}
    text = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{cmd}")]])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)

# Команды
async def hots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_tokens(update, context, "hots", 4000, 250_000)

async def bighots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_tokens(update, context, "bighots", 250_000, 10_000_000)

async def ignore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Формат: /ignore <contract_address>")
    ignore_set = load_ignore_list()
    ignore_set.add(context.args[0])
    save_ignore_list(ignore_set)
    await update.message.reply_text("Добавлено в игнор")

async def deignore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Формат: /deignore <contract_address>")
    ignore_set = load_ignore_list()
    ignore_set.discard(context.args[0])
    save_ignore_list(ignore_set)
    await update.message.reply_text("Удалено из игнора")

async def ignorelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ignore_set = load_ignore_list()
    if not ignore_set:
        return await update.message.reply_text("Игнор-лист пуст")
    await update.message.reply_text("\n".join(ignore_set))

# Автообновление
async def auto_refresh(context: ContextTypes.DEFAULT_TYPE):
    for cmd, (min_cap, max_cap) in {"hots": (4000, 250_000), "bighots": (250_000, 10_000_000)}.items():
        page, timestamp = await fetch_tokens(min_cap, max_cap)
        if not page:
            continue
        latest_pages[cmd] = {"page": page, "timestamp": timestamp}
        text = f"{page}\n\nОбновлено: {timestamp} (UTC+3)"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{cmd}")]])
        for (chat_id, label), msg_id in pinned_messages.items():
            if label != cmd:
                continue
            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode=ParseMode.HTML, reply_markup=markup)
            except Exception as e:
                logger.warning(f"Auto-update error for {chat_id}: {e}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots))
    app.add_handler(CommandHandler("bighots", bighots))
    app.add_handler(CommandHandler("ignore", ignore))
    app.add_handler(CommandHandler("deignore", deignore))
    app.add_handler(CommandHandler("ignorelist", ignorelist))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern=r"refresh_.*"))
    app.job_queue.run_repeating(auto_refresh, interval=10, first=10)
    print("Bot started...")
    app.run_polling()
