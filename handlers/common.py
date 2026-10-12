from aiogram import Router
from aiogram.filters import Command

router = Router()


@router.message(Command("start"))
async def cmd_start(m):
    await m.answer(
        "Кидай ссылку на YouTube-видео или плейлист — скачаю в самом низком качестве.\n"
        "Для плейлиста спрошу номер стартового видео."
    )


@router.message(Command("help"))
async def cmd_help(m):
    await m.answer(
        "Команды:\n"
        "/start — приветствие\n"
        "/help — эта справка\n"
        "/dl <url> [--start N] [--proxy P] [--cookies F] [--no-proxy] — прямой запуск (только админ)\n\n"
        "Также можно просто прислать ссылку."
    )
