import logging
import os
import aiohttp
import base64
import crcmod
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

REFERRAL_PREFIX = "prghZZEt-"
LATEST_RESULT = None
LATEST_MESSAGE_ID = {}


def address_to_base64url(address: str) -> str:
    address = address.strip()
    if ':' in address:
        wc, hex_addr = address.split(':')
        wc = int(wc)
        hex_addr = bytes.fromhex(hex_addr)
    else:
        wc = 0
        hex_addr = bytes.fromhex(address)

    tag = 0x11  # bounceable = 1, testnet = 0
    workchain_byte = wc.to_bytes(1, byteorder="big", signed=True)
    data = bytes([tag]) + workchain_byte + hex_addr

    crc16 = crcmod.predefined.mkPredefinedCrcFun('crc-ccitt-false')
    checksum = crc16(data).to_bytes(2, 'big')

    full_data = data + checksum
    return base64.urlsafe_b64encode(full_data).rstrip(b'=').decode()


async def get_ton_price():
    url = 'https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data["the-open-network"]["usd"])
    except Exception as e:
        logger.warning(f"Не удалось получить цену TON: {e}")
    return 0


async def get_tokens():
    url = 'https://prod-api.bigpump.app/api/v1/coins?sortType=pocketfi&limit=30'
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9,ru-RU;q=0.8,ru;q=0.7',
        'authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJhZGRyZXNzIjoiMDpmNWI5MWRkZDBiOWM4N2VmNjUwMTFhNzlmMWRhNzE5NzIwYzVhODgwN2I1NGMxYTQwNTIyNzRmYTllMzc5YmNkIiwibmV0d29yayI6Ii0yMzkiLCJpYXQiOjE3NDI4MDY4NTMsImV4cCI6MTc3NDM2NDQ1M30.U_GaaX5psI572w4YmwAjlh8u4uFBVHdsD-zJacvWiPo',
        'origin': 'https://bigpump.app',
        'referer': 'https://bigpump.app/',
        'user-agent': 'Mozilla/5.0'
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


async def listings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LATEST_RESULT, LATEST_MESSAGE_ID

    tokens_data = await get_tokens()
    coins = tokens_data.get("coins", [])
    ton_usd_price = await get_ton_price()

    result = []
    for idx, token in enumerate(coins[:15], 1):
        name = token.get('name', 'N/A')
        symbol = token.get('symbol', 'N/A')
        address = token.get('address')
        change = token.get('priceChange1H')

        try:
            cap = float(token.get("marketCap", 0)) * ton_usd_price / 1e9
            mcap = f"<b>${cap/1000:.1f}K</b>" if cap >= 1_000 else f"<b>${cap:.2f}</b>"
        except:
            mcap = "N/A"

        if address:
            try:
                encoded = address_to_base64url(address)
                link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{encoded}"
                name_symbol = f'<a href="{link}">{name} ({symbol})</a>'
            except:
                name_symbol = f"{name} ({symbol})"
        else:
            name_symbol = f"{name} ({symbol})"

        emoji = ""
        try:
            growth = float(change)
            if growth >= 100:
                emoji = "💎"
            elif growth >= 50:
                emoji = "🤑"
            elif growth >= 25:
                emoji = "💸"
            elif growth >= 10:
                emoji = "💪"
            elif growth >= 5:
                emoji = "🙃"
            elif growth > 0:
                emoji = "🥹"
            elif growth > -10:
                emoji = "🥲"
            elif growth > -25:
                emoji = "😭"
            else:
                emoji = "🤡"
            growth_str = f"{emoji} {growth:.2f}%"
        except:
            growth_str = "N/A"

        result.append(f"{idx}. {name_symbol} | {mcap} | {growth_str}")

    if not result:
        result = ["Нет подходящих токенов"]

    LATEST_RESULT = "\n\n".join(result)

    keyboard = [[InlineKeyboardButton("🔁 Обновить", callback_data="refresh")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = await update.message.reply_text(
        LATEST_RESULT,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )

    LATEST_MESSAGE_ID[update.effective_chat.id] = message.message_id


async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LATEST_RESULT

    query = update.callback_query
    await query.answer()

    tokens_data = await get_tokens()
    coins = tokens_data.get("coins", [])
    ton_usd_price = await get_ton_price()

    result = []
    for idx, token in enumerate(coins[:15], 1):
        name = token.get('name', 'N/A')
        symbol = token.get('symbol', 'N/A')
        address = token.get('address')
        change = token.get('priceChange1H')

        try:
            cap = float(token.get("marketCap", 0)) * ton_usd_price / 1e9
            mcap = f"<b>${cap/1000:.1f}K</b>" if cap >= 1_000 else f"<b>${cap:.2f}</b>"
        except:
            mcap = "N/A"

        if address:
            try:
                encoded = address_to_base64url(address)
                link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{encoded}"
                name_symbol = f'<a href="{link}">{name} ({symbol})</a>'
            except:
                name_symbol = f"{name} ({symbol})"
        else:
            name_symbol = f"{name} ({symbol})"

        emoji = ""
        try:
            growth = float(change)
            if growth >= 100:
                emoji = "💎"
            elif growth >= 50:
                emoji = "🤑"
            elif growth >= 25:
                emoji = "💸"
            elif growth >= 10:
                emoji = "💪"
            elif growth >= 5:
                emoji = "🙃"
            elif growth > 0:
                emoji = "🥹"
            elif growth > -10:
                emoji = "🥲"
            elif growth > -25:
                emoji = "😭"
            else:
                emoji = "🤡"
            growth_str = f"{emoji} {growth:.2f}%"
        except:
            growth_str = "N/A"

        result.append(f"{idx}. {name_symbol} | {mcap} | {growth_str}")

    new_text = "\n\n".join(result)

    if new_text != LATEST_RESULT:
        LATEST_RESULT = new_text
        try:
            await context.bot.edit_message_text(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                text=new_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=query.message.reply_markup
            )
        except Exception:
            pass


if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("listings", listings_command))
    app.add_handler(CallbackQueryHandler(refresh_callback))
    app.run_polling()
