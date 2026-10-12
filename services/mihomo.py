import random

import aiohttp

from config import MIHOMO_API, MIHOMO_GROUP, MIHOMO_SECRET
from logger import setup_logging

log = setup_logging("mihomo")


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if MIHOMO_SECRET:
        h["Authorization"] = f"Bearer {MIHOMO_SECRET}"
    return h


async def list_nodes() -> list[str]:
    """Получить все имена узлов в策略组 (без DIRECT/REJECT и рекламных)."""
    if not MIHOMO_API:
        return []
    url = f"{MIHOMO_API}/proxies/{MIHOMO_GROUP}"
    async with (
        aiohttp.ClientSession() as s,
        s.get(url, headers=_headers(), timeout=aiohttp.ClientTimeout(total=5)) as r,
    ):
        if r.status != 200:
            log.warning("mihomo list_nodes failed: %s", r.status)
            return []
        data = await r.json()

    skip = {"DIRECT", "REJECT", "GLOBAL", "COMPATIBLE"}
    bad_kw = ("остаток", "осталось", "до ", "трафик", "到期", "剩余", "官网", "流量")
    return [
        n
        for n in (data.get("all") or [])
        if n not in skip and not any(kw in n.lower() for kw in bad_kw)
    ]


async def switch_node(name: str) -> bool:
    if not MIHOMO_API:
        return False
    url = f"{MIHOMO_API}/proxies/{MIHOMO_GROUP}"
    async with (
        aiohttp.ClientSession() as s,
        s.put(
            url,
            headers=_headers(),
            json={"name": name},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as r,
    ):
        ok = r.status in (200, 204)
        if not ok:
            log.warning("mihomo switch_node %s failed: %s", name, r.status)
        return ok


async def rotate() -> str | None:
    nodes = await list_nodes()
    if not nodes:
        return None
    pick = random.choice(nodes)
    if await switch_node(pick):
        log.info("mihomo rotated to: %s", pick)
        return pick
    return None
