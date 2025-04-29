import os
import requests
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Переменные
API_TOKEN = os.getenv("API_TOKEN")
BIGPUMP_URL = "https://prod-api.bigpump.app/api/v1/coins/list?limit=150&sort=liq_mcap&order=desc"
TON_PRICE_URL = "https://api.ton.sh/rates"
REFERRAL_PREFIX = "prghZZEt-"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Функции

def address_to_base64url(address: str) -> str:
    address = address.strip()
    wc, hex_addr = address.split(":")
    full_addr = bytes([int(wc)]) + bytes.fromhex(hex_addr)
    return requests.utils.quote(full_addr)

def get_ton_price() -> float:
    response = requests.get(TON_PRICE_URL)
    response.raise_for_status()
    return float(response.json()["rates"]["TON"]["prices"]["USD"])

def get_tokens():
    response = requests.get(BIGPUMP_URL)
    response.raise_for_status()
    return response.json()["items"]

def format_tokens(tokens, ton_price):
    result = []

    filtered = [
        t for t in tokens
        if t.get("marketCap") and (float(t["marketCap"]) / 10**9 * ton_price) >= 11000
    ][:30]

    for idx, token in enumerate(filtered, 1):
        name = token.get("name", "N/A")
        symbol = token.get("symbol", "N/A")
        market_cap = token.get("marketCap")
        growth = token.get("priceChange1H", "N/A")
        address = token.get("address")

        mcap = float(market_cap) / 10**9 * ton_price if market_cap else 0
        mcap_str = f"<b>${mcap/1000:.1f}K</b>" if mcap else "N/A"

        emoji = ""
        if growth != "N/A":
            try:
                g = float(growth)
                if g >= 100:
                    emoji = "💎"
                elif g >= 50:
                    emoji = "🤑"
                elif g >= 25:
                    emoji = "💸"
                elif g >= 10:
                    emoji = "💪"
                elif g >= 5:
                    emoji = "🙃"
                elif g > 0:
                    emoji = "🫩"
                elif g > -10:
                    emoji = "🫲"
                elif g > -25:
                    emoji = "😭"
                else:
                    emoji = "🤡"
            except:
                pass

        growth_str = f"{emoji} {growth}%" if growth != "N/A" else "N/A"

        if address:
            addr_encoded = address_to_base64url(address)
            token_link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{addr_encoded}"
            name_symbol = f'<a href="{token_link}">{name} ({symbol})</a>'
        else:
            name_symbol = f"{name} ({symbol})"

        line = f"{idx}. {name_symbol} | {mcap_str} | {growth_str}\n{'\u2014'*35}"
        result.append(line)

    if result:
        result[-1] = result[-1].rsplit("\n", 1)[0]

    return "\n".join(result[:15])

# Обработчики

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Напиши /tokens чтобы увидеть топ токены.")

async def tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_tokens(update.effective_chat.id)

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_tokens(query.message.chat_id, query.message.message_id)

async def send_tokens(chat_id, message_id=None):
    try:
        ton_price = get_ton_price()
        tokens = get_tokens()
        text = format_tokens(tokens, ton_price)

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔄 Обновить", callback_data="refresh")]]
        )

        if message_id:
            await app.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text,
                parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True
            )
        else:
            await app.bot.send_message(
                chat_id=chat_id, text=text,
                parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True
            )

    except Exception as e:
        logger.error(f"Ошибка: {e}")

# Старт

app = Application.builder().token(API_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("tokens", tokens))
app.add_handler(CallbackQueryHandler(refresh, pattern="refresh"))

if __name__ == "__main__":
    app.run_polling()
