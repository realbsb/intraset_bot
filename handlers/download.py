from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from config import ADMIN_IDS, DOWNLOAD_DIR
from logger import setup_logging
from services import cookies as cookies_svc
from services import modes
from services.downloader import (
    DownloadError,
    is_playlist,
    probe_playlist,
    validate_proxy,
)
from services.queue import Job

log = setup_logging("handler.download")
router = Router()

_queue = None
_notify = None


def bind_queue(q):
    global _queue
    _queue = q


def bind_notifier(fn):
    global _notify
    _notify = fn


class S(StatesGroup):
    waiting_start_index = State()


def _job_for(
    m: Message,
    url: str,
    start: int,
    user_proxy: str | None = None,
    force_cookies: str | None = None,
) -> Job:
    personal = cookies_svc.get_user_cookies(m.from_user.id)
    if personal:
        mode = "personal"
        cookies_path = str(personal)
    else:
        mode = modes.get_mode(m.from_user.id)
        cookies_path = None

    if user_proxy:
        mode = "direct"
    if force_cookies:
        cookies_path = force_cookies

    return Job(
        chat_id=m.chat.id,
        user_id=m.from_user.id,
        url=url,
        start_index=start,
        out_dir=DOWNLOAD_DIR,
        mode=mode,
        user_cookies=cookies_path,
        notifier=_notify,
    )


@router.message(F.document)
async def handle_cookies_upload(m: Message):
    doc = m.document
    name = (doc.file_name or "").lower()

    if not name.endswith(".txt"):
        await m.answer("Пришли .txt-файл в формате Netscape cookies.txt.")
        return

    tmp = Path("/tmp") / f"upload_{m.from_user.id}.txt"
    file = await m.bot.get_file(doc.file_id)
    await m.bot.download_file(file.file_path, destination=tmp)

    try:
        cookies_svc.validate_cookies_file(tmp)
    except cookies_svc.CookieValidationError as e:
        tmp.unlink(missing_ok=True)
        await m.answer(f"❌ Не принял: {e}")
        return

    dst = cookies_svc.save_user_cookies(m.from_user.id, tmp)
    tmp.unlink(missing_ok=True)

    modes.set_mode(m.from_user.id, "personal")
    await m.answer(
        f"✅ Куки приняты ({dst.stat().st_size} байт).\n"
        f"Режим: personal (свои куки + mihomo).\n"
        f"Если словим 403 — сброшу куки и перейду в mihomo.\n"
        f"Сбросить вручную: /resetcookies"
    )


@router.message(Command("resetcookies"))
async def cmd_resetcookies(m: Message):
    had = cookies_svc.get_user_cookies(m.from_user.id)
    if had:
        cookies_svc.reset_user_cookies(m.from_user.id)
        modes.set_mode(m.from_user.id, "direct")
        await m.answer("🧹 Персональные куки удалены. Режим: direct.")
    else:
        await m.answer("У тебя нет персональных куки. Режим: direct.")


@router.message(Command("dl"))
async def cmd_direct(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("Нет доступа.")
        return

    parts = (m.text or "").split()
    if len(parts) < 2:
        await m.answer(
            "Использование: /dl <url> "
            "[--start N] [--proxy P] [--cookies F] [--no-proxy]"
        )
        return

    url = parts[1]
    start, proxy, cookies, force_direct = 1, None, None, False
    i = 2
    while i < len(parts):
        if parts[i] == "--start" and i + 1 < len(parts):
            start = int(parts[i + 1])
            i += 2
        elif parts[i] == "--proxy" and i + 1 < len(parts):
            proxy = parts[i + 1]
            i += 2
        elif parts[i] == "--cookies" and i + 1 < len(parts):
            cookies = parts[i + 1]
            i += 2
        elif parts[i] == "--no-proxy":
            force_direct = True
            i += 1
        else:
            i += 1

    if proxy and not validate_proxy(proxy):
        await m.answer("Прокси не похож на валидный URL.")
        return

    job = _job_for(m, url, start, user_proxy=proxy, force_cookies=cookies)
    if force_direct:
        job.mode = "direct"
        job.user_cookies = None

    await _queue.submit(job)
    await m.answer("Задача в очереди.")


@router.message(F.text.contains("youtube.com") | F.text.contains("youtu.be"))
async def handle_url(m: Message, state: FSMContext):
    url = m.text.strip()

    if await is_playlist(url):
        personal = cookies_svc.get_user_cookies(m.from_user.id)
        try:
            info = await probe_playlist(
                url,
                cookies=str(personal) if personal else None,
            )
        except DownloadError as e:
            await m.answer(f"Не удалось получить данные плейлиста: {e}")
            return

        await state.update_data(url=url)
        await state.set_state(S.waiting_start_index)
        await m.answer(
            f"Плейлист «{info['title']}» — {info['count']} видео.\n"
            f"С какого номера начать? (например, 245)"
        )
    else:
        await _queue.submit(_job_for(m, url, 1))
        await m.answer("Задача в очереди.")


@router.message(S.waiting_start_index)
async def process_start_index(m: Message, state: FSMContext):
    data = await state.get_data()
    url = data.get("url")
    try:
        start = int(m.text.strip())
    except ValueError:
        await m.answer("Введи число.")
        return

    await _queue.submit(_job_for(m, url, start))
    await m.answer("Задача в очереди.")
    await state.clear()
