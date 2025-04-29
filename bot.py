import logging
import os
import aiohttp
import base64
import crcmod
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, Application

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

REFERRAL_PREFIX = "prghZZEt-"
chat_id_for_auto_update = None

def address_to_base64url(address: str) -> str:
    address = address.strip()
    if ':' in address:
        wc, hex_addr = address.split(':')
        wc = int(wc)
        hex_addr = bytes.fromhex(hex_addr)
    else:
        wc = 0
        hex_addr = bytes.fromhex(address)

    tag = 0x11
    workchain_byte = wc.to_bytes(1, byteorder="big", signed=True)
    data = bytes([tag]) + workchain_byte + hex_addr

    crc16 = crcmod.predefined.mkPredefinedCrcFun('crc-ccitt-false')
    checksum = crc16(data).to_bytes(2, 'big')

    full_data = data + checksum
    return base64.urlsafe_b64encode(full_data).rstrip(b'=').decode()

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
        'accept-language': 'en-US,en;q=0.9,ru-RU;q=0.8,ru;q=0.7,tr-TR;q=0.6,tr;q=0.5',
        'authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJhZGRyZXNzIjoiMDpmNWI5...'}  # Тут подставь свой токен правильно, укорочен
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
                        address = token.get('masterAddress') or token.get('address')
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
                                emoji = "🫩"
                            elif growth > -10:
                                emoji = "🫢"
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
    global chat_id_for_auto_update
    chat_id_for_auto_update = update.effective_chat.id
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

async def auto_update(app: Application):
    global chat_id_for_auto_update
    while True:
        if chat_id_for_auto_update:
            tokens = await get_tokens()
            if tokens:
                await app.bot.send_message(chat_id=chat_id_for_auto_update, text=tokens[0], parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data='refresh')]]))
        await asyncio.sleep(3600)

async def on_startup(app: Application):
    app.create_task(auto_update(app))

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()

    app.add_handler(CommandHandler("tokens", tokens_command))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern="refresh"))

    print("Бот запущен...")
    app.run_polling()
