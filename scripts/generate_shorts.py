import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# 채널당 최신 1개만
MAX_ITEMS_PER_CHANNEL = 1

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

def run_ytdlp_json_lines(url: str, limit: int):
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--skip-download",
        "--playlist-end", str(limit),   # ✅ 최신 N개만
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

def normalize_item(x: dict, source_url: str):
    vid = x.get("id") or x.get("url")
    title = x.get("title") or ""
    uploader = x.get("uploader") or x.get("channel") or ""  # 없으면 빈값

    return {
        "videoId": vid,
        "title": title,
        "uploader": uploader,
        "source": source_url,  # ✅ 어떤 채널에서 왔는지 추적용
        "url": f"https://www.youtube.com/shorts/{vid}" if vid else None,
        "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else None,
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
        raw = run_ytdlp_json_lines(url, MAX_ITEMS_PER_CHANNEL)
        for x in raw:
            item = normalize_item(x, url)
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


if __name__ == "__main__":
    main()

