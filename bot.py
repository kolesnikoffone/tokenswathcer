import asyncio
import logging
import os
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Укажи переменную окружения или вставь напрямую

API_URL = "https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all"
HEADERS = {
    "accept": "application/json",
    "authorization": f"Bearer {os.getenv('BLUM_BEARER_TOKEN')}",
    "lang": "ru",
}

dp = Dispatcher()

@dp.message(Command("hots"))
async def get_hot_list(message: Message):
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(API_URL, headers=HEADERS)
            r.raise_for_status()
            data = r.json()

            sorted_jettons = sorted(
                data.get("jettons", []),
                key=lambda j: float(j["stats"].get("marketCap", 0)),
                reverse=True
            )[:10]

            result_lines = []
            for i, jetton in enumerate(sorted_jettons, start=1):
                ticker = jetton.get("ticker", "?")
                market_cap = float(jetton["stats"].get("marketCap", 0))
                market_cap_str = f"${market_cap/1e6:.1f}M" if market_cap > 1e6 else f"${market_cap:,.0f}"
                result_lines.append(f"{i}. {ticker} | {market_cap_str}")

            result_text = "\n".join(result_lines)
            result_text += f"\n\nОбновлено: {message.date.strftime('%d.%m.%Y %H:%M:%S')} (UTC+3)"
            await message.answer(result_text)

        except Exception as e:
            logging.exception("Ошибка при получении hot list")
            await message.answer("⚠️ Ошибка при получении данных")


async def main():
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
