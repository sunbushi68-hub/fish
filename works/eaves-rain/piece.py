#!/usr/bin/env python3.11
"""《檐下雨》— 一首只用 Python 标准库合成的 6/8 小品。

结构：前奏 1 小节 + 四个 4 小节段落，段与段之间插三次逐渐变长的停顿。
所有音高、时值、和弦、停顿都写在数据里，合成过程无随机数、可复现。

用法：
    python3.11 piece.py            # 生成 out/eaves_rain.wav 与 out/timeline.json
"""

from __future__ import annotations

import array
import json
import math
import wave
from pathlib import Path

SR = 44_100
BPM = 84.0                     # 附点四分音符 = 84
EIGHTH = 60.0 / BPM / 3.0      # 6/8 拍里一个八分音符的秒数
BAR = 6 * EIGHTH               # 一小节 = 6 个八分音符
TAIL = 3.0                     # 最后一个音之后的混响尾巴

TITLE = "檐下雨"
SUBTITLE = "D 小调 · 6/8 · 附点四分音符 84 · 三次逐渐变长的停顿"

# ---------------------------------------------------------------- 音高

NOTE_TO_MIDI = {}
for _oct in range(0, 8):
    for _name, _pc in (("C", 0), ("C#", 1), ("D", 2), ("D#", 3),
                       ("E", 4), ("F", 5), ("F#", 6), ("G", 7),
                       ("G#", 8), ("A", 9), ("A#", 10), ("B", 11)):
        NOTE_TO_MIDI[f"{_name}{_oct}"] = 12 * (_oct + 1) + _pc
NOTE_TO_MIDI["Bb4"] = NOTE_TO_MIDI["A#4"]
NOTE_TO_MIDI["Bb5"] = NOTE_TO_MIDI["A#5"]
NOTE_TO_MIDI["Bb2"] = NOTE_TO_MIDI["A#2"]


def freq_of(midi: int) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


# ---------------------------------------------------------------- 乐谱

# 每小节 6 个八分音符；写法是 "音名:占几个八分音符"。
A1 = [
    "D5:2 F5:1 E5:1 F5:1 D5:1",
    "A4:2 C5:1 Bb4:1 A4:2",
    "D5:2 F5:1 G5:1 A5:2",
    "F5:2 E5:1 C5:3",
]
A2 = [
    "A5:2 G5:1 F5:1 E5:2",
    "D5:2 C5:1 Bb4:1 A4:2",
    "D5:2 F5:1 G5:1 A5:1 F5:1",
    "E5:2 D5:4",
]
B = [
    "F5:3 D5:1 F5:2",
    "G5:2 F5:1 D5:1 Bb4:2",
    "C5:2 E5:1 G5:1 A5:2",
    "D6:3 C6:1 A5:1 F5:1",
]
A_RETURN = [
    "D5:2 F5:1 E5:1 F5:1 D5:1",
    "A4:2 C5:1 Bb4:1 A4:2",
    "D5:2 F5:1 G5:1 A5:2",
    "F5:1 E5:1 D5:4",
]

MELODY_BY_BAR = {}
for _i, _bar in enumerate(A1, start=1):
    MELODY_BY_BAR[_i] = _bar
for _i, _bar in enumerate(A2, start=5):
    MELODY_BY_BAR[_i] = _bar
for _i, _bar in enumerate(B, start=9):
    MELODY_BY_BAR[_i] = _bar
for _i, _bar in enumerate(A_RETURN, start=13):
    MELODY_BY_BAR[_i] = _bar

CHORD_BY_BAR = {
    1: "Dm", 2: "Bb", 3: "Gm", 4: "Am",
    5: "Dm", 6: "Bb", 7: "Gm", 8: "Dm",
    9: "Bb", 10: "Gm", 11: "Am", 12: "Dm",
    13: "Dm", 14: "Bb", 15: "Gm", 16: "Dm",
}

# 低音：每小节两个音，各占一个附点四分音符。
BASS_FOR_CHORD = {
    "Dm": ("D3", "A3"),
    "Bb": ("Bb2", "F3"),
    "Gm": ("G2", "D3"),
    "Am": ("A2", "E3"),
}

SECTIONS = [
    {"id": "intro", "label": "前奏", "start_bar": 0, "end_bar": 0,
     "gain": 0.34, "pause_after": 0.0},
    {"id": "A1", "label": "A1 · 第一次陈述", "start_bar": 1, "end_bar": 4,
     "gain": 0.62, "pause_after": 0.4},
    {"id": "A2", "label": "A2 · 应答", "start_bar": 5, "end_bar": 8,
     "gain": 0.66, "pause_after": 0.9},
    {"id": "B", "label": "B · 抬起来", "start_bar": 9, "end_bar": 12,
     "gain": 0.84, "pause_after": 1.6},
    {"id": "A'", "label": "A′ · 回来", "start_bar": 13, "end_bar": 16,
     "gain": 0.56, "pause_after": 0.0},
]


def build_timeline() -> dict:
    """把乐谱展开成绝对时间，返回可写盘的时间线。"""
    bar_start: dict[int, float] = {}
    cursor = 0.0
    sections = []
    pauses = []

    for sec in SECTIONS:
        sections.append({
            "id": sec["id"],
            "label": sec["label"],
            "start": cursor,
            "chords": [],
        })
        for bar in range(sec["start_bar"], sec["end_bar"] + 1):
            bar_start[bar] = cursor
            cursor += BAR
            if bar != 0:
                sections[-1]["chords"].append(
                    {"bar": bar, "symbol": CHORD_BY_BAR[bar]})
        sections[-1]["end"] = cursor
        if sec["pause_after"] > 0:
            pauses.append({
                "after": sec["id"],
                "start": cursor,
                "end": cursor + sec["pause_after"],
                "seconds": sec["pause_after"],
            })
            cursor += sec["pause_after"]

    duration = cursor + TAIL

    notes = []
    # 低音
    for bar, start in sorted(bar_start.items()):
        chord = "Dm" if bar == 0 else CHORD_BY_BAR[bar]
        root, fifth = BASS_FOR_CHORD[chord]
        sec_gain = next(s["gain"] for s in SECTIONS
                        if s["start_bar"] <= bar <= s["end_bar"])
        for beat, name in ((0, root), (3, fifth)):
            midi = NOTE_TO_MIDI[name]
            notes.append({
                "voice": "bass", "bar": bar, "name": name, "midi": midi,
                "start": start + beat * EIGHTH,
                "dur": 3 * EIGHTH,
                "freq": round(freq_of(midi), 3),
                "amp": round(sec_gain * 0.46, 3),
            })

    # 旋律
    for bar, text in MELODY_BY_BAR.items():
        pos = 0
        tokens = text.split()
        for idx, token in enumerate(tokens):
            name, length = token.split(":")
            length = int(length)
            midi = NOTE_TO_MIDI[name]
            sec = next(s for s in SECTIONS
                       if s["start_bar"] <= bar <= s["end_bar"])
            # 句内轻微起伏：句子中段稍强，句尾稍收。
            arc = 0.90 + 0.10 * math.sin(math.pi * (idx + 0.5) / len(tokens))
            notes.append({
                "voice": "melody", "bar": bar, "name": name, "midi": midi,
                "start": bar_start[bar] + pos * EIGHTH,
                "dur": length * EIGHTH,
                "freq": round(freq_of(midi), 3),
                "amp": round(sec["gain"] * arc, 3),
            })
            pos += length
        if pos != 6:
            raise ValueError(f"第 {bar} 小节时值合计 {pos}，应为 6")

    return {
        "title": TITLE,
        "subtitle": SUBTITLE,
        "sample_rate": SR,
        "channels": 2,
        "bit_depth": 16,
        "tempo": {"meter": "6/8", "dotted_quarter_bpm": BPM,
                  "eighth_seconds": round(EIGHTH, 6),
                  "bar_seconds": round(BAR, 6)},
        "tuning": "A4 = 440 Hz，十二平均律",
        "duration": round(duration, 6),
        "sections": sections,
        "pauses": pauses,
        "notes": notes,
        "counts": {"melody": sum(n["voice"] == "melody" for n in notes),
                   "bass": sum(n["voice"] == "bass" for n in notes)},
    }


# ---------------------------------------------------------------- 合成

def render_tone(left: list[float], right: list[float], t0: float, dur: float,
                freq: float, amp: float, pan: float, release: float,
                harmonics: tuple[float, ...], vibrato: bool) -> None:
    """把一个带 ADSR 的加法合成音叠加到立体声缓冲区。"""
    n = int((dur + release) * SR)
    start = int(round(t0 * SR))
    if start + n > len(left):
        n = len(left) - start
    if n <= 0:
        return

    gl = math.cos((pan + 1.0) * math.pi / 4.0) * amp
    gr = math.sin((pan + 1.0) * math.pi / 4.0) * amp
    w = 2.0 * math.pi * freq
    attack = 0.012
    end = dur + release
    tail_fade = 0.02

    for i in range(n):
        t = i / SR
        if t < attack:
            env = t / attack
        elif t < attack + 0.13:
            env = 1.0 - 0.30 * ((t - attack) / 0.13)
        elif t < dur:
            env = 0.70
        else:
            env = 0.70 * math.exp(-4.0 * (t - dur) / release)
        if t > end - tail_fade:
            env *= max(0.0, (end - t) / tail_fade)
        if env <= 1e-5:
            continue

        phase = w * t
        if vibrato:
            depth = 0.25 * min(1.0, max(0.0, (t - 0.18) / 0.30))
            phase += depth * math.sin(2.0 * math.pi * 4.7 * t)

        s = 0.0
        for h, ha in enumerate(harmonics, start=1):
            s += ha * math.sin(h * phase)
        s *= env
        left[start + i] += s * gl
        right[start + i] += s * gr


def ping_pong(send: list[float], delay_s: float, feedback: float,
              wet: float) -> tuple[list[float], list[float]]:
    """乒乓延时：左右各一条延迟线，互相反馈。"""
    n = len(send)
    d = int(round(delay_s * SR))
    buf_l = [0.0] * d
    buf_r = [0.0] * d
    out_l = [0.0] * n
    out_r = [0.0] * n
    pl = pr = 0
    for i in range(n):
        x = send[i]
        yl = buf_l[pl]
        yr = buf_r[pr]
        buf_l[pl] = x + feedback * yr
        buf_r[pr] = x + feedback * yl
        out_l[i] = yl * wet
        out_r[i] = yr * wet
        pl += 1
        if pl == d:
            pl = 0
        pr += 1
        if pr == d:
            pr = 0
    return out_l, out_r


def reverb(send: list[float], wet: float) -> tuple[list[float], list[float]]:
    """简化的 Schroeder 混响：4 个梳状滤波器 + 2 个全通滤波器。"""
    n = len(send)
    comb_delays = [1249, 1361, 1487, 1601]   # 约 28–36 ms
    combs = [[0.0] * d for d in comb_delays]
    cpos = [0] * len(comb_delays)
    damp_state = [0.0] * len(comb_delays)
    fb = 0.75
    damp = 0.30

    ap_delays = [225, 556]
    aps = [[0.0] * d for d in ap_delays]
    apos = [0] * len(ap_delays)
    ap_g = 0.5
    ap_state = [0.0] * len(ap_delays)

    out_l = [0.0] * n
    out_r = [0.0] * n
    ncomb = len(comb_delays)
    for i in range(n):
        x = send[i]
        acc = 0.0
        for k in range(ncomb):
            buf = combs[k]
            p = cpos[k]
            y = buf[p]
            lp = y * (1.0 - damp) + damp_state[k] * damp
            damp_state[k] = lp
            buf[p] = x + lp * fb
            cpos[k] = 0 if p + 1 == len(buf) else p + 1
            acc += y
        v = acc / ncomb

        for k in range(2):
            buf = aps[k]
            p = apos[k]
            delayed = buf[p]
            y = -ap_g * v + delayed + ap_g * ap_state[k]
            ap_state[k] = y
            buf[p] = v
            apos[k] = 0 if p + 1 == len(buf) else p + 1
            v = y

        out_l[i] = v * wet
        # 右声道晚 11 个采样，制造一点宽度。
        out_r[i] = (out_l[i - 11] if i >= 11 else 0.0)

    return out_l, out_r


def synthesize(timeline: dict) -> tuple[list[float], list[float]]:
    n = int(round(timeline["duration"] * SR)) + 1
    mel_l = [0.0] * n
    mel_r = [0.0] * n
    bass_l = [0.0] * n
    bass_r = [0.0] * n

    for note in timeline["notes"]:
        if note["voice"] == "melody":
            render_tone(
                mel_l, mel_r, note["start"], note["dur"], note["freq"],
                note["amp"], pan=-0.12, release=0.34,
                harmonics=(1.0, 0.22, 0.12, 0.06, 0.03), vibrato=True,
            )
        else:
            render_tone(
                bass_l, bass_r, note["start"], note["dur"], note["freq"],
                note["amp"], pan=0.0, release=0.60,
                harmonics=(1.0, 0.16, 0.05), vibrato=False,
            )

    send = [(mel_l[i] + mel_r[i]) * 0.5 for i in range(n)]
    echo_l, echo_r = ping_pong(send, delay_s=1.5 * EIGHTH,
                               feedback=0.34, wet=0.26)
    rev_l, rev_r = reverb(send, wet=0.30)

    mix_l = [0.0] * n
    mix_r = [0.0] * n
    for i in range(n):
        mix_l[i] = mel_l[i] + bass_l[i] + echo_l[i] + rev_l[i]
        mix_r[i] = mel_r[i] + bass_r[i] + echo_r[i] + rev_r[i]

    # 淡入淡出，避免首尾爆音。
    fade_in = int(0.02 * SR)
    fade_out = int(1.2 * SR)
    for i in range(fade_in):
        g = i / fade_in
        mix_l[i] *= g
        mix_r[i] *= g
    for i in range(fade_out):
        g = i / fade_out
        j = n - 1 - i
        mix_l[j] *= g
        mix_r[j] *= g

    return mix_l, mix_r


def normalize(left: list[float], right: list[float], target=0.891) -> float:
    peak = max(max(abs(x) for x in left), max(abs(x) for x in right))
    if peak == 0:
        raise RuntimeError("音频全为零")
    g = target / peak
    for i in range(len(left)):
        left[i] *= g
        right[i] *= g
    return peak


def write_wav(path: Path, left: list[float], right: list[float]) -> None:
    n = len(left)
    inter = array.array("h", bytes(2 * n * 2))
    li = array.array("h", (int(round(max(-1.0, min(1.0, v)) * 32767))
                           for v in left))
    ri = array.array("h", (int(round(max(-1.0, min(1.0, v)) * 32767))
                           for v in right))
    inter[0::2] = li
    inter[1::2] = ri
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(inter.tobytes())


def main() -> None:
    out = Path(__file__).resolve().parent / "out"
    out.mkdir(parents=True, exist_ok=True)
    timeline = build_timeline()
    print(f"时长 {timeline['duration']:.3f}s，旋律 "
          f"{timeline['counts']['melody']} 音，低音 "
          f"{timeline['counts']['bass']} 音，停顿 "
          f"{[p['seconds'] for p in timeline['pauses']]}")

    left, right = synthesize(timeline)
    peak = normalize(left, right)
    print(f"归一化前峰值 {peak:.3f}")

    wav_path = out / "eaves_rain.wav"
    write_wav(wav_path, left, right)
    with open(out / "timeline.json", "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)
    print(f"写出 {wav_path} ({wav_path.stat().st_size} 字节)")
    print(f"写出 {out / 'timeline.json'}")


if __name__ == "__main__":
    main()
