import json
import os
import re
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ======================
# 설정
# ======================
API_KEY = os.getenv("AIzaSyDHpNdYSA5RYpgZL1WqNiN02722uRBuDbA", "").strip()  # ✅ GitHub Secrets 권장
MAX_ITEMS_PER_CHANNEL = 1

KST = timezone(timedelta(hours=9))

SEARCH_CANDIDATES = 15          # 채널당 최신 후보 몇 개를 볼지
SHORTS_MAX_SECONDS = 60         # 60초 이하만 쇼츠로 간주
# ======================


def load_sources():
    here = Path(__file__).resolve().parent
    src = here / "sources.txt"
    lines = []
    if src.exists():
        for line in src.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
    return lines


def format_views_ko(n):
    try:
        n = int(n)
    except Exception:
        return ""
    if n < 1000:
        return f"{n}회"
    if n < 10000:
        return f"{n/1000:.1f}".rstrip("0").rstrip(".") + "천회"
    if n < 100000000:
        return f"{n/10000:.1f}".rstrip("0").rstrip(".") + "만회"
    return f"{n/100000000:.1f}".rstrip("0").rstrip(".") + "억회"


def time_ago_ko(published_at):
    # "2026-02-05T07:40:45Z" -> "+00:00" 형태로 변환
    dt = datetime.fromisoformat(published_at.replace("Z", "+00:00")).astimezone(KST)
    now = datetime.now(KST)
    sec = int((now - dt).total_seconds())
    if sec < 60:
        return "방금 전"
    if sec < 3600:
        return f"{sec//60}분 전"
    if sec < 86400:
        return f"{sec//3600}시간 전"
    if sec < 86400 * 30:
        return f"{sec//86400}일 전"
    if sec < 86400 * 365:
        return f"{sec//(86400*30)}개월 전"
    return f"{sec//(86400*365)}년 전"


def extract_handle(url: str):
    # https://www.youtube.com/@abc/shorts -> abc
    if "/@" not in url:
        return ""
    return url.split("/@")[1].split("/")[0].strip()


def extract_channel_id_from_handle(handle: str):
    if not handle:
        return None

    # ✅ channels.list 의 forHandle 사용 (가능하면 가장 정확)
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "id", "forHandle": handle, "key": API_KEY},
        timeout=20
    ).json()

    items = r.get("items", [])
    if items:
        return items[0].get("id")

    # fallback: search(type=channel)
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={"part": "snippet", "q": handle, "type": "channel", "maxResults": 1, "key": API_KEY},
        timeout=20
    ).json()
    items = r.get("items", [])
    if not items:
        return None

    # ✅ 여기 중요: channelId는 snippet이 아니라 id에 있음
    return items[0].get("id", {}).get("channelId")


def iso8601_duration_to_seconds(dur: str) -> int:
    # 예: PT59S, PT1M2S, PT2M, PT1H3M
    if not dur or not dur.startswith("PT"):
        return 999999
    h = m = s = 0
    m1 = re.search(r"(\d+)H", dur)
    m2 = re.search(r"(\d+)M", dur)
    m3 = re.search(r"(\d+)S", dur)
    if m1: h = int(m1.group(1))
    if m2: m = int(m2.group(1))
    if m3: s = int(m3.group(1))
    return h * 3600 + m * 60 + s


def search_recent_video_ids(channel_id: str, limit: int):
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "channelId": channel_id,
            "order": "date",
            "maxResults": limit,
            "type": "video",
            "key": API_KEY
        },
        timeout=20
    ).json()

    ids = []
    for x in r.get("items", []):
        vid = (x.get("id") or {}).get("videoId")
        if vid:
            ids.append(vid)
    return ids


def get_video_details(ids):
    if not ids:
        return []

    r = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={
            division := "part": "snippet,statistics,contentDetails",
            "id": ",".join(ids),
            "key": API_KEY
        },
        timeout=20
    ).json()

    return r.get("items", [])


def pick_latest_shorts(details):
    """
    details: videos.list 결과들(최신 후보들)
    - duration <= 60초만 "쇼츠"로 가정
    - 그중 publishedAt 최신 1개 선택
    """
    shorts = []
    for d in details:
        cd = d.get("contentDetails", {})
        dur = cd.get("duration", "")
        sec = iso8601_duration_to_seconds(dur)
        if sec <= SHORTS_MAX_SECONDS:
            shorts.append(d)

    if not shorts:
        return None

    # publishedAt 내림차순
    shorts.sort(key=lambda x: x.get("snippet", {}).get("publishedAt", ""), reverse=True)
    return shorts[0]


def main():
    if not API_KEY:
        raise RuntimeError("❌ YOUTUBE_API_KEY가 비어있습니다. GitHub Secrets에 등록하세요.")

    sources = load_sources()

    out = {
        "generatedAt": datetime.now(KST).isoformat(),
        "sources": sources,
        "items": []
    }

    for src in sources:
        handle = extract_handle(src)
        cid = extract_channel_id_from_handle(handle)
        if not cid:
            print("❌ channelId not found:", src)
            continue

        # 1) 최신 후보 여러 개
        ids = search_recent_video_ids(cid, SEARCH_CANDIDATES)
        if not ids:
            continue

        # 2) 상세(길이/조회수/업로드시간)
        details = get_video_details(ids)

        # 3) 60초 이하만 쇼츠로 간주 → 최신 1개 선택
        picked = pick_latest_shorts(details)
        if not picked:
            print("⚠️ no shorts (<=60s) found:", src)
            continue

        d = picked
        vid = d["id"]
        sn = d["snippet"]
        st = d.get("statistics", {})

        out["items"].append({
            "videoId": vid,
            "title": sn.get("title", ""),
            "uploader": sn.get("channelTitle", ""),
            "source": src,
            "url": f"https://www.youtube.com/shorts/{vid}",
            "thumbnail": (sn.get("thumbnails", {}).get("high", {}) or sn.get("thumbnails", {}).get("default", {})).get("url", ""),
            "viewsText": format_views_ko(st.get("viewCount")),
            "timeAgo": time_ago_ko(sn.get("publishedAt", "1970-01-01T00:00:00Z"))
        })

    # ✅ 혹시 sources 중복이 있으면 채널당 1개 유지
    dedup = {}
    for it in out["items"]:
        if it["source"] not in dedup:
            dedup[it["source"]] = it
    out["items"] = list(dedup.values())

    Path("docs").mkdir(exist_ok=True)
    with open("docs/shorts.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("✅ shorts.json generated:", len(out["items"]))


if __name__ == "__main__":
    main()

