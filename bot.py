import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

bot = Bot(TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🚌 Assalomu alaykum!\n\n"
        "🚇 Toshkent Transport AI botiga xush kelibsiz.\n\n"
        "Quyidagilardan birini tanlang:\n"
        "🚌 Avtobuslar\n"
        "🚇 Metro\n"
        "📍 Yaqin bekatlar\n"
        "🗺️ Qayerga boraman?\n"
        "🤖 AI yordamchi"
    )


@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📚 Yordam\n\n"
        "/start — Botni ishga tushirish\n"
        "/buses — Avtobuslar\n"
        "/metro — Metro\n"
        "/nearby — Yaqin bekatlar\n"
        "/route — Yo'nalish topish"
    )


@dp.message(Command("buses"))
async def buses(message: types.Message):
    await message.answer(
        "🚌 Toshkent avtobuslari\n\n"
        "Hozircha transport ma'lumotlar bazasi ulanmoqda.\n"
        "Keyingi bosqichda real yo'nalishlar va bekatlar qo'shiladi."
    )


@dp.message(Command("metro"))
async def metro(message: types.Message):
    await message.answer(
        "🚇 Toshkent metropoliteni\n\n"
        "Metro yo'nalishlari va bekatlari keyingi bosqichda qo'shiladi."
    )


@dp.message(Command("nearby"))
async def nearby(message: types.Message):
    await message.answer(
        "📍 Yaqin bekatlarni topish funksiyasi tayyorlanmoqda."
    )


@dp.message(Command("route"))
async def route(message: types.Message):
    await message.answer(
        "🗺️ Qayerdan → qayerga borishingizni yozing.\n\n"
        "Masalan:\n"
        "Yunusoboddan Chilonzorga qanday boraman?"
    )


@dp.message()
async def other_messages(message: types.Message):
    await message.answer(
        "🤖 Men Toshkent transport yordamchisiman.\n\n"
        "Savolingizni yozing yoki /start ni bosing."
    )


async def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN topilmadi")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
