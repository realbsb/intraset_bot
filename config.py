import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

# --- 路径（宿主机视角已在 compose 里映射，容器内用这些路径）---
YTDLP_PATH = os.getenv("YTDLP_PATH", "/usr/local/bin/yt-dlp")
NODE_PATH = os.getenv("NODE_PATH", "/usr/bin/node")
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "/usr/bin/ffmpeg")
COOKIES_PATH = os.getenv("COOKIES_PATH", "/app/yt.txt")
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "/downloads"))
LOG_DIR = Path(os.getenv("LOG_DIR", "/app/logs"))

# --- mihomo ---
# 代理入口：混合端口（HTTP/SOCKS 都走这里）
MIHOMO_PROXY = os.getenv("MIHOMO_PROXY", "")  # 例: http://mihomo:7890
# API：用于轮换节点（External Controller）
MIHOMO_API = os.getenv("MIHOMO_API", "")  # 例: http://mihomo:9090
MIHOMO_SECRET = os.getenv("MIHOMO_SECRET", "")  # 如配置了 secret
MIHOMO_GROUP = os.getenv("MIHOMO_GROUP", "PROXY")  # 策略组名，默认 PROXY

# 轮换策略：rotate=每次任务前换节点；sticky=不主动换（mihomo 自己处理）
MIHOMO_ROTATE = os.getenv("MIHOMO_ROTATE", "rotate").lower() == "rotate"

MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2"))
COOKIES_MAX_AGE_HOURS = int(os.getenv("COOKIES_MAX_AGE_HOURS", "48"))
USER_COOKIES_DIR = Path(os.getenv("USER_COOKIES_DIR", "/app/user_cookies"))