import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ======================
# 설정
# ======================

API_KEY = "unique-perigee-387707"   # ← 여기에 키 넣기
MAX_ITEMS_PER_CHANNEL = 1

KST = timezone(timedelta(hours=9))

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
    except:
        return ""

    if n < 1000:
        return f"{n}회"
    if n < 10000:
        return f"{n/1000:.1f}".rstrip("0").rstrip(".") + "천회"
    if n < 100000000:
        return f"{n/10000:.1f}".rstrip("0").rstrip(".") + "만회"
    return f"{n/100000000:.1f}".rstrip("0").rstrip(".") + "억회"


def time_ago_ko(published_at):
    dt = datetime.fromisoformat(published_at.replace("Z","")).replace(tzinfo=timezone.utc).astimezone(KST)
    now = datetime.now(KST)
    diff = now - dt
    sec = int(diff.total_seconds())

    if sec < 60: return "방금 전"
    if sec < 3600: return f"{sec//60}분 전"
    if sec < 86400: return f"{sec//3600}시간 전"
    if sec < 86400*30: return f"{sec//86400}일 전"
    if sec < 86400*365: return f"{sec//(86400*30)}개월 전"
    return f"{sec//(86400*365)}년 전"


def extract_channel_id(url):
    if "/@" in url:
        name = url.split("/@")[1].split("/")[0]
        q = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": name,
                "type": "channel",
                "key": API_KEY
            }
        ).json()
        return q["items"][0]["snippet"]["channelId"]
    return None


def get_latest_shorts(channel_id):
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "channelId": channel_id,
            "order": "date",
            "maxResults": MAX_ITEMS_PER_CHANNEL,
            "type": "video",
            "key": API_KEY
        }
    ).json()

    return [x["id"]["videoId"] for x in r.get("items", [])]


def get_video_details(ids):
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={
            "part": "snippet,statistics",
            "id": ",".join(ids),
            "key": API_KEY
        }
    ).json()

    return r.get("items", [])


def main():
    sources = load_sources()

    out = {
        "generatedAt": datetime.now(KST).isoformat(),
        "sources": sources,
        "items": []
    }

    for src in sources:
        cid = extract_channel_id(src)
        if not cid:
            continue

        ids = get_latest_shorts(cid)
        if not ids:
            continue

        details = get_video_details(ids)

        for d in details:
            vid = d["id"]
            sn = d["snippet"]
            st = d["statistics"]

            out["items"].append({
                "videoId": vid,
                "title": sn["title"],
                "uploader": sn["channelTitle"],
                "source": src,
                "url": f"https://www.youtube.com/shorts/{vid}",
                "thumbnail": sn["thumbnails"]["high"]["url"],
                "viewsText": format_views_ko(st.get("viewCount")),
                "timeAgo": time_ago_ko(sn["publishedAt"])
            })

    Path("docs").mkdir(exist_ok=True)
    with open("docs/shorts.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("✅ shorts.json generated:", len(out["items"]))


if __name__ == "__main__":
    main()
