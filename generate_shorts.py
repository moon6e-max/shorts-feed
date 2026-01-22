import json
import subprocess
from datetime import datetime, timezone

CHANNEL_SHORTS_URLS = [
    "https://www.youtube.com/@virbro_/shorts",
]

MAX_ITEMS_PER_CHANNEL = 50  # 필요하면 100으로 늘려도 됨

def run_ytdlp_json_lines(url: str):
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--skip-download",
        "-j",
        url,
    ]
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

def normalize_item(x: dict):
    vid = x.get("id") or x.get("url")
    title = x.get("title") or ""
    uploader = x.get("uploader") or x.get("channel") or ""
    return {
        "videoId": vid,
        "title": title,
        "uploader": uploader,
        "url": f"https://www.youtube.com/shorts/{vid}" if vid else None,
        "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else None,
    }

def main():
    out = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sources": CHANNEL_SHORTS_URLS,
        "items": []
    }

    for url in CHANNEL_SHORTS_URLS:
        raw = run_ytdlp_json_lines(url)
        for x in raw[:MAX_ITEMS_PER_CHANNEL]:
            item = normalize_item(x)
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

    # Pages 배포 폴더
    with open("docs/shorts.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"✅ Wrote docs/shorts.json ({len(out['items'])} items)")

if __name__ == "__main__":
    main()
