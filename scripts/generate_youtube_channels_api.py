import json
import os
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
KST = timezone(timedelta(hours=9))

SRC_FILE = Path("scripts/youtube_sources.json")
OUT_FILE = Path("docs/youtube_channels.json")

def extract_handle(url: str) -> str:
    if not url:
        return ""
    if "/@" not in url:
        return ""
    return url.split("/@")[1].split("/")[0].strip()

def extract_channel_id(url: str) -> str:
    # https://www.youtube.com/channel/UCxxxx
    if not url:
        return ""
    try:
        parts = url.split("/")
        for i in range(len(parts) - 1):
            if parts[i] == "channel":
                cid = parts[i + 1].strip()
                if cid.startswith("UC"):
                    return cid
    except Exception:
        pass
    return ""

def fetch_channel_by_id(channel_id: str):
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "snippet,statistics", "id": channel_id, "key": API_KEY},
        timeout=20
    ).json()
    items = r.get("items", [])
    return items[0] if items else None

def fetch_channel_by_handle(handle: str):
    # forHandle 우선
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "snippet,statistics", "forHandle": handle, "key": API_KEY},
        timeout=20
    ).json()
    items = r.get("items", [])
    return items[0] if items else None

def pick_avatar(snippet: dict) -> str:
    thumbs = (snippet or {}).get("thumbnails", {}) or {}
    for k in ("high", "medium", "default"):
        u = (thumbs.get(k) or {}).get("url")
        if u:
            return u
    return ""

def parse_channel(item: dict, url: str) -> dict:
    snippet = item.get("snippet", {}) or {}
    stats = item.get("statistics", {}) or {}

    title = snippet.get("title", "") or url
    desc = snippet.get("description", "") or ""
    avatar = pick_avatar(snippet)

    subs = 0
    try:
        subs = int(stats.get("subscriberCount", "0") or "0")
    except Exception:
        subs = 0

    return {
        "enabled": True,
        "url": url,
        "channelId": item.get("id"),
        "title": title,
        "description": desc,
        "avatarUrl": avatar,
        "subscriberCount": subs
    }

def main():
    if not API_KEY:
        raise RuntimeError("❌ YOUTUBE_API_KEY가 비어있습니다. GitHub Secrets에 등록하세요.")

    if not SRC_FILE.exists():
        raise RuntimeError(f"❌ {SRC_FILE} 파일이 없습니다.")

    src = json.loads(SRC_FILE.read_text(encoding="utf-8"))

    out = {
        "generatedAt": datetime.now(KST).isoformat(),
        "categories": []
    }

    cats = src.get("categories", []) or []
    for cat in cats:
        name = (cat.get("name") or "").strip()
        if not name:
            continue

        channels = cat.get("channels", []) or []
        out_channels = []

        for ch in channels:
            if not (ch.get("enabled", True)):
                continue

            url = (ch.get("url") or "").strip()
            if not url:
                continue

            cid = extract_channel_id(url)
            handle = extract_handle(url)

            item = None
            if cid:
                item = fetch_channel_by_id(cid)
            if item is None and handle:
                item = fetch_channel_by_handle(handle)

            if item is None:
                # 최소한 url은 남기되, 카드가 너무 비어 보이니 title=url로
                out_channels.append({
                    "enabled": True,
                    "url": url,
                    "channelId": cid or None,
                    "title": url,
                    "description": "",
                    "avatarUrl": None,
                    "subscriberCount": 0
                })
                continue

            out_channels.append(parse_channel(item, url))

        if out_channels:
            out["categories"].append({
                "name": name,
                "channels": out_channels
            })

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("✅ youtube_channels.json generated:", sum(len(c["channels"]) for c in out["categories"]))

if __name__ == "__main__":
    main()
