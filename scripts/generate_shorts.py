import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


# 채널당 몇 개 가져올지 (원하면 2~3으로 늘려도 됨)
MAX_ITEMS_PER_CHANNEL = 1


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


def infer_uploader_from_url(channel_url: str) -> str:
    # https://www.youtube.com/@handle/shorts  -> handle
    try:
        parts = channel_url.split("/")
        for p in parts:
            if p.startswith("@"):
                return p[1:]
    except Exception:
        pass
    return ""


def normalize_item(x: dict, channel_url: str):
    vid = x.get("id") or x.get("url")
    title = x.get("title") or ""
    uploader = x.get("uploader") or x.get("channel") or ""
    if not uploader:
        uploader = infer_uploader_from_url(channel_url)

    return {
        "videoId": vid,
        "title": title,
        "uploader": uploader,
        "url": f"https://www.youtube.com/shorts/{vid}" if vid else None,
        "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else None,
        # (선택) 어떤 채널에서 왔는지 앱에서 쓰고 싶으면 이 필드 유지
        "source": channel_url,
    }


def read_sources_txt(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"sources.txt not found: {path}")

    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        urls.append(line)
    return urls


def main():
    # repo root = scripts 폴더의 상위 폴더
    repo_root = Path(__file__).resolve().parents[1]

    sources_path = repo_root / "scripts" / "sources.txt"
    channel_urls = read_sources_txt(sources_path)

    out = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sources": channel_urls,
        "items": []
    }

    for url in channel_urls:
        raw = run_ytdlp_json_lines(url)

        # ✅ 채널당 최신 1개만
        for x in raw[:MAX_ITEMS_PER_CHANNEL]:
            item = normalize_item(x, url)
            if item["videoId"]:
                out["items"].append(item)

    # ✅ 중복 제거
    seen = set()
    deduped = []
    for it in out["items"]:
        if it["videoId"] in seen:
            continue
        seen.add(it["videoId"])
        deduped.append(it)
    out["items"] = deduped

    # ✅ Pages 배포 폴더로 저장
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    out_path = docs_dir / "shorts.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ Wrote {out_path} ({len(out['items'])} items)")


if __name__ == "__main__":
    main()

