import os
import json
import logging
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
REFERRAL_PREFIX = "213213722_"
IGNORE_FILE = "ignore_list.json"

# Загрузка игнор-листа
if os.path.exists(IGNORE_FILE):
    with open(IGNORE_FILE, "r") as f:
        ignored_addresses = set(json.load(f))
else:
    ignored_addresses = set()

# Сохранение игнор-листа
def save_ignore_list():
    with open(IGNORE_FILE, "w") as f:
        json.dump(list(ignored_addresses), f)

# Формат адреса в base64url
def address_to_base64url(address: str) -> str:
    return Address(address).to_str(
        is_user_friendly=True,
        is_bounceable=True,
        is_test_only=False,
        is_url_safe=True
    )

# Получение токенов из Blum
async def fetch_tokens(min_cap: float, max_cap: float):
    url = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                tokens = data.get("jettons", [])
                result = []
                for token in tokens:
                    address = token.get("address")
                    if not address or address in ignored_addresses:
                        continue
                    cap = float(token.get("marketCap", 0))
                    change = float(token.get("price24hChange", 0))
                    if cap < min_cap or cap > max_cap or abs(change) < 2:
                        continue

                    try:
                        encoded_address = address_to_base64url(address)
                        ref_link = f"https://t.me/dtrade?start={REFERRAL_PREFIX}{encoded_address}"
                    except:
                        ref_link = ""

                    if cap >= 1_000_000:
                        cap_str = f"${cap/1e6:.1f}M"
                    else:
                        cap_str = f"${cap/1e3:.1f}K"

                    emoji = (
                        "💎" if change > 100 else "🤑" if change > 50 else
                        "🚀" if change > 25 else "💸" if change > 10 else
                        "📈" if change > 5 else "🥹"
                    )
                    line = f"├{emoji} +{change:.2f}% • <a href=\"{ref_link}\">{token.get('symbol')}</a> • {cap_str}"
                    result.append(line)
                return result
    except Exception as e:
        logging.error(f"Ошибка при получении токенов: {e}")
        return []

# Хендлеры
async def send_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE, min_cap: float, max_cap: float):
    chat_id = update.effective_chat.id
    tokens = await fetch_tokens(min_cap, max_cap)
    if not tokens:
        return
    timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
    text = "\n".join(tokens) + f"\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{min_cap}_{max_cap}")]])
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
    context.chat_data[f"msg_{min_cap}_{max_cap}"] = msg.message_id

async def hots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_tokens(update, context, 4_000, 250_000)

async def bighots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_tokens(update, context, 250_000, 10_000_000)

async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, min_cap, max_cap = query.data.split("_")
    tokens = await fetch_tokens(float(min_cap), float(max_cap))
    if not tokens:
        return
    timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
    text = "\n".join(tokens) + f"\n\nОбновлено: {timestamp} (UTC+3)"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data=query.data)]])
    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)

# Игнор-команды
async def ignore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Укажи адрес токена, который нужно игнорировать")
        return
    address = context.args[0]
    ignored_addresses.add(address)
    save_ignore_list()
    await update.message.reply_text(f"Добавлен в игнор: {address}")

async def deignore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Укажи адрес токена, который нужно удалить из игнора")
        return
    address = context.args[0]
    ignored_addresses.discard(address)
    save_ignore_list()
    await update.message.reply_text(f"Удалён из игнора: {address}")

async def ignorelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ignored_addresses:
        await update.message.reply_text("Игнор-лист пуст")
        return
    msg = "Игнор-лист:\n" + "\n".join(ignored_addresses)
    await update.message.reply_text(msg)

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CommandHandler("bighots", bighots_command))
    app.add_handler(CommandHandler("ignore", ignore_command))
    app.add_handler(CommandHandler("deignore", deignore_command))
    app.add_handler(CommandHandler("ignorelist", ignorelist_command))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern=r"^refresh_\\d+_\\d+$"))
    app.run_polling()
