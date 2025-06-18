import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.utils.markdown import hbold
import httpx
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

async def fetch_hot_jettons():
    url = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()["jettons"]

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(f"Привет, {hbold(message.from_user.full_name)}!\nОтправь команду /hot, чтобы увидеть горячие токены.")

@dp.message(commands=["hot"])
async def send_hot_jettons(message: Message):
    try:
        jettons = await fetch_hot_jettons()
        top = jettons[:10]
        msg = "🔥 Топ 10 HOT токенов:\n\n"
        for i, j in enumerate(top, 1):
            name = j.get("name", "")
            ticker = j.get("ticker", "")
            price = j.get("stats", {}).get("lastPrice", "0")
            volume = j.get("stats", {}).get("volume24h", "0")
            change = j.get("stats", {}).get("price24hChange", "0")
            msg += f"{i}. {hbold(name)} ({ticker})\n💰 Price: {price}\n📊 Volume 24h: {volume}\n📈 Change: {change}%\n\n"
        await message.answer(msg)
    except Exception as e:
        logging.error(f"Ошибка при получении данных: {e}")
        await message.answer("Произошла ошибка при получении данных. Попробуйте позже.")

async def main() -> None:
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
