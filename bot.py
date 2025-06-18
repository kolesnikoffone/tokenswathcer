import logging
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.utils import executor

API_URL = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
BLUM_BEARER_TOKEN = "your_token_here"  # Замените на ваш актуальный токен

logging.basicConfig(level=logging.INFO)
bot = Bot(token="your_telegram_bot_token")
dp = Dispatcher(bot)

def format_number(n):
    try:
        n = float(n)
        if n >= 1e9:
            return f"{n / 1e9:.1f}B"
        elif n >= 1e6:
            return f"{n / 1e6:.1f}M"
        elif n >= 1e3:
            return f"{n / 1e3:.1f}K"
        else:
            return f"{n:.2f}"
    except Exception:
        return str(n)

@dp.message_handler(commands=["hots"])
async def send_hots(message: Message):
    headers = {
        "Authorization": f"Bearer {BLUM_BEARER_TOKEN}",
        "accept": "application/json"
    }
    try:
        response = requests.get(API_URL, headers=headers)
        response.raise_for_status()
        data = response.json()
        jettons = data.get("jettons", [])

        # Сортировка по капитализации (по убыванию)
        sorted_jettons = sorted(jettons, key=lambda j: float(j["stats"].get("marketCap", 0)), reverse=True)

        # Формируем текст
        lines = []
        for i, token in enumerate(sorted_jettons[:10], 1):
            ticker = token.get("ticker", "?")
            market_cap = token.get("stats", {}).get("marketCap", 0)
            formatted_cap = format_number(market_cap)
            lines.append(f"{i}. {ticker} | ${formatted_cap}")

        reply = "🔥 <b>Hot Jettons</b> 🔥\n\n" + "\n".join(lines)
        reply += f"\n\nОбновлено: <i>{message.date.strftime('%d.%m.%Y %H:%M:%S')}</i>"

        await message.answer(reply, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Failed to fetch hot jettons: {e}")
        await message.answer("Ошибка при получении списка hot токенов.")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
