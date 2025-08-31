
#!/usr/bin/env python3
"""
Fetch the best YouTube video and transcript for an identifier like:
    "IMO 2024 problem 5"

Primary: YouTube Data API v3 + youtube-transcript-api
Fallback: yt-dlp auto-captions (if available)

Usage:
    python fetch_imo_youtube_plus.py "IMO 2024 problem 5" --max 10 --outdir out
    python fetch_imo_youtube_plus.py "IMO 2024 problem 5" --fallback yt-dlp --cookies cookies.txt

Env:
    - YOUTUBE_API_KEY or GOOGLE_API_KEY for the search step.
    - Optional .env with those keys if python-dotenv is installed.

Outputs:
    - <video_id>.json   -> metadata (title, channel, url, etc.)
    - <video_id>.txt    -> transcript (if available)
    - search_results.json -> candidate list
"""
import os
import sys
import json
import time
import argparse
import pathlib
import re
import shlex
import subprocess
from typing import Dict, Any, List, Optional
import requests

# Try to load .env if available (don't require it)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

def get_api_key() -> str:
    key = os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise SystemExit(
            "Missing API key. Set YOUTUBE_API_KEY (preferred) or GOOGLE_API_KEY "
            "as an environment variable (can be placed in a .env file)."
        )
    return key

def search_youtube(query: str, api_key: str, max_results: int = 5, region_code: Optional[str] = None) -> List[Dict[str, Any]]:
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max(1, min(50, int(max_results))),
        "order": "relevance",
        "safeSearch": "none",
        "key": api_key,
    }
    if region_code:
        params["regionCode"] = region_code

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    results = []
    for item in data.get("items", []):
        vid = item["id"]["videoId"]
        sn = item["snippet"]
        results.append({
            "video_id": vid,
            "title": sn.get("title", ""),
            "description": sn.get("description", ""),
            "channel_title": sn.get("channelTitle", ""),
            "published_at": sn.get("publishedAt", ""),
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return results

def _score_candidate(title: str, description: str, query: str) -> float:
    t = title.lower()
    d = description.lower()
    q = query.lower()
    score = 0.0
    for kw in ["imo", "international mathematical olympiad"]:
        if kw in t: score += 4
        if kw in d: score += 1
    m_prob = re.search(r"problem\s*(\d+)", q)
    if m_prob:
        p = m_prob.group(1)
        if f"problem {p}" in t: score += 4
        if re.search(rf"\b{p}\b", t): score += 1
        if f"p{p}" in t: score += 1
        if f"#{p}" in t: score += 1
    m_year = re.search(r"(19|20)\d{2}", q)
    if m_year:
        y = m_year.group(0)
        if y in t: score += 3
        if y in d: score += 1
    score += max(0, 3 - len(title) / 50)
    for token in set(re.findall(r"[a-z0-9]+", q)):
        if token in t: score += 0.3
    return score

def pick_best(candidates: List[Dict[str, Any]], query: str) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None
    scored = [(c, _score_candidate(c["title"], c.get("description",""), query)) for c in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0]

def get_transcript_text(video_id: str) -> Optional[str]:
    """
    Robust transcript fetch via youtube-transcript-api.
    Tries manual EN, generated EN, then translates first available to EN.
    Handles older API oddities and XML parse failures.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound  # type: ignore
    except Exception:
        print("[warn] youtube-transcript-api not installed; cannot fetch transcript.", file=sys.stderr)
        return None

    try:
        list_obj = YouTubeTranscriptApi.list_transcripts(video_id)
    except Exception as e:
        print(f"[warn] list_transcripts failed: {e}", file=sys.stderr)
        list_obj = None

    if list_obj:
        # Try manual EN
        for pref in (["en"], ["en-US", "en-GB"]):
            try:
                tran_obj = list_obj.find_transcript(pref)
                tran = tran_obj.fetch()
                text = "\n".join([seg.get("text", "") for seg in tran if seg.get("text")]).strip()
                if text:
                    return text
            except Exception as e:
                # XML parse / empty -> continue
                continue
        # Try generated EN
        try:
            tran_obj = list_obj.find_generated_transcript(["en","en-US","en-GB"])
            tran = tran_obj.fetch()
            text = "\n".join([seg.get("text", "") for seg in tran if seg.get("text")]).strip()
            if text:
                return text
        except Exception as e:
            pass
        # Translate first available to EN
        try:
            first = next(iter(list_obj), None)
            if first is not None:
                tran = first.translate("en").fetch()
                text = "\n".join([seg.get("text", "") for seg in tran if seg.get("text")]).strip()
                if text:
                    return text
        except Exception as e:
            pass

    # Final legacy attempt: some very old installs only had get_transcript
    try:
        tran = YouTubeTranscriptApi.get_transcript(video_id, languages=["en","en-US","en-GB"])
        text = "\n".join([seg.get("text","") for seg in tran if seg.get("text")]).strip()
        if text:
            return text
    except Exception as e:
        pass

    return None

def run_yt_dlp_auto_sub(video_url: str, outdir: pathlib.Path, cookies: Optional[str] = None) -> Optional[pathlib.Path]:
    """
    Use yt-dlp to fetch auto-captions (en) without downloading the video.
    Returns the path to the .vtt file if created.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--skip-download",
        "--sub-lang", "en",
        "-o", "%(id)s.%(ext)s",
        video_url,
    ]
    if cookies:
        cmd.extend(["--cookies", cookies])

    try:
        subprocess.run(cmd, check=True, cwd=str(outdir), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        print("[warn] yt-dlp not installed. Install with: pip install yt-dlp", file=sys.stderr)
        return None
    except subprocess.CalledProcessError as e:
        print(f"[warn] yt-dlp failed: {e}", file=sys.stderr)
        return None

    # Find a .en.vtt (or any .vtt if lang marker absent)
    for p in outdir.glob("*.vtt"):
        return p
    return None

def vtt_to_txt(vtt_path: pathlib.Path) -> str:
    """Convert WEBVTT to plain text lines; drop timestamps and cues."""
    import re
    lines = []
    for line in vtt_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip().startswith("WEBVTT"):
            continue
        if line.strip().isdigit():
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3} -->", line):
            continue
        if line.strip():
            lines.append(line.strip())
    return "\n".join(lines).strip()

def save_outputs(outdir: pathlib.Path, video: Dict[str, Any], transcript: Optional[str]) -> Dict[str, str]:
    outdir.mkdir(parents=True, exist_ok=True)
    vid = video["video_id"]
    meta_path = outdir / f"{vid}.json"
    txt_path = outdir / f"{vid}.txt"
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(video, f, ensure_ascii=False, indent=2)
    if transcript:
        with txt_path.open("w", encoding="utf-8") as f:
            f.write(transcript)
    return {"meta": str(meta_path), "transcript": str(txt_path) if transcript else ""}

def main():
    ap = argparse.ArgumentParser(description="Find a YouTube solution video and transcript for an IMO problem.")
    ap.add_argument("query", help='e.g. "IMO 2024 problem 5"')
    ap.add_argument("--max", type=int, default=10, help="Max search results to consider (1-50).")
    ap.add_argument("--outdir", default="out", help="Directory to save outputs.")
    ap.add_argument("--region", default=None, help="Optional ISO region code (e.g., IN, US).")
    ap.add_argument("--fallback", choices=["none","yt-dlp"], default="yt-dlp", help="Fallback method if API transcript unavailable.")
    ap.add_argument("--cookies", default=None, help="Path to cookies file for yt-dlp (export from your browser).")
    args = ap.parse_args()

    api_key = get_api_key()
    candidates = search_youtube(args.query, api_key, max_results=args.max, region_code=args.region)
    if not candidates:
        raise SystemExit("No videos found for that query. Try adjusting your search.")

    best = pick_best(candidates, args.query)
    if not best:
        raise SystemExit("Couldn't rank candidates.")

    print(f"Best match:\n  Title : {best['title']}\n  Channel: {best['channel_title']}\n  URL   : {best['url']}\n  Published: {best['published_at']}")

    transcript = get_transcript_text(best["video_id"])
    if transcript:
        print(f"\nTranscript: found via youtube-transcript-api ({len(transcript.split())} words). Saving...")
    else:
        print("\nTranscript: not available or failed via API.")
        if args.fallback == "yt-dlp":
            print("Trying yt-dlp auto-captions fallback...")
            vtt_path = run_yt_dlp_auto_sub(best["url"], pathlib.Path(args.outdir), args.cookies)
            if vtt_path and vtt_path.exists():
                try:
                    transcript = vtt_to_txt(vtt_path)
                    if transcript:
                        print(f"yt-dlp fallback succeeded: {vtt_path.name}")
                    else:
                        print("yt-dlp fallback produced empty transcript.")
                except Exception as e:
                    print(f"[warn] Failed to parse VTT: {e}")

    paths = save_outputs(pathlib.Path(args.outdir), best, transcript)
    print(f"\nSaved:\n  Metadata : {paths['meta']}")
    if transcript:
        print(f"  Transcript: {paths['transcript']}")

    list_path = pathlib.Path(args.outdir) / "search_results.json"
    with list_path.open("w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
    print(f"  All search results: {list_path}")

if __name__ == "__main__":
    main()
