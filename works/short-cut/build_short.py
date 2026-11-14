#!/usr/bin/env python3.11
"""把《檐下雨》剪成一支 15 秒竖屏切片，字幕卡在段落边界上。

只问一件小事：能不能让字幕只在段落内出现、在三次停顿处留白，并且
把段落的和弦写对？——所以时间点全部取自 out/timeline.json，不手填。

产物：out/eaves_rain_15s.mp4（720×1280，H.264/AAC）
运行：python3.11 build_short.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SRC_WAV = HERE.parent / "first-work" / "out" / "eaves_rain.wav"
TIMELINE = HERE.parent / "first-work" / "out" / "timeline.json"
FONT = "/usr/share/fonts/google-droid/DroidSansFallback.ttf"
START = 1.4          # 从 A1 起拍开始
DURATION = 15.0

CAPTIONS = [          # (段落 id, 文案)
    ("A1", "A1 · 第一次陈述　Dm – Bb – Gm – Am"),
    ("A2", "A2 · 应答　同样的和弦，句尾换回 Dm"),
    ("B", "B · 抬起来　Bb – Gm – Am – Dm"),
]


def main() -> None:
    tl = json.loads(TIMELINE.read_text(encoding="utf-8"))
    secs = {s["id"]: s for s in tl["sections"]}
    end = START + DURATION

    # 字幕时间：段落起点裁剪到窗口内，段落终点同样裁剪；窗口尾部若进 B 段则到 15 s
    lines = []
    for i, (sid, text) in enumerate(CAPTIONS):
        s = max(secs[sid]["start"], START)
        e = min(secs[sid]["end"], end)
        if e <= s:
            continue
        t0, t1 = s - START, e - START
        cap = OUT / f"caption_{i}.txt"
        cap.write_text(text, encoding="utf-8")
        lines.append((str(cap), t0, t1))

    filters = [
        "color=c=0x0b1220:s=720x1280:r=30:d=15,format=rgb24[bg]",
        "[0:a]showwaves=s=720x1280:mode=cline:colors=0x4a7fb5:rate=30,format=rgb24[wv]",
        "[bg][wv]blend=all_mode=screen,format=yuv420p[base]",
    ]
    for i, (path, t0, t1) in enumerate(lines):
        src = "base" if i == 0 else f"v{i - 1}"
        filters.append(
            f"[{src}]drawtext=fontfile={FONT}:textfile={path}:"
            f"fontcolor=white:fontsize=30:x=(w-text_w)/2:y=h-260:"
            f"enable='between(t\\,{t0:.2f}\\,{t1:.2f})'[v{i}]")
    last = f"v{len(lines) - 1}"
    filters.append(f"[{last}]fade=t=in:st=0:d=0.4,fade=t=out:st={DURATION - 0.6:.2f}:d=0.6[vout]")
    filters.append(f"[0:a]afade=t=in:st=0:d=0.3,afade=t=out:st={DURATION - 0.5:.2f}:d=0.5[aout]")

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{START}", "-t", f"{DURATION}", "-i", str(SRC_WAV),
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-crf", "23", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(OUT / "eaves_rain_15s.mp4"),
    ]
    subprocess.run(cmd, check=True)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_name,width,height,r_frame_rate",
         "-of", "json", str(OUT / "eaves_rain_15s.mp4")],
        capture_output=True, text=True, check=True)
    report = {"window": [START, end], "captions": [
        {"section": CAPTIONS[i][0], "text": CAPTIONS[i][1], "t0": round(t0, 3), "t1": round(t1, 3)}
        for i, (_, t0, t1) in enumerate(lines)],
        "ffprobe": json.loads(probe.stdout)}
    (OUT / "short_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
