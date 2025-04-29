import logging
import os
import aiohttp
from tonsdk.utils import Address
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

REFERRAL_PREFIX = "prghZZEt-"
latest_tokens_cache = None

def address_to_base64url(address: str) -> str:
    try:
        wc, hex_addr = address.strip().split(":")
        wc = int(wc)
        addr = Address(wc=wc, address=bytes.fromhex(hex_addr))
        return addr.to_string(bounceable=True, url_safe=True)
    except Exception as e:
        logger.warning(f"Ошибка при кодировании адреса {address}: {e}")
        return ""

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
        'authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJhZGRyZXNzIjoiMDpmNWI5...snip...wiPo',
        'origin': 'https://bigpump.app',
        'referer': 'https://bigpump.app/',
        'user-agent': 'Mozilla/5.0'
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                logger.info(f"BigPump API responded with status {response.status}")
                if response.status == 200:
                    data = await response.json()
                    tokens = data.get('coins', [])
                    ton_usd_price = await get_ton_price()
                    result = []

                    filtered = []
                    for token in tokens:
                        try:
                            cap = float(token.get("marketCap", 0)) * ton_usd_price / 1e9
                            if cap >= 11000:
                                filtered.append((token, cap))
                        except:
                            continue

                    for idx, (token, cap) in enumerate(filtered[:15], 1):
                        name = token.get('name', 'N/A')
                        symbol = token.get('symbol', 'N/A')
                        address = token.get('address')
                        change = token.get('priceChange1H')

                        mcap = f"<b>${cap/1000:.1f}K</b>" if cap >= 1_000 else f"<b>${cap:.2f}</b>"

                        name_symbol = f'{name} ({symbol})'
                        if address:
                            encoded_address = address_to_base64url(address)
                            if encoded_address:
                                link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{encoded_address}"
                                name_symbol = f'<a href="{link}">{name} ({symbol})</a>'

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
                                emoji = "🤭"
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

                        line = f"{idx}. {name_symbol} | {mcap} | {growth_str}"
                        result.append(line)

                    return ["\n\n".join(result)] if result else ["Нет подходящих токенов"]
                else:
                    return [f"Ошибка {response.status}"]
    except Exception as e:
        logger.exception("Ошибка при обращении к BigPump API")
        return [f"Ошибка при запросе: {str(e)}"]

async def listings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_tokens_cache
    tokens = await get_tokens()
    latest_tokens_cache = tokens
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Обновить", callback_data="refresh")]
    ])
    await update.message.reply_text(tokens[0], parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=keyboard)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_tokens_cache
    query = update.callback_query
    await query.answer()
    tokens = await get_tokens()
    if tokens[0] != latest_tokens_cache[0]:
        latest_tokens_cache = tokens
        await query.edit_message_text(tokens[0], parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Обновить", callback_data="refresh")]
        ]))

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("listings", listings_command))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="refresh"))
    print("Бот запущен...")
    app.run_polling()
