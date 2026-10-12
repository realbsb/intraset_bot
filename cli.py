import argparse
import asyncio
import sys
from pathlib import Path

from services.downloader import (
    DownloadError,
    is_playlist,
    probe_playlist,
    validate_proxy,
)
from services.downloader import download as dl_download


def parse_args():
    p = argparse.ArgumentParser(description="Прямое скачивание YouTube через yt-dlp")
    p.add_argument("url")
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--proxy", default=None)
    p.add_argument("--cookies", default=None, help="Путь к своему cookies.txt")
    p.add_argument("--no-proxy", action="store_true")
    p.add_argument("--out", default=None)
    return p.parse_args()


async def amain() -> int:
    args = parse_args()

    if args.proxy and not validate_proxy(args.proxy):
        print("Некорректный формат прокси", file=sys.stderr)
        return 2

    out_dir = Path(args.out) if args.out else None

    if await is_playlist(args.url):
        try:
            info = await probe_playlist(
                args.url,
                proxy=args.proxy,
                cookies=args.cookies,
            )
            print(f"Плейлист: {info['title']}, видео: {info['count']}")
        except DownloadError as e:
            print(f"Не удалось получить инфо: {e}", file=sys.stderr)

    # CLI всегда ходит как direct или через user_proxy — без mihomo-ротации,
    # потому что это осознанный ручной запуск.
    try:
        await dl_download(
            args.url,
            start_index=args.start,
            out_dir=out_dir,
            mode="direct",
            user_cookies=args.cookies,
            user_proxy=args.proxy,
        )
    except DownloadError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
    print("Готово.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
