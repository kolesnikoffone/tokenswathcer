import logging
import os
import aiohttp
from pytoniq_core import Address
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
TOKENS_PER_PAGE = 10

def address_to_base64url(address: str) -> str:
    return Address(address).to_str(
        is_user_friendly=True,
        is_bounceable=True,
        is_test_only=False,
        is_url_safe=True
    )

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
    url = 'https://prod-api.bigpump.app/api/v1/coins?sortType=pocketfi&limit=40'
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
                    ton_usd_price, _ = await get_ton_price()
                    result = []

                    for token in tokens:
                        try:
                            cap = float(token.get("marketCap", 0)) * ton_usd_price / 1e9
                            if cap >= 11000:
                                result.append((token, cap))
                        except:
                            continue

                    return result[:20]
                else:
                    return []
    except Exception as e:
        logger.exception("Ошибка при обращении к BigPump API")
        return []

def format_tokens_page(tokens_data, page):
    result = []
    page_tokens = tokens_data[page*TOKENS_PER_PAGE:(page+1)*TOKENS_PER_PAGE]

    for idx, (token, cap) in enumerate(page_tokens, 1 + page * TOKENS_PER_PAGE):
        name = token.get('name', 'N/A')
        symbol = token.get('symbol', 'N/A')
        address = token.get('address')
        change = token.get('priceChange1H')

        mcap = f"<b>${cap/1000:.1f}K</b>" if cap >= 1_000 else f"<b>${cap:.2f}</b>"

        if address:
            try:
                encoded_address = address_to_base64url(address)
                link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{encoded_address}"
                name_symbol = f'<a href="{link}">{name} ({symbol})</a>'
            except Exception as e:
                logger.warning(f"Ошибка при конвертации адреса: {e}")
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

    return "\n\n".join(result)

def build_keyboard(current_page, total_pages):
    buttons = []
    if current_page > 0:
        buttons.append(InlineKeyboardButton("⏪", callback_data=f"page_{current_page - 1}"))
    buttons.append(InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{current_page}"))
    if current_page < total_pages - 1:
        buttons.append(InlineKeyboardButton("⏩", callback_data=f"page_{current_page + 1}"))
    return InlineKeyboardMarkup([buttons])

async def listings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tokens_data = await get_tokens()
    if not tokens_data:
        await update.message.reply_text("Нет подходящих токенов")
        return
    total_pages = (len(tokens_data) + TOKENS_PER_PAGE - 1) // TOKENS_PER_PAGE
    text = format_tokens_page(tokens_data, 0)
    keyboard = build_keyboard(0, total_pages)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=keyboard)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("refresh_") or data.startswith("page_"):
        try:
            page = int(data.split("_")[1])
        except:
            page = 0
        tokens_data = await get_tokens()
        if not tokens_data:
            await query.edit_message_text("Нет подходящих токенов")
            return
        total_pages = (len(tokens_data) + TOKENS_PER_PAGE - 1) // TOKENS_PER_PAGE
        page = max(0, min(page, total_pages - 1))
        text = format_tokens_page(tokens_data, page)
        keyboard = build_keyboard(page, total_pages)
        try:
            await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=keyboard)
        except Exception as e:
            logger.warning(f"Не удалось обновить сообщение: {e}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("listings", listings_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("Бот запущен...")
    app.run_polling()
