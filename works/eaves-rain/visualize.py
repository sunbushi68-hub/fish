#!/usr/bin/env python3.11
"""把 timeline.json 与 WAV 画成两张独立的 SVG：钢琴卷帘、波形。"""

from __future__ import annotations

import array
import html
import json
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

FONT = "'Noto Sans CJK SC','Source Han Sans SC','WenQuanYi Micro Hei',sans-serif"
PAPER = "#fbf8f2"
INK = "#2b2a27"
MUTED = "#8a857c"
MELODY = "#b5533c"
BASS = "#2f6b7a"
PAUSE = "#e6dfd1"


def esc(text: str) -> str:
    return html.escape(str(text))


def load() -> tuple[dict, list[float]]:
    timeline = json.loads((OUT / "timeline.json").read_text(encoding="utf-8"))
    with wave.open(str(OUT / "eaves_rain.wav"), "rb") as w:
        ch = w.getnchannels()
        raw = w.readframes(w.getnframes())
    data = array.array("h")
    data.frombytes(raw)
    mono = [(data[i] + data[i + 1]) / 65536.0
            for i in range(0, len(data), 2)] if ch == 2 else \
           [v / 32768.0 for v in data]
    return timeline, mono


def pause_bands(tl: dict, x_of, top: float, bottom: float) -> list[str]:
    out = []
    for i, p in enumerate(tl["pauses"], start=1):
        x0 = x_of(p["start"])
        x1 = x_of(p["end"])
        out.append(
            f'<rect x="{x0:.2f}" y="{top:.2f}" width="{x1 - x0:.2f}" '
            f'height="{bottom - top:.2f}" fill="{PAUSE}" opacity="0.85"/>')
        if x1 - x0 > 14:
            out.append(
                f'<text x="{(x0 + x1) / 2:.2f}" y="{top + 16:.2f}" '
                f'font-size="10" fill="{MUTED}" text-anchor="middle" '
                f'transform="rotate(90 {(x0 + x1) / 2:.2f} {top + 16:.2f})">'
                f'停顿{i} · {p["seconds"]:.1f}s</text>')
    return out


def score_svg(tl: dict) -> str:
    W, H = 1560, 620
    left, right, top, bottom = 170, 40, 100, 90
    plot_w = W - left - right
    plot_h = H - top - bottom
    dur = tl["duration"]

    def x_of(t: float) -> float:
        return left + t / dur * plot_w

    lo, hi = 43, 86                      # G2 .. D6
    row_h = plot_h / (hi - lo + 1)

    def y_of(midi: int) -> float:
        return top + (hi - midi + 0.5) * row_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="{FONT}">',
        f'<rect width="{W}" height="{H}" fill="{PAPER}"/>',
        f'<text x="{left}" y="38" font-size="26" fill="{INK}" '
        f'font-weight="600">{esc(tl["title"])}</text>',
        f'<text x="{left}" y="63" font-size="13" fill="{MUTED}">'
        f'{esc(tl["subtitle"])}</text>',
        f'<text x="{W - right}" y="38" font-size="12" fill="{MUTED}" '
        f'text-anchor="end">钢琴卷帘 · {dur:.1f}s</text>',
    ]

    # 段落底色
    for i, sec in enumerate(tl["sections"]):
        if i % 2 == 0:
            x0, x1 = x_of(sec["start"]), x_of(sec["end"])
            parts.append(f'<rect x="{x0:.2f}" y="{top}" width="{x1 - x0:.2f}" '
                         f'height="{plot_h}" fill="#f3eee4" opacity="0.55"/>')

    parts += pause_bands(tl, x_of, top, top + plot_h)

    # 横向半音格
    for midi in range(lo, hi + 1):
        y = y_of(midi)
        is_c = midi % 12 == 0
        parts.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{W - right}" y2="{y:.2f}" '
            f'stroke="{"#d8d0c2" if is_c else "#eee8dc"}" '
            f'stroke-width="{1.0 if is_c else 0.6}"/>')
        if is_c:
            parts.append(
                f'<text x="{left - 10}" y="{y + 3.5:.2f}" font-size="10" '
                f'fill="{MUTED}" text-anchor="end">C{midi // 12 - 1}</text>')

    # 小节线与和弦
    for sec in tl["sections"]:
        for chord in sec["chords"]:
            bar = chord["bar"]
            bar_t = None
            for n in tl["notes"]:
                if n["bar"] == bar:
                    bar_t = n["start"]
                    break
            if bar_t is None:
                continue
            x = x_of(bar_t)
            parts.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" '
                         f'y2="{top + plot_h}" stroke="#cfc6b6" '
                         f'stroke-width="0.9" stroke-dasharray="3 4"/>')
            parts.append(f'<text x="{x + 5:.2f}" y="{top - 9}" font-size="12" '
                         f'fill="{INK}" font-weight="600">'
                         f'{esc(chord["symbol"])}</text>')
            parts.append(f'<text x="{x + 5:.2f}" y="{top + plot_h + 17}" '
                         f'font-size="9" fill="{MUTED}">'
                         f'{bar}</text>')

    # 段落标签
    for sec in tl["sections"]:
        parts.append(
            f'<text x="{x_of(sec["start"]) + 6:.2f}" y="{top + 15}" '
            f'font-size="11" fill="{MUTED}" letter-spacing="0.5">'
            f'{esc(sec["label"])}</text>')

    # 音符
    for n in tl["notes"]:
        x = x_of(n["start"])
        w = max(2.5, n["dur"] / dur * plot_w - 1.2)
        y = y_of(n["midi"]) - row_h * 0.40
        h = row_h * 0.80
        color = MELODY if n["voice"] == "melody" else BASS
        parts.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'rx="1.8" fill="{color}" opacity="{0.92 if n["voice"] == "melody" else 0.8}"/>')

    # 图例与署名
    ly = H - 26
    parts += [
        f'<rect x="{left}" y="{ly - 10}" width="16" height="10" rx="2" '
        f'fill="{MELODY}"/>',
        f'<text x="{left + 24}" y="{ly - 1}" font-size="11" fill="{INK}">'
        f'旋律（62 音）</text>',
        f'<rect x="{left + 120}" y="{ly - 10}" width="16" height="10" rx="2" '
        f'fill="{BASS}"/>',
        f'<text x="{left + 144}" y="{ly - 1}" font-size="11" fill="{INK}">'
        f'低音（34 音）</text>',
        f'<text x="{W - right}" y="{ly - 1}" font-size="10" fill="{MUTED}" '
        f'text-anchor="end">由 piece.py 的标准库合成 · 时间线见 timeline.json</text>',
        "</svg>",
    ]
    return "\n".join(parts)


def waveform_svg(tl: dict, mono: list[float]) -> str:
    W, H = 1560, 440
    left, right, top, bottom = 90, 40, 78, 66
    plot_w = W - left - right
    plot_h = H - top - bottom
    dur = tl["duration"]

    def x_of(t: float) -> float:
        return left + t / dur * plot_w

    mid = top + plot_h / 2
    amp = plot_h / 2 / 0.92

    # 每 2 px 取一个 min/max 包络
    cols = int(plot_w // 2)
    env = []
    for c in range(cols):
        t0 = c / cols * dur
        t1 = (c + 1) / cols * dur
        a = int(t0 * tl["sample_rate"])
        b = min(len(mono), int(t1 * tl["sample_rate"]) + 1)
        if b <= a:
            env.append((0.0, 0.0))
        else:
            seg = mono[a:b]
            env.append((min(seg), max(seg)))

    upper = [f"{left + c * plot_w / cols:.2f},{mid - hi * amp:.2f}"
             for c, (lo, hi) in enumerate(env)]
    lower = [f"{left + c * plot_w / cols:.2f},{mid - lo * amp:.2f}"
             for c, (lo, hi) in enumerate(env)][::-1]
    path = "M " + " L ".join(upper) + " L " + " L ".join(lower) + " Z"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="{FONT}">',
        f'<rect width="{W}" height="{H}" fill="{PAPER}"/>',
        f'<text x="{left}" y="36" font-size="24" fill="{INK}" '
        f'font-weight="600">波形与结构</text>',
        f'<text x="{left}" y="58" font-size="12" fill="{MUTED}">'
        f'{esc(tl["title"])} · 峰值归一化到 −1 dBFS · 灰块为谱面上的三次停顿</text>',
        f'<text x="{W - right}" y="36" font-size="11" fill="{MUTED}" '
        f'text-anchor="end">{dur:.2f}s · 44.1 kHz · 16-bit stereo</text>',
    ]

    parts += pause_bands(tl, x_of, top, top + plot_h)

    # 时间刻度
    for t in range(0, int(dur) + 1, 2):
        x = x_of(t)
        parts.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" '
                     f'y2="{top + plot_h}" stroke="#e7e0d3" stroke-width="0.7"/>')
        parts.append(f'<text x="{x:.2f}" y="{top + plot_h + 20}" font-size="10" '
                     f'fill="{MUTED}" text-anchor="middle">{t}s</text>')

    for frac, label in ((0.5, "+0.5"), (0.0, "0"), (-0.5, "−0.5")):
        y = mid - frac * amp
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{W - right}" '
                     f'y2="{y:.2f}" stroke="#d9d1c2" '
                     f'stroke-width="{1 if frac == 0 else 0.6}"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 3.5:.2f}" font-size="9" '
                     f'fill="{MUTED}" text-anchor="end">{label}</text>')

    parts.append(f'<path d="{path}" fill="{MELODY}" opacity="0.78"/>')

    for sec in tl["sections"]:
        x = x_of(sec["start"])
        parts.append(f'<text x="{x + 5:.2f}" y="{top + 14}" font-size="10" '
                     f'fill="{INK}" opacity="0.7">{esc(sec["id"])}</text>')

    parts += [
        f'<text x="{left}" y="{H - 20}" font-size="10" fill="{MUTED}">'
        f'包络由 mono 混音逐列取 min/max 得到；图只说明响度与结构，不等于听感评价。</text>',
        "</svg>",
    ]
    return "\n".join(parts)


def page_html(tl: dict) -> str:
    rows = []
    for sec in tl["sections"]:
        rows.append(
            f'<li><span class="t">{sec["start"]:.1f}s</span>'
            f'<strong>{esc(sec["label"])}</strong>'
            f'<span class="n">{esc(" ".join(c["symbol"] for c in sec["chords"]))}</span></li>')
        for p in tl["pauses"]:
            if p["after"] == sec["id"]:
                rows.append(
                    f'<li class="pause"><span class="t">{p["start"]:.1f}s</span>'
                    f'<strong>停顿 {p["seconds"]:.1f}s</strong>'
                    f'<span class="n">留白</span></li>')
    return f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(tl["title"])} · 本地合成小品</title>
<style>
  :root {{ --paper:#fbf8f2; --ink:#2b2a27; --muted:#8a857c; --line:#ded6c7; --accent:#b5533c; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
         font:16px/1.7 "Noto Sans CJK SC","Source Han Sans SC","PingFang SC",sans-serif; }}
  main {{ max-width:1080px; margin:0 auto; padding:56px 28px 72px; }}
  h1 {{ font-size:44px; margin:0 0 6px; letter-spacing:.06em; font-weight:600; }}
  .sub {{ color:var(--muted); margin:0 0 28px; font-size:14px; }}
  audio {{ width:100%; margin:6px 0 8px; }}
  .hint {{ color:var(--muted); font-size:12px; margin:0 0 36px; }}
  h2 {{ font-size:15px; letter-spacing:.12em; color:var(--muted); font-weight:600;
        border-top:1px solid var(--line); padding-top:22px; margin:36px 0 14px; }}
  ul {{ list-style:none; padding:0; margin:0; display:grid; gap:2px; }}
  li {{ display:grid; grid-template-columns:74px 1fr auto; gap:12px;
        padding:7px 10px; border-bottom:1px solid #eee8dc; font-size:14px; }}
  li.pause {{ color:var(--muted); background:#f4efe4; }}
  .t {{ font-variant-numeric:tabular-nums; color:var(--muted); }}
  .n {{ color:var(--muted); font-size:12px; }}
  figure {{ margin:18px 0 0; }}
  img {{ width:100%; height:auto; display:block; border:1px solid var(--line); border-radius:4px; background:#fff; }}
  figcaption {{ color:var(--muted); font-size:12px; margin-top:8px; }}
  footer {{ margin-top:52px; color:var(--muted); font-size:12px; border-top:1px solid var(--line); padding-top:16px; }}
  a {{ color:var(--accent); }}
</style>
<main>
  <h1>{esc(tl["title"])}</h1>
  <p class="sub">{esc(tl["subtitle"])}</p>
  <audio controls preload="metadata" src="eaves_rain.wav">
    你的浏览器不支持 audio 元素，请直接打开 eaves_rain.wav。
  </audio>
  <p class="hint">本地文件 · 30.2 秒 · 无外部素材、无联网、无账号动作</p>

  <h2>结构</h2>
  <ul>{"".join(rows)}</ul>

  <h2>钢琴卷帘</h2>
  <figure>
    <img src="score.svg" alt="钢琴卷帘：旋律、低音与三次停顿">
    <figcaption>橙色为旋律，蓝绿色为低音；灰色竖条是三次逐渐变长的停顿。</figcaption>
  </figure>

  <h2>波形</h2>
  <figure>
    <img src="waveform.svg" alt="整曲波形包络">
    <figcaption>逐列 min/max 包络，只说明响度与结构，不等于听感评价。</figcaption>
  </figure>

  <footer>
    由 <code>piece.py</code> 用 Python 3.11 标准库合成，<code>visualize.py</code> 画图。<br>
    这只是一个本地作品页：没有连接或发布到任何社交平台。
  </footer>
</main>
</html>"""


def main() -> None:
    tl, mono = load()
    (OUT / "score.svg").write_text(score_svg(tl), encoding="utf-8")
    (OUT / "waveform.svg").write_text(waveform_svg(tl, mono), encoding="utf-8")
    (OUT / "index.html").write_text(page_html(tl), encoding="utf-8")
    print("写出 out/score.svg、out/waveform.svg、out/index.html")


if __name__ == "__main__":
    main()
