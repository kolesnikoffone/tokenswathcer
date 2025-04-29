import asyncio
import logging
import httpx
import base64
import os
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")

BIGPUMP_API_URL = 'https://prod-api.bigpump.app/api/v1/coins/list?limit=150&sort=liq_mcap&order=desc'
TON_API_URL = 'https://api.ton.sh/rates'
REFERRAL_PREFIX = 'prghZZEt-'

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
        'Authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJhZGRyZXNzIjoiMDpmNWI5MWRkZDBiOWM4N2VmNjUwMTFhNzlmMWRhNzE5NzIwYzVhODgwN2I1NGMxYTQwNTIyNzRmYTllMzc5YmNkIiwibmV0d29yayI6Ii0yMzkiLCJpYXQiOjE3NDI4MDY4NTMsImV4cCI6MTc3NDM2NDQ1M30.U_GaaX5psI572w4YmwAjlh8u4uFBVHdsD-zJacvWiPo',
        'Origin': 'https://bigpump.app',
        'Referer': 'https://bigpump.app/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36',
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

async def tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        bigpump_data = await fetch_bigpump_data()
        ton_price = await fetch_ton_price()
        tokens = bigpump_data.get("items", [])

        filtered_tokens = [
            token for token in tokens
            if token.get("marketCap") and (float(token["marketCap"]) / 10**9 * ton_price) >= 11000
        ][:15]

        result = []
        for idx, token in enumerate(filtered_tokens, start=1):
            name = token.get("name", "N/A")
            symbol = token.get("symbol", "N/A")
            mcap_value = token.get("marketCap")
            growth = token.get("priceChange1H", "N/A")
            address = token.get("address", None)

            if mcap_value:
                mcap = float(mcap_value) / 10**9 * ton_price
                mcap_str = f"${mcap/1000:.1f}K"
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

            line = f"{idx}. {clickable_name} | {mcap_str} | {growth_str}\n"
            result.append(line)

        final_text = "\n".join(result)
        await update.message.reply_text(final_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Ошибка при получении токенов: {e}")
        await update.message.reply_text("Произошла ошибка при получении токенов.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("tokens", tokens_command))
    print("Бот запущен...")
    app.run_polling()
