import logging
import os
import aiohttp
import base64
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

last_valid_tokens = "Нет подходящих токенов"

def address_to_base64url(address: str) -> str:
    def crc16(data: bytes) -> bytes:
        crc = 0xFFFF
        for b in data:
            crc ^= b << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
                crc &= 0xFFFF
        return crc.to_bytes(2, 'big')

    address = address.strip()
    if ':' not in address:
        raise ValueError("Некорректный адрес: отсутствует ':'")

    wc_str, hex_part = address.split(':')
    wc = int(wc_str)
    addr_bytes = bytes.fromhex(hex_part)

    tag = b'\x11'
    wc_byte = wc.to_bytes(1, 'big', signed=True)
    full = tag + wc_byte + addr_bytes
    checksum = crc16(full)
    full_with_crc = full + checksum

    return base64.urlsafe_b64encode(full_with_crc).decode().rstrip('=')

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

                    filtered = []
                    for token in tokens:
                        try:
                            cap = float(token.get("marketCap", 0)) * ton_usd_price / 1e9
                            if cap >= 11000:
                                filtered.append((token, cap))
                        except:
                            continue

                    if not filtered:
                        logger.warning("Все токены отфильтрованы. Сохраняем старое значение.")
                        return None

                    for idx, (token, cap) in enumerate(filtered[:15], 1):
                        name = token.get('name', 'N/A')
                        symbol = token.get('symbol', 'N/A')
                        address = token.get('address')
                        change = token.get('priceChange1H')

                        mcap = f"<b>${cap/1000:.1f}K</b>" if cap >= 1_000 else f"<b>${cap:.2f}</b>"

                        if not address:
                            continue

                        try:
                            encoded_address = address_to_base64url(address)
                            link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{encoded_address}"
                            name_symbol = f'<a href="{link}">{name} ({symbol})</a>'
                        except Exception as e:
                            logger.warning(f"Ошибка при кодировании адреса {address}: {e}")
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

                    return "\n\n".join(result)
                else:
                    return None
    except Exception as e:
        logger.exception("Ошибка при обращении к BigPump API")
        return None

async def tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_valid_tokens
    tokens = await get_tokens()
    if tokens:
        last_valid_tokens = tokens

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Обновить", callback_data="refresh_tokens")]
    ])

    await update.message.reply_text(
        last_valid_tokens[:4000],
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=keyboard
    )

async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_valid_tokens
    query = update.callback_query
    await query.answer("Обновляю...")

    new_tokens = await get_tokens()
    if new_tokens:
        last_valid_tokens = new_tokens
    else:
        await query.answer("Данные актуальны ✅", show_alert=False)
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Обновить", callback_data="refresh_tokens")]
    ])

    try:
        await query.edit_message_text(
            last_valid_tokens[:4000],
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.exception(f"Ошибка при обновлении сообщения: {e}")
        await query.message.reply_text(
            "Не удалось обновить сообщение. Попробуйте снова позже.",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("tokens", tokens_command))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern="refresh_tokens"))
    print("Бот запущен...")
    app.run_polling()
