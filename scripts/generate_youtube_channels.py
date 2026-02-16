import json
import os
import time
import re
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
KST = timezone(timedelta(hours=9))

SRC_FILE = Path("scripts/youtube_channels_source.json")     # 입력(URL목록)
OUT_FILE = Path("docs/youtube_channels.json")               # 출력(완성본)

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"


def extract_channel_id(url: str) -> str:
    # https://www.youtube.com/channel/UCxxxx -> UCxxxx
    if not url:
        return ""
    m = re.search(r"/channel/(UC[a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else ""


def extract_handle(url: str) -> str:
    # https://www.youtube.com/@HEYNEE103 -> HEYNEE103
    if not url:
        return ""
    m = re.search(r"/@([^/?]+)", url)
    return m.group(1) if m else ""


def yt_get(path, params):
    r = requests.get(f"{YOUTUBE_API}/{path}", params=params, timeout=25)
    try:
        return r.json()
    except Exception:
        return {}


def channel_id_by_handle(handle: str) -> str:
    if not handle:
        return ""

    # 1) channels.list forHandle (가장 정확)
    data = yt_get("channels", {"part": "id", "forHandle": handle, "key": API_KEY})
    items = data.get("items", [])
    if items and items[0].get("id"):
        return items[0]["id"]

    # 2) fallback search(type=channel)
    data = yt_get("search", {
        "part": "snippet",
        "q": handle,
        "type": "channel",
        "maxResults": 1,
        "key": API_KEY
    })
    items = data.get("items", [])
    if not items:
        return ""
    return (items[0].get("id") or {}).get("channelId", "") or ""


def fetch_channels_by_ids(channel_ids):
    # channels.list는 최대 50개까지 한 번에 가능
    out = {}
    for i in range(0, len(channel_ids), 50):
        chunk = channel_ids[i:i+50]
        data = yt_get("channels", {
            "part": "snippet,statistics",
            "id": ",".join(chunk),
            "key": API_KEY
        })
        for it in data.get("items", []):
            cid = it.get("id")
            if cid:
                out[cid] = it
        time.sleep(0.2)
    return out


def safe_int(x):
    try:
        return int(x)
    except Exception:
        return 0


def main():
    if not API_KEY:
        raise RuntimeError("❌ YOUTUBE_API_KEY가 비어있습니다. GitHub Secrets에 등록하세요.")

    if not SRC_FILE.exists():
        raise RuntimeError(f"❌ 소스 파일이 없습니다: {SRC_FILE}")

    src = json.loads(SRC_FILE.read_text(encoding="utf-8"))

    cats = src.get("categories", [])
    if not isinstance(cats, list):
        raise RuntimeError("❌ source json 형식 오류: categories가 list가 아닙니다.")

    # 1) 모든 채널의 channelId를 최대한 확보
    all_ids = []
    resolved = {}  # url -> channelId
    for cat in cats:
        channels = cat.get("channels", []) or []
        for ch in channels:
            if not isinstance(ch, dict):
                continue
            if not ch.get("enabled", True):
                continue

            url = (ch.get("url") or "").strip()
            if not url:
                continue

            cid = (ch.get("channelId") or "").strip()
            if not cid:
                cid = extract_channel_id(url)

            if not cid:
                handle = extract_handle(url)
                # 한글 handle은 forHandle에서 실패할 수 있음 -> 가능하면 channelId를 source에 직접 넣는 걸 권장
                cid = channel_id_by_handle(handle)

            if cid:
                resolved[url] = cid
                all_ids.append(cid)
            else:
                resolved[url] = ""  # 못 찾음

            time.sleep(0.1)

    # 중복 제거
    all_ids = list(dict.fromkeys([x for x in all_ids if x]))

    # 2) channelId들로 채널 정보 일괄 조회
    info_map = fetch_channels_by_ids(all_ids)

    # 3) 출력 JSON 구성 (앱이 바로 그릴 수 있게 title/avatar/subs 포함)
    out = {
        "generatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "categories": []
    }

    for cat in cats:
        out_cat = {
            "key": (cat.get("key") or "").strip(),
            "name": (cat.get("name") or "").strip(),
            "channels": []
        }

        channels = cat.get("channels", []) or []
        for ch in channels:
            if not isinstance(ch, dict):
                continue

            url = (ch.get("url") or "").strip()
            enabled = bool(ch.get("enabled", True))

            if not url:
                continue

            cid = (ch.get("channelId") or "").strip() or resolved.get(url, "") or ""
            item = {
                "url": url,
                "enabled": enabled,
                "channelId": cid
            }

            # enabled=false는 그냥 목록 유지(필요하면 앱에서 숨김)
            if enabled and cid and cid in info_map:
                raw = info_map[cid]
                sn = raw.get("snippet", {}) or {}
                st = raw.get("statistics", {}) or {}

                thumbs = sn.get("thumbnails", {}) or {}
                avatar = ""
                for k in ("high", "medium", "default"):
                    if (thumbs.get(k) or {}).get("url"):
                        avatar = thumbs[k]["url"]
                        break

                item.update({
                    "title": sn.get("title", ""),
                    "description": sn.get("description", ""),
                    "avatarUrl": avatar,
                    "subscriberCount": safe_int(st.get("subscriberCount")),
                })
            else:
                # 못 찾았으면 최소한 URL만이라도 유지
                item.update({
                    "title": "",
                    "description": "",
                    "avatarUrl": "",
                    "subscriberCount": 0,
                })

            out_cat["channels"].append(item)

        out["categories"].append(out_cat)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ generated: {OUT_FILE} (categories={len(out['categories'])})")


if __name__ == "__main__":
    main()
