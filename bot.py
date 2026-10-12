import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from handlers import common, download
from logger import setup_logging
from services.queue import DownloadQueue

# from handlers import inline  # включим позже

log = setup_logging("bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
queue = DownloadQueue()


async def notify(chat_id: int, text: str):
    try:
        await bot.send_message(chat_id, text)
    except Exception: 
        log.exception("notify failed chat=%d", chat_id)


async def main():
    download.bind_queue(queue)
    download.bind_notifier(notify)

    dp.include_router(common.router)
    dp.include_router(download.router)
    # dp.include_router(inline.router)

    await queue.start()
    log.info("Bot starting…")
    try:
        await dp.start_polling(bot)
    finally:
        await queue.stop()


if __name__ == "__main__":
    asyncio.run(main())
