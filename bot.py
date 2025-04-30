import logging
import os
import aiohttp
import base64
import crcmod
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
latest_tokens_result = None

def address_to_base64url(address: str) -> str:
    address = address.strip()
    if ':' in address:
        wc_str, hex_addr = address.split(':')
        wc = int(wc_str)
        addr_bytes = bytes.fromhex(hex_addr)
    else:
        wc = 0
        addr_bytes = bytes.fromhex(address)

    tag = 0x11
    wc_byte = wc.to_bytes(1, byteorder="big", signed=True)
    data = bytes([tag]) + wc_byte + addr_bytes

    crc16 = crcmod.predefined.mkPredefinedCrcFun('crc-ccitt-false')
    checksum = crc16(data).to_bytes(2, 'big')
    full = data + checksum
    return base64.urlsafe_b64encode(full).decode()

async def get_ton_price():
    url = 'https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd&include_24hr_change=true'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data["the-open-network"]["usd"])
                    change = float(data["the-open-network"].get("usd_24h_change", 0))
                    return price, change
    except Exception as e:
        logger.warning(f"Не удалось получить цену TON: {e}")
    return None, 0

async def get_tokens():
    bigpump_url = 'https://prod-api.bigpump.app/api/v1/coins?sortType=pocketfi&limit=30'
    dyor_url = 'https://api.dyor.io/v1/jettons?sort=createdAt&order=desc&limit=200&excludeScam=true'
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
            async with session.get(bigpump_url, headers=headers) as bp_resp:
                if bp_resp.status != 200:
                    logger.warning(f"BigPump API error: {bp_resp.status}")
                    return "BigPump API не отвечает"

                bp_data = await bp_resp.json()
                bp_tokens = bp_data.get("coins", [])

            async with session.get(dyor_url) as dyor_resp:
                if dyor_resp.status != 200:
                    logger.warning(f"DYOR API error: {dyor_resp.status}")
                    return "DYOR API не отвечает"

                dyor_data = await dyor_resp.json()
                dyor_tokens = dyor_data.get("jettons", [])

        symbol_to_address = {
            j["metadata"]["symbol"].strip(): j["metadata"]["address"]
            for j in dyor_tokens
            if j.get("metadata", {}).get("symbol") and j["metadata"].get("address")
        }

        ton_usd_price, _ = await get_ton_price()
        result = []
        filtered = []
        for token in bp_tokens:
            try:
                cap = float(token.get("marketCap", 0)) * ton_usd_price / 1e9
                if cap >= 11000:
                    filtered.append((token, cap))
            except:
                continue

        for idx, (token, cap) in enumerate(filtered[:15], 1):
            name = token.get('name', 'N/A')
            symbol = token.get('symbol', 'N/A')
            change = token.get('priceChange1H')
            address = symbol_to_address.get(symbol)

            mcap = f"<b>${cap/1000:.1f}K</b>" if cap >= 1_000 else f"<b>${cap:.2f}</b>"

            if address:
                encoded = address_to_base64url(address)
                link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{encoded}"
                name_symbol = f'<a href="{link}">{name} ({symbol})</a>'
            else:
                name_symbol = f'{name} ({symbol})'

            try:
                growth = float(change)
                emoji = (
                    "💎" if growth >= 100 else
                    "🤑" if growth >= 50 else
                    "💸" if growth >= 25 else
                    "💪" if growth >= 10 else
                    "🙃" if growth >= 5 else
                    "🥹" if growth > 0 else
                    "🥲" if growth > -10 else
                    "😭" if growth > -25 else "🤡"
                )
                growth_str = f"{emoji} {growth:.2f}%"
            except:
                growth_str = "N/A"

            result.append(f"{idx}. {name_symbol} | {mcap} | {growth_str}")

        return "\n\n".join(result) if result else "Нет подходящих токенов"

    except Exception as e:
        logger.exception("Ошибка при обращении к API")
        return f"Ошибка при запросе: {str(e)}"

async def listings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_tokens_result
    result = await get_tokens()
    if result:
        latest_tokens_result = result
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")]
        ])
        await update.message.reply_text(result, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=keyboard)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_tokens_result
    query = update.callback_query
    await query.answer()
    result = await get_tokens()
    if result and result != latest_tokens_result:
        latest_tokens_result = result
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")]
        ])
        try:
            await query.edit_message_text(text=result, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=keyboard)
        except Exception as e:
            logger.warning(f"Не удалось обновить сообщение: {e}")

async def tonprice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price, change = await get_ton_price()
    if price is not None:
        if change >= 5:
            emoji = "🚀"
        elif change >= 1:
            emoji = "📈"
        elif change > 0:
            emoji = "🔼"
        elif change > -1:
            emoji = "🔽"
        elif change > -5:
            emoji = "📉"
        else:
            emoji = "💥"

        message = (
            f"{emoji} <b>TON:</b> ${price:.4f} ({change:+.2f}%)\n"
            f'<a href="https://www.coingecko.com/en/coins/the-open-network">🌐 Смотреть на CoinGecko</a>'
        )
    else:
        message = "Не удалось получить цену TON 😕"

    await update.message.reply_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=False)

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("listings", listings_command))
    app.add_handler(CommandHandler("tonprice", tonprice_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("Бот запущен...")
    app.run_polling()
