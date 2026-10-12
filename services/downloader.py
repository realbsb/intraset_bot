import asyncio
import json
import re
import time
from pathlib import Path

from config import (
    COOKIES_MAX_AGE_HOURS,
    COOKIES_PATH,
    DOWNLOAD_DIR,
    MIHOMO_PROXY,
    MIHOMO_ROTATE,
    YTDLP_PATH,
)
from logger import setup_logging
from services import mihomo

log = setup_logging("downloader")

PROXY_RE = re.compile(
    r"^(socks5h?|https?|http)://"
    r"([^:@/\s]+:[^@/\s]+@)?"
    r"[A-Za-z0-9.\-_]+"
    r"(:\d{1,5})?$"
)


class DownloadError(Exception):
    """Ошибка скачивания. is_403=True, если последняя причина — HTTP 403."""

    def __init__(self, msg: str, is_403: bool = False):
        super().__init__(msg)
        self.is_403 = is_403


def validate_proxy(p: str) -> bool:
    return bool(PROXY_RE.match(p.strip()))


def mask_proxy(p: str | None) -> str:
    if not p:
        return "direct"
    return re.sub(r"://([^:@/]+):([^@/]+)@", r"://***:***@", p)


def cookies_fresh(path: str) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    age_h = (time.time() - p.stat().st_mtime) / 3600
    return age_h < COOKIES_MAX_AGE_HOURS


def _is_403(stderr: str) -> bool:
    s = stderr.lower()
    return "http error 403" in s or "403 forbidden" in s


def _build_cmd(
    url: str,
    out_dir: Path,
    start_index: int,
    proxy: str | None,
    cookies: str,
) -> list[str]:
    cmd = [
        YTDLP_PATH,
        "--playlist-start",
        str(start_index),
        "--ignore-errors",
        "--sleep-interval",
        "7",
        "--max-sleep-interval",
        "45",
        "--js-runtimes",
        "node",
        "--remote-components",
        "ejs:github",
        "--cookies",
        cookies,
        "--format",
        "worstvideo+worstaudio/worst",
        "--merge-output-format",
        "mp4",
        "--output",
        str(out_dir / "%(playlist_index)s - %(title)s.%(ext)s"),
        "--no-progress",
        "--newline",
    ]
    if proxy:
        cmd += ["--proxy", proxy]
    cmd.append(url)
    return cmd


async def _run(cmd: list[str], proxy: str | None) -> tuple[int, str, str]:
    logged = " ".join(
        mask_proxy(a) if a.startswith(("socks", "http")) else a for a in cmd
    )
    log.info("yt-dlp start (proxy=%s): %s", mask_proxy(proxy), logged)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")


async def is_playlist(url: str) -> bool:
    return "list=" in url or "/playlist" in url


async def probe_playlist(
    url: str,
    proxy: str | None = None,
    cookies: str | None = None,
) -> dict:
    cookies_path = cookies or COOKIES_PATH
    cmd = [
        YTDLP_PATH,
        "--cookies",
        cookies_path,
        "--js-runtimes",
        "node",
        "--remote-components",
        "ejs:github",
        "--flat-playlist",
        "--dump-single-json",
    ]
    if proxy:
        cmd += ["--proxy", proxy]
    cmd.append(url)

    rc, _, err = await _run(cmd, proxy)
    if rc != 0:
        raise DownloadError(f"probe failed: {err.strip()[:500]}", is_403=_is_403(err))

    # отдельно перезапускаем без proxy-маски, чтобы получить чистый stdout
    cmd_data = [
        YTDLP_PATH,
        "--cookies",
        cookies_path,
        "--js-runtimes",
        "node",
        "--remote-components",
        "ejs:github",
        "--flat-playlist",
        "--dump-single-json",
    ]
    if proxy:
        cmd_data += ["--proxy", proxy]
    cmd_data.append(url)

    proc = await asyncio.create_subprocess_exec(
        *cmd_data,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise DownloadError(
            f"probe failed: {err.decode(errors='replace').strip()[:500]}",
            is_403=_is_403(err.decode(errors="replace")),
        )

    data = json.loads(out.decode(errors="replace"))
    return {
        "title": data.get("title", "Без названия"),
        "count": len(data.get("entries") or []),
        "url": url,
    }


async def download(
    url: str,
    start_index: int = 1,
    out_dir: Path | None = None,
    mode: str = "direct",
    user_cookies: str | None = None,
    user_proxy: str | None = None,
) -> Path:
    """
    mode:
      - "direct"   : прямое подключение, дефолтные куки
      - "mihomo"   : через mihomo, дефолтные куки
      - "personal" : персональные куки (user_cookies обязателен), через mihomo

    user_proxy (только CLI/админ): если задан — единственная попытка
    через этот прокси, без ротации и без fallback.
    """
    out_dir = Path(out_dir or DOWNLOAD_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    if user_proxy and not validate_proxy(user_proxy):
        raise ValueError("Некорректный формат прокси")

    if mode == "personal":
        if not user_cookies:
            raise DownloadError("personal mode без файла куки")
        cookies_path = user_cookies
    else:
        cookies_path = COOKIES_PATH

    if not Path(cookies_path).exists():
        raise DownloadError(f"Файл куки не найден: {cookies_path}")
    if not cookies_fresh(cookies_path):
        log.warning(
            "cookies file is older than %dh: %s",
            COOKIES_MAX_AGE_HOURS,
            cookies_path,
        )

    if user_proxy:
        attempts: list[str | None] = [user_proxy]
    elif mode == "direct":
        attempts = [None]
    elif mode in ("mihomo", "personal"):
        attempts = [MIHOMO_PROXY] if MIHOMO_PROXY else [None]
    else:
        raise ValueError(f"Неизвестный режим: {mode}")

    if not user_proxy and MIHOMO_PROXY and MIHOMO_ROTATE:
        chosen = await mihomo.rotate()
        if chosen:
            log.info("mihomo picked node: %s", chosen)

    last_err = ""
    for i, proxy in enumerate(attempts, 1):
        cmd = _build_cmd(url, out_dir, start_index, proxy, cookies_path)
        rc, _, err = await _run(cmd, proxy)

        if rc == 0:
            log.info(
                "yt-dlp OK (attempt %d/%d, proxy=%s, mode=%s)",
                i,
                len(attempts),
                mask_proxy(proxy),
                mode,
            )
            return out_dir

        last_err = err
        log.warning(
            "yt-dlp FAILED (attempt %d/%d, proxy=%s, rc=%d): %s",
            i,
            len(attempts),
            mask_proxy(proxy),
            rc,
            err.strip()[:400],
        )
        break

    raise DownloadError(
        f"Скачивание не удалось. Последняя ошибка: {last_err.strip()[:500]}",
        is_403=_is_403(last_err),
    )
