import logging
import os
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from ton.utils import address as ton_address

# Получаем токен из переменных окружения
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

REFERRAL_PREFIX = "prghZZEt-"

def address_to_base64url(raw: str) -> str:
    try:
        return ton_address.to_userfriendly(raw, bounceable=True, testnet=False, urlsafe=True)
    except Exception as e:
        logger.warning(f"Ошибка при кодировании адреса {raw}: {e}")
        return None

cached_result = None

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
    global cached_result
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

                    for idx, (token, cap) in enumerate(filtered[:15], 1):
                        name = token.get('name', 'N/A')
                        symbol = token.get('symbol', 'N/A')
                        address_raw = token.get('address')
                        change = token.get('priceChange1H')

                        mcap = f"<b>${cap/1000:.1f}K</b>" if cap >= 1_000 else f"<b>${cap:.2f}</b>"

                        if address_raw:
                            encoded = address_to_base64url(address_raw)
                            if encoded:
                                link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{encoded}"
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

                    cached_result = "\n\n".join(result)
                    return cached_result
                else:
                    return "Ошибка получения данных"
    except Exception as e:
        logger.exception("Ошибка при обращении к BigPump API")
        return "Ошибка при запросе"

async def listings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = cached_result or await get_tokens()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data="refresh")]])
    await update.message.reply_text(message_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=keyboard)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    new_data = await get_tokens()
    if new_data != query.message.text_html:
        await query.edit_message_text(new_data, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=query.message.reply_markup)

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("listings", listings_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Бот запущен...")
    app.run_polling()
