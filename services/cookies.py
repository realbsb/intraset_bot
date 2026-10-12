import re
from pathlib import Path

from config import USER_COOKIES_DIR
from logger import setup_logging

log = setup_logging("cookies")

MAX_COOKIE_SIZE = 512 * 1024  # 512 КБ

# Netscape-формат: 7 полей через таб
NETSCAPE_LINE = re.compile(
    r"^[^\t#][^\t]*\t[^\t]*\t[^\t]*\t[^\t]*\t[^\t]*\t[^\t]*\t[^\t]+$"
)

# Сигнатуры, которых не должно быть в текстовом файле куки
BANNED_PREFIXES = (b"\x7fELF", b"MZ", b"#!", b"<?php", b"\x89PNG", b"\xff\xd8\xff")


class CookieValidationError(Exception):
    pass


def validate_cookies_file(path: Path) -> None:
    """Бросает CookieValidationError, если файл не похож на Netscape cookies.txt."""
    if not path.exists():
        raise CookieValidationError("Файл не найден.")
    if path.stat().st_size == 0:
        raise CookieValidationError("Файл пустой.")
    if path.stat().st_size > MAX_COOKIE_SIZE:
        raise CookieValidationError("Файл слишком большой (не похоже на cookies.txt).")

    raw = path.read_bytes()
    for sig in BANNED_PREFIXES:
        if raw.startswith(sig):
            raise CookieValidationError("Это не текстовый файл куки.")

    if b"\x00" in raw[:4096]:
        raise CookieValidationError("В файле есть нулевые байты — это не cookies.txt.")

    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as e:
        raise CookieValidationError(
            "Файл не в UTF-8 — скорее всего не cookies.txt."
        ) from e
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if not lines:
        raise CookieValidationError("Не нашёл ни одной строки куки.")

    netscape_lines = [ln for ln in lines if NETSCAPE_LINE.match(ln)]
    if len(netscape_lines) < 3:
        raise CookieValidationError(
            "Не похоже на Netscape cookies.txt (мало валидных строк)."
        )

    domains = " ".join(netscape_lines).lower()
    if ".youtube.com" not in domains and ".google.com" not in domains:
        raise CookieValidationError("В куках нет доменов youtube.com/google.com.")


def save_user_cookies(user_id: int, source: Path) -> Path:
    """Сохраняет куки юзера под его id. Файл уже должен быть скачан в source."""
    USER_COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    dst = USER_COOKIES_DIR / f"{user_id}.txt"
    dst.write_bytes(source.read_bytes())
    log.info("cookies saved for user %d (%d bytes)", user_id, dst.stat().st_size)
    return dst


def get_user_cookies(user_id: int) -> Path | None:
    p = USER_COOKIES_DIR / f"{user_id}.txt"
    return p if p.exists() else None


def reset_user_cookies(user_id: int) -> None:
    p = USER_COOKIES_DIR / f"{user_id}.txt"
    if p.exists():
        p.unlink()
        log.info("cookies reset for user %d", user_id)
