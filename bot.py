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
TOKENS_PER_PAGE = 10
TOTAL_PAGES = 3


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


async def fetch_tokens():
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
                    return data.get('coins', [])
    except Exception as e:
        logger.exception("Ошибка при обращении к BigPump API")
    return []


def build_keyboard(page: int) -> InlineKeyboardMarkup:
    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("⏪ Назад", callback_data=f"page_{page - 1}"))
    buttons.append(InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{page}"))
    if page < TOTAL_PAGES:
        buttons.append(InlineKeyboardButton("⏩ Вперёд", callback_data=f"page_{page + 1}"))
    return InlineKeyboardMarkup([buttons])


async def generate_token_page(page: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    tokens = context.user_data.get("tokens")
    if not tokens:
        all_tokens = await fetch_tokens()
        ton_usd_price, _ = await get_ton_price()
        filtered = []
        for token in all_tokens:
            try:
                cap = float(token.get("marketCap", 0)) * ton_usd_price / 1e9
                if cap >= 11:
                    filtered.append((token, cap))
            except:
                continue
        context.user_data["tokens"] = filtered
        tokens = filtered

    start = (page - 1) * TOKENS_PER_PAGE
    end = start + TOKENS_PER_PAGE
    current_slice = tokens[start:end]

    if not current_slice:
        return "Нет подходящих токенов"

    result = [f"<i>Страница {page} из {TOTAL_PAGES}</i>\n"]
    for idx, (token, cap) in enumerate(current_slice, start + 1):
        name = token.get('name', 'N/A')
        symbol = token.get('symbol', 'N/A')
        address = token.get('address')
        change = token.get('priceChange1H')

        mcap = f"<b>${cap/1000:.1f}K</b>" if cap >= 1_000 else f"<b>${cap:.2f}</b>"
        name_symbol = f"{name} ({symbol})"

        if address:
            encoded = address_to_base64url(address)
            logger.info(f"Address conversion: {address} -> {encoded}")
            link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{encoded}"
            name_symbol = f'<a href="{link}">{name_symbol}</a>'

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
    page = 1
    context.user_data["page"] = page
    text = await generate_token_page(page, context)
    keyboard = build_keyboard(page)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=keyboard)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("page_"):
        page = int(data.split("_")[1])
    elif data.startswith("refresh_"):
        page = int(data.split("_")[1])
        context.user_data["tokens"] = None  # force refresh
    else:
        return

    context.user_data["page"] = page
    text = await generate_token_page(page, context)
    keyboard = build_keyboard(page)
    await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=keyboard)


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
