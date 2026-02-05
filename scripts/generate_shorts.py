import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 채널당 최신 N개
MAX_ITEMS_PER_CHANNEL = 1

KST = timezone(timedelta(hours=9))

def load_sources():
    here = Path(__file__).resolve().parent          # scripts/
    src = here / "sources.txt"                      # scripts/sources.txt
    lines = []
    if src.exists():
        for line in src.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            lines.append(line)
    return lines

def run_ytdlp_json_lines(url: str, limit: int, flat: bool):
    cmd = ["yt-dlp", "--skip-download", "--playlist-end", str(limit), "-j"]
    if flat:
        cmd.insert(1, "--flat-playlist")
    cmd.append(url)

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"yt-dlp failed for {url}\nSTDERR:\n{p.stderr}")

    items = []
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return items

def fetch_video_detail(video_id: str):
    """Shorts 개별 URL로 상세 메타(조회수/업로드 시간 등) 받아오기"""
    if not video_id:
        return None

    url = f"https://www.youtube.com/shorts/{video_id}"

    cmd = [
        "yt-dlp",
        "--skip-download",
        "-j",
        "--no-warnings",
        "--geo-bypass",
        "--extractor-args", "youtube:player_client=android",
        url
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)

    if p.returncode != 0:
        # ✅ 실패 이유 로그 (Actions에서 확인 가능)
        print("DETAIL FAIL:", video_id)
        print("STDERR:", (p.stderr or "")[:500])
        return None

    try:
        last = p.stdout.strip().splitlines()[-1]
        return json.loads(last)
    except Exception as e:
        print("DETAIL PARSE FAIL:", video_id, e)
        return None


def format_views_ko(view_count):
    """예: 28340 -> '2.8만회' / 532 -> '532회' / 120000000 -> '1.2억회'"""
    try:
        n = int(view_count)
    except Exception:
        return ""

    if n < 1000:
        return f"{n}회"
    if n < 10_000:
        # 1,234 -> 1.2천회 (원하면 그냥 1,234회로 바꿔도 됨)
        return f"{n/1000:.1f}".rstrip("0").rstrip(".") + "천회"
    if n < 100_000_000:
        return f"{n/10_000:.1f}".rstrip("0").rstrip(".") + "만회"
    return f"{n/100_000_000:.1f}".rstrip("0").rstrip(".") + "억회"

def time_ago_ko(ts):
    """UNIX timestamp(초) -> '3시간 전' 같은 한국어 상대시간"""
    if not ts:
        return ""
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(KST)
    except Exception:
        return ""

    now = datetime.now(KST)
    diff = now - dt
    sec = int(diff.total_seconds())
    if sec < 0:
        sec = 0

    minute = 60
    hour = 3600
    day = 86400

    if sec < minute:
        return "방금 전"
    if sec < hour:
        return f"{sec//minute}분 전"
    if sec < day:
        return f"{sec//hour}시간 전"
    if sec < day * 30:
        return f"{sec//day}일 전"
    if sec < day * 365:
        return f"{sec//(day*30)}개월 전"
    return f"{sec//(day*365)}년 전"

# ✅ 조회수
view_count = detail.get("view_count") if detail else None

# ✅ 시간 (fallback 포함)
ts = None
if detail:
    ts = detail.get("timestamp") or detail.get("release_timestamp")

    # upload_date fallback (YYYYMMDD → timestamp)
    if not ts:
        ud = detail.get("upload_date")
        if ud and len(ud) == 8:
            try:
                dt = datetime(
                    int(ud[0:4]),
                    int(ud[4:6]),
                    int(ud[6:8]),
                    0, 0, 0,
                    tzinfo=timezone.utc
                )
                ts = int(dt.timestamp())
            except Exception:
                ts = None

# ✅ 로그 확인용
print("NORMALIZE:", vid, "views=", view_count, "ts=", ts)


    return {
        "videoId": vid,
        "title": title,
        "uploader": uploader,
        "source": source_url,
        "url": f"https://www.youtube.com/shorts/{vid}" if vid else None,
        "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else None,
        "viewsText": format_views_ko(view_count),
        "timeAgo": time_ago_ko(ts),
    }


def main():
    sources = load_sources()
    if not sources:
        raise RuntimeError("scripts/sources.txt 가 비어있거나 없습니다.")

    out = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "items": []
    }

    for url in sources:
        # 1) 채널 shorts 목록에서 최신 N개 id만 빠르게
        raw_flat = run_ytdlp_json_lines(url, MAX_ITEMS_PER_CHANNEL, flat=True)

        for x in raw_flat:
            vid = x.get("id") or x.get("url")
            if not vid:
                continue

            # 2) 각 shorts 영상 상세 메타(조회수/시간) 가져오기
            detail = fetch_video_detail(vid)

            item = normalize_item(x, detail, url)
            if item["videoId"]:
                out["items"].append(item)

    # 중복 제거
    seen = set()
    deduped = []
    for it in out["items"]:
        if it["videoId"] in seen:
            continue
        seen.add(it["videoId"])
        deduped.append(it)
    out["items"] = deduped

    # Pages 배포 폴더 docs/
    Path("docs").mkdir(exist_ok=True)
    with open("docs/shorts.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"✅ Wrote docs/shorts.json ({len(out['items'])} items)")

if __name__ == "__main__":
    main()
