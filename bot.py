import logging
import os
import aiohttp
import base64
import crcmod
import struct
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

def address_to_base64url(address: str) -> str:
    address = address.strip()
    wc, hex_part = address.split(":")
    wc = int(wc)
    addr_bytes = bytes.fromhex(hex_part)
    tag = 0x11  # bounceable, non-testnet
    workchain_byte = wc.to_bytes(1, byteorder="big", signed=True)
    data = bytes([tag]) + workchain_byte + addr_bytes
    crc16 = crcmod.predefined.mkPredefinedCrcFun('crc-ccitt-false')
    checksum = crc16(data).to_bytes(2, 'big')
    return base64.urlsafe_b64encode(data + checksum).rstrip(b'=').decode()

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
        'authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJhZGRyZXNzIjoiMDpmNWI5MWRkZDBiOWM4N2VmNjUwMTFhNzlmMWRhNzE5NzIwYzVhODgwN2I1NGMxYTQwNTIyNzRmYTllMzc5YmNkIiwibmV0d29yayI6Ii0yMzkiLCJpYXQiOjE3NDI4MDY4NTMsImV4cCI6MTc3NDM2NDQ1M30.U_GaaX5psI572w4yMwAjlh8u4uFBVHdsD-zJacvWiPo',
        'accept': '*/*',
        'origin': 'https://bigpump.app',
        'referer': 'https://bigpump.app/',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
        'telegramrawdata': 'query_id=AAEaYrUMAAAAABpitQwu6gcp&user=%7B%22id%22%3A213213722%2C%22first_name%22%3A%22Igor%22%2C%22last_name%22%3A%22Koles%22%2C%22username%22%3A%22kolesnikoffone%22%2C%22language_code%22%3A%22en%22%2C%22is_premium%22%3Atrue%2C%22allows_write_to_pm%22%3Atrue%2C%22photo_url%22%3A%22https%3A%5C%2F%5C%2Ft.me%5C%2Fi%5C%2Fuserpic%5C%2F320%5C%2FLOS2-JjhnhmjzAqoRwJhBdgkfv48pIMkDeo8El8OkCc.svg%22%7D&auth_date=1739471509&signature=_BACnt92QPix6-bfrlGuo5HiA4XBiSI6BP-v3jQRUVJqp2N8ydUMmWGixj4e9s9x0o0xONFOa51eo2W1JfbYBQ&hash=0c3fd36bf663249d93da37b949087c716d9e883171da0fa107f026bf439bd9d3'
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

                        if address:
                            encoded_address = address_to_base64url(address)
                            link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{encoded_address}"
                            name_symbol = f'<a href="{link}">{name} ({symbol})</a>'
                        else:
                            name_symbol = f'{name} ({symbol})'

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

                        line = f"{idx}. {name_symbol} | {mcap} | {growth_str}"
                        result.append(line)

                    return ["\n\n".join(result)] if result else ["Нет подходящих токенов"]
                else:
                    return [f"Ошибка {response.status}"]
    except Exception as e:
        logger.exception("Ошибка при обращении к BigPump API")
        return [f"Ошибка при запросе: {str(e)}"]


async def tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Получаю токены с BigPump...")
    tokens = await get_tokens()
    keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data='refresh')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    for t in tokens:
        await update.message.reply_text(t, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)


async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tokens = await get_tokens()
    if tokens:
        await query.edit_message_text(tokens[0], parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data='refresh')]]))


if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("tokens", tokens_command))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern='refresh'))
    print("Бот запущен...")
    app.run_polling()
