import asyncio
import logging
import httpx
import base64
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart, Command
from aiogram import F

API_TOKEN = os.getenv('API_TOKEN')
BIGPUMP_API_URL = 'https://prod-api.bigpump.app/api/v1/coins/list?limit=150&sort=liq_mcap&order=desc'
BIGPUMP_API_TOKEN = os.getenv('BIGPUMP_API_TOKEN')
TON_API_URL = 'https://api.ton.sh/rates'
REFERRAL_PREFIX = 'prghZZEt-'
TELEGRAM_RAW_DATA = os.getenv('TELEGRAM_RAW_DATA')

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def address_to_base64url(address: str) -> str:
    address = address.strip()
    if ':' in address:
        wc, hex_addr = address.split(':')
        wc = int(wc)
        hex_addr = bytes.fromhex(hex_addr)
        full_addr = bytes([wc]) + hex_addr
    else:
        full_addr = bytes.fromhex(address)
    b64 = base64.urlsafe_b64encode(full_addr).rstrip(b'=').decode('utf-8')
    return b64

async def fetch_bigpump_data():
    headers = {
        'Authorization': f'Bearer {BIGPUMP_API_TOKEN}',
        'Origin': 'https://bigpump.app',
        'Referer': 'https://bigpump.app/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36',
        'telegramrawdata': TELEGRAM_RAW_DATA
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(BIGPUMP_API_URL, headers=headers)
        response.raise_for_status()
        return response.json()

async def fetch_ton_price():
    async with httpx.AsyncClient() as client:
        response = await client.get(TON_API_URL)
        response.raise_for_status()
        data = response.json()
        return float(data["rates"]["TON"]["prices"]["USD"])

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer("Напиши /tokens чтобы увидеть топ токены.")

@dp.message(Command("tokens"))
async def tokens_handler(message: types.Message):
    await send_tokens(message.chat.id)

@dp.callback_query(F.data == "refresh_tokens")
async def refresh_tokens_handler(callback_query: types.CallbackQuery):
    await send_tokens(callback_query.message.chat.id, callback_query.message.message_id)
    await callback_query.answer()

async def send_tokens(chat_id, message_id=None):
    try:
        bigpump_data = await fetch_bigpump_data()
        ton_price = await fetch_ton_price()
        tokens = bigpump_data.get("items", [])

        filtered_tokens = [
            token for token in tokens
            if token.get("marketCap") and (float(token["marketCap"]) / 10**9 * ton_price) >= 11000
        ]

        filtered_tokens = filtered_tokens[:30]

        result = []
        for idx, token in enumerate(filtered_tokens, start=1):
            name = token.get("name", "N/A")
            symbol = token.get("symbol", "N/A")
            mcap_value = token.get("marketCap")
            growth = token.get("priceChange1H", "N/A")
            address = token.get("address", None)

            if mcap_value:
                mcap = float(mcap_value) / 10**9 * ton_price
                mcap_str = f"<b>${mcap/1000:.1f}K</b>"
            else:
                mcap_str = "N/A"

            if address:
                encoded_address = address_to_base64url(address)
                token_link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{encoded_address}"
                clickable_name = f'<a href="{token_link}">{name} ({symbol})</a>'
            else:
                clickable_name = f'{name} ({symbol})'

            emoji = ""
            if growth != "N/A":
                try:
                    growth_value = float(growth)
                    if growth_value >= 100:
                        emoji = "💎"
                    elif growth_value >= 50:
                        emoji = "🤑"
                    elif growth_value >= 25:
                        emoji = "💸"
                    elif growth_value >= 10:
                        emoji = "💪"
                    elif growth_value >= 5:
                        emoji = "🙃"
                    elif growth_value > 0:
                        emoji = "🥹"
                    elif growth_value > -10:
                        emoji = "🥲"
                    elif growth_value > -25:
                        emoji = "😭"
                    else:
                        emoji = "🤡"
                except ValueError:
                    pass

            growth_str = f"{emoji} {growth}%" if growth != "N/A" else "N/A"

            line = f"{idx}. {clickable_name} | {mcap_str} | {growth_str}\n{chr(8212) * 35}"
            result.append(line)

        if result and result[-1].endswith(chr(8212) * 35):
            result[-1] = result[-1].rsplit("\n", 1)[0]

        final_text = "\n".join(result[:15])

        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_tokens")]
            ]
        )

        if message_id:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=final_text, reply_markup=markup, parse_mode='HTML', disable_web_page_preview=True)
        else:
            await bot.send_message(chat_id=chat_id, text=final_text, reply_markup=markup, parse_mode='HTML', disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Ошибка при получении токенов: {e}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
