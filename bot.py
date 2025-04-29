import logging
import os
import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

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

# Функция запроса данных с BigPump
async def get_tokens():
    url = 'https://prod-api.bigpump.app/api/v1/coins?sortType=pocketfi&limit=10'
    headers = {
        'authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJhZGRyZXNzIjoiMDpmNWI5MWRkZDBiOWM4N2VmNjUwMTFhNzlmMWRhNzE5NzIwYzVhODgwN2I1NGMxYTQwNTIyNzRmYTllMzc5YmNkIiwibmV0d29yayI6Ii0yMzkiLCJpYXQiOjE3NDI4MDY4NTMsImV4cCI6MTc3NDM2NDQ1M30.U_GaaX5psI572w4YmwAjlh8u4uFBVHdsD-zJacvWiPo',
        'accept': '*/*',
        'origin': 'https://bigpump.app',
        'referer': 'https://bigpump.app/',
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                logger.info(f"BigPump API responded with status {response.status}")
                text = await response.text()
                logger.debug(f"Raw response: {text}")
                if response.status == 200:
                    data = await response.json()
                    tokens = data.get('coins', [])
                    result = []
                    for token in tokens:
                        logger.info(f"Parsed token: {token}")
                        name = token.get('name')
                        symbol = token.get('symbol')
                        address = token.get('address')
                        chain = 'TON'  # по умолчанию, так как поле отсутствует
                        if not all([name, symbol, address]):
                            result.append(f"⚠️ Неполные данные: {token}")
                        else:
                            result.append(f"{name} ({symbol})\nChain: {chain}\nAddress: {address}\n")
                    if not result:
                        result.append("Нет токенов в ответе от BigPump.")
                    return result
                else:
                    return [f"Ошибка {response.status}: {text}"]
    except Exception as e:
        logger.exception("Ошибка при обращении к BigPump API")
        return [f"Ошибка при запросе: {str(e)}"]

# Обработчик команды /tokens
async def tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Получаю токены с BigPump...")
    tokens = await get_tokens()
    for t in tokens:
        await update.message.reply_text(t)

# Основной запуск бота
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("tokens", tokens_command))

    print("Бот запущен...")
    app.run_polling()
