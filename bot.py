import logging
import os
import aiohttp
import base64
import crcmod
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
last_token_message = None
cached_token_result = None


def address_to_base64url(address: str) -> str:
    try:
        wc_str, hex_addr = address.split(":")
        wc = int(wc_str)
        addr_bytes = bytes.fromhex(hex_addr)

        tag = 0x11  # bounceable, not test-only
        workchain_byte = wc.to_bytes(1, byteorder="big", signed=True)
        data = bytes([tag]) + workchain_byte + addr_bytes

        crc16 = crcmod.predefined.mkPredefinedCrcFun('crc-ccitt-false')
        checksum = crc16(data).to_bytes(2, byteorder='big')
        full = data + checksum

        return base64.urlsafe_b64encode(full).decode().rstrip('=')
    except Exception as e:
        logger.warning(f"Ошибка при кодировании адреса {address}: {e}")
        return None


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
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                logger.info(f"BigPump API responded with status {response.status}")
                if response.status == 200:
                    data = await response.json()
                    tokens = data.get('coins', [])
                    ton_usd_price = await get_ton_price()
                    result = []

                    for idx, token in enumerate(tokens, 1):
                        try:
                            cap = float(token.get("marketCap", 0)) * ton_usd_price / 1e9
                            if cap < 11_000:
                                continue

                            name = token.get('name', 'N/A')
                            symbol = token.get('symbol', 'N/A')
                            address = token.get('address') or token.get('masterAddress')
                            change = token.get('priceChange1H')

                            mcap = f"<b>${cap/1000:.1f}K</b>" if cap >= 1_000 else f"<b>${cap:.2f}</b>"

                            if address:
                                encoded_address = address_to_base64url(address)
                                if encoded_address:
                                    link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{encoded_address}"
                                    name_symbol = f'<a href="{link}">{name} ({symbol})</a>'
                                else:
                                    name_symbol = f'{name} ({symbol})'
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
                        except:
                            continue

                    return ["\n\n".join(result)] if result else ["Нет подходящих токенов"]
                else:
                    return [f"Ошибка {response.status}"]
    except Exception as e:
        logger.exception("Ошибка при обращении к BigPump API")
        return [f"Ошибка при запросе: {str(e)}"]


async def listings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_token_message, cached_token_result

    if cached_token_result:
        tokens = cached_token_result
    else:
        tokens = await get_tokens()
        cached_token_result = tokens

    keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="refresh")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        last_token_message = await update.message.reply_text(tokens[0], parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)


async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_token_message, cached_token_result

    query = update.callback_query
    await query.answer()

    new_tokens = await get_tokens()

    if new_tokens != cached_token_result:
        cached_token_result = new_tokens
        try:
            await query.edit_message_text(new_tokens[0], parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data="refresh")]]), disable_web_page_preview=True)
        except Exception as e:
            logger.warning(f"Ошибка обновления сообщения: {e}")


if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("listings", listings_command))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern="refresh"))
    print("Бот запущен...")
    app.run_polling()
