import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from config import MAX_CONCURRENT_DOWNLOADS
from logger import setup_logging
from services import cookies as cookies_svc
from services import modes
from services.downloader import DownloadError, download

log = setup_logging("queue")


@dataclass
class Job:
    chat_id: int
    user_id: int
    url: str
    start_index: int
    out_dir: Path
    mode: str
    user_cookies: str | None
    notifier: Callable[[int, str], Awaitable[None]]


class DownloadQueue:
    def __init__(self, workers: int = MAX_CONCURRENT_DOWNLOADS):
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.workers = workers
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        for i in range(self.workers):
            self._tasks.append(asyncio.create_task(self._worker(i), name=f"dl-{i}"))
        log.info("DownloadQueue started with %d workers", self.workers)

    async def stop(self):
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def submit(self, job: Job):
        await self.queue.put(job)
        log.info(
            "Job queued: user=%d url=%s start=%d mode=%s chat=%d size=%d",
            job.user_id,
            job.url,
            job.start_index,
            job.mode,
            job.chat_id,
            self.queue.qsize(),
        )

    async def _worker(self, wid: int):
        while True:
            job = await self.queue.get()
            try:
                await self._run_job(wid, job)
            finally:
                self.queue.task_done()

    async def _run_job(self, wid: int, job: Job):
        """
        Выполняет задачу. При 403 один раз меняет режим и пробует ещё раз.
        На втором круге 403 — сдаётся и сообщает юзеру.
        """
        attempt = 0
        max_attempts = 2  # первый + один после смены режима

        while attempt < max_attempts:
            attempt += 1
            log.info(
                "Worker %d attempt %d/%d user=%d url=%s mode=%s",
                wid,
                attempt,
                max_attempts,
                job.user_id,
                job.url,
                job.mode,
            )
            await job.notifier(job.chat_id, "▶️ Начинаю скачивание…")

            try:
                await download(
                    url=job.url,
                    start_index=job.start_index,
                    out_dir=job.out_dir,
                    mode=job.mode,
                    user_cookies=job.user_cookies,
                )
                await job.notifier(job.chat_id, "✅ Готово.")
                return

            except DownloadError as e:
                log.warning(
                    "job failed user=%d mode=%s 403=%s: %s",
                    job.user_id,
                    job.mode,
                    e.is_403,
                    e,
                )
                if not e.is_403:
                    await job.notifier(job.chat_id, f"❌ Ошибка: {e}")
                    return

                # 403: меняем режим, если есть куда
                changed = await self._downgrade_mode(job)
                if not changed:
                    await job.notifier(
                        job.chat_id,
                        "❌ Поймал 403 в прямом режиме. Дальше переключаться некуда.",
                    )
                    return

                if attempt >= max_attempts:
                    await job.notifier(
                        job.chat_id,
                        f"❌ Снова 403 в режиме {job.mode}. Останавливаюсь, "
                        f"перепробовал все режимы.",
                    )
                    return
                # иначе — цикл повторится с новым режимом

            except Exception as e:
                log.exception("Worker %d unexpected failure", wid)
                await job.notifier(job.chat_id, f"❌ Ошибка: {e}")
                return

    async def _downgrade_mode(self, job: Job) -> bool:
        """
        Понижает режим при 403. Возвращает True, если режим изменился
        (значит, есть смысл пробовать снова), False — если ниже некуда.
        """
        old = job.mode

        if old == "personal":
            cookies_svc.reset_user_cookies(job.user_id)
            job.mode = "mihomo"
            job.user_cookies = None
            modes.set_mode(job.user_id, "mihomo")
            await job.notifier(
                job.chat_id,
                "⚠️ Поймал 403 с твоими куками. Сбросил их, перехожу на mihomo…",
            )
        elif old == "mihomo":
            job.mode = "direct"
            job.user_cookies = None
            modes.set_mode(job.user_id, "direct")
            await job.notifier(
                job.chat_id,
                "⚠️ Поймал 403 через mihomo. Перехожу на прямое подключение…",
            )
        else:
            return False

        log.info("user %d mode downgraded: %s -> %s", job.user_id, old, job.mode)
        return True
