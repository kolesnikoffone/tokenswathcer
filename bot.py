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
tokens_data = []  # Кэш всех токенов


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
    global tokens_data
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

                    tokens_data = []
                    for token in tokens:
                        try:
                            cap = float(token.get("marketCap", 0)) * ton_usd_price / 1e9
                            if cap >= 11000:
                                tokens_data.append((token, cap))
                        except:
                            continue
                else:
                    tokens_data = []
    except Exception as e:
        logger.exception("Ошибка при обращении к BigPump API")
        tokens_data = []


def format_tokens_page(page: int) -> str:
    if not tokens_data:
        return "Нет подходящих токенов"

    start = page * 10
    end = start + 10
    result = []

    for idx, (token, cap) in enumerate(tokens_data[start:end], start + 1):
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
            except:
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

        result.append(f"{idx}. {name_symbol} | {mcap} | {growth_str}")

    return "\n\n".join(result)


async def listings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await get_tokens()
    context.user_data['page'] = 0
    text = format_tokens_page(0)
    keyboard = [[
        InlineKeyboardButton("⏪", callback_data="prev"),
        InlineKeyboardButton("🔄 Обновить", callback_data="refresh"),
        InlineKeyboardButton("⏩", callback_data="next")
    ]]
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(keyboard))


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    page = context.user_data.get('page', 0)

    if action == 'refresh':
        await get_tokens()
    elif action == 'next':
        page = min(page + 1, (len(tokens_data) - 1) // 10)
    elif action == 'prev':
        page = max(page - 1, 0)

    context.user_data['page'] = page
    text = format_tokens_page(page)
    keyboard = [[
        InlineKeyboardButton("⏪", callback_data="prev"),
        InlineKeyboardButton("🔄 Обновить", callback_data="refresh"),
        InlineKeyboardButton("⏩", callback_data="next")
    ]]
    try:
        await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение: {e}")


if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("listings", listings_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("Бот запущен...")
    app.run_polling()
