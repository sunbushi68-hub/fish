#!/usr/bin/env python3.11
"""对《檐下雨》做独立验证：只读 WAV 与 timeline.json，不导入 piece.py。

验证内容：
  1. 手工解析 RIFF/WAVE 头，确认 PCM、双声道、44.1 kHz、16 bit；
  2. 时长与时间线一致，无削波，直流偏移可忽略；
  3. 用 Goertzel 在 ±60 音分内扫频，核对 10 个音的实际音高；
  4. 量出每次停顿内最安静的 100 ms，相对前一段音乐下降了多少 dB。

用法：python3.11 verify.py    （全部通过退出码 0，否则 1）
"""

from __future__ import annotations

import array
import json
import math
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SR_EXPECTED = 44_100


def parse_riff(path: Path) -> dict:
    raw = path.read_bytes()
    if raw[0:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("不是 RIFF/WAVE 文件")
    riff_size = struct.unpack("<I", raw[4:8])[0]
    chunks = {}
    off = 12
    while off + 8 <= len(raw):
        cid = raw[off:off + 4]
        size = struct.unpack("<I", raw[off + 4:off + 8])[0]
        chunks[cid] = raw[off + 8:off + 8 + size]
        off += 8 + size + (size & 1)
    fmt = struct.unpack("<HHIIHH", chunks[b"fmt "][:16])
    return {
        "riff_size_ok": riff_size == len(raw) - 8,
        "audio_format": fmt[0],
        "channels": fmt[1],
        "sample_rate": fmt[2],
        "byte_rate": fmt[3],
        "block_align": fmt[4],
        "bits": fmt[5],
        "data_bytes": len(chunks[b"data"]),
        "raw": chunks[b"data"],
    }


def load_mono(info: dict) -> tuple[list[float], list[float], list[float]]:
    data = array.array("h")
    data.frombytes(info["raw"])
    if sys.byteorder == "big":
        data.byteswap()
    ch = info["channels"]
    left = [data[i] / 32768.0 for i in range(0, len(data), ch)]
    right = [data[i + 1] / 32768.0 for i in range(0, len(data), ch)]
    mono = [(l + r) / 2.0 for l, r in zip(left, right)]
    return mono, left, right


def goertzel_power(seg: list[float], freq: float, sr: int) -> float:
    w = 2.0 * math.pi * freq / sr
    coeff = 2.0 * math.cos(w)
    s0 = s1 = s2 = 0.0
    for x in seg:
        s0 = x + coeff * s1 - s2
        s2 = s1
        s1 = s0
    return s1 * s1 + s2 * s2 - coeff * s1 * s2


def measure_pitch(mono: list[float], start: float, expected: float) -> dict:
    """在 expected ±60 音分内以 1 音分为步长找谱峰。"""
    n = 8192
    a = int(round((start + 0.12) * SR_EXPECTED))
    seg = mono[a:a + n]
    seg = [x * (0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)))
           for i, x in enumerate(seg)]
    best_f, best_p = None, -1.0
    cents = -60.0
    while cents <= 60.0001:
        f = expected * 2.0 ** (cents / 1200.0)
        p = goertzel_power(seg, f, SR_EXPECTED)
        if p > best_p:
            best_f, best_p = f, p
        cents += 1.0
    # 用抛物线在相邻三点上细化（再扫一遍邻点）。
    step = 1.0
    f_lo = best_f * 2.0 ** (-step / 1200.0)
    f_hi = best_f * 2.0 ** (step / 1200.0)
    p_lo = goertzel_power(seg, f_lo, SR_EXPECTED)
    p_hi = goertzel_power(seg, f_hi, SR_EXPECTED)
    if p_lo < best_p and p_hi < best_p:
        denom = p_lo - 2 * best_p + p_hi
        if abs(denom) > 1e-18:
            delta = 0.5 * (p_lo - p_hi) / denom
            best_f *= 2.0 ** (delta * step / 1200.0)
    err_cents = 1200.0 * math.log2(best_f / expected)
    return {"expected_hz": round(expected, 3), "measured_hz": round(best_f, 3),
            "error_cents": round(err_cents, 2), "power": best_p}


def frame_rms(mono: list[float], win: int = 2048, hop: int = 1024) -> tuple[list[float], list[float]]:
    out_t, out_r = [], []
    for a in range(0, len(mono) - win, hop):
        acc = 0.0
        for x in mono[a:a + win]:
            acc += x * x
        out_t.append(a / SR_EXPECTED)
        out_r.append(math.sqrt(acc / win))
    return out_t, out_r


def quietest_window(mono: list[float], start: float, end: float,
                    win: float) -> float:
    """在 [start, end] 内滑动 100 ms 窗，返回最低 RMS。"""
    step = 0.025
    best = float("inf")
    t = start
    while t + win <= end + 1e-9:
        a = int(t * SR_EXPECTED)
        b = int((t + win) * SR_EXPECTED)
        seg = mono[a:b]
        if seg:
            rms = math.sqrt(sum(x * x for x in seg) / len(seg))
            best = min(best, rms)
        t += step
    return 0.0 if best == float("inf") else best


def db(x: float) -> float:
    return 20.0 * math.log10(max(x, 1e-12))


def median(xs: list[float]) -> float:
    xs = sorted(xs)
    if not xs:
        return 0.0
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def main() -> int:
    checks = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    timeline = json.loads((OUT / "timeline.json").read_text(encoding="utf-8"))
    info = parse_riff(OUT / "eaves_rain.wav")
    mono, left, right = load_mono(info)

    check("RIFF 头长度自洽", info["riff_size_ok"],
          "RIFF size == 文件长度 − 8")
    check("PCM / 双声道 / 44.1 kHz / 16 bit",
          info["audio_format"] == 1 and info["channels"] == 2
          and info["sample_rate"] == SR_EXPECTED and info["bits"] == 16,
          f"fmt={info['audio_format']}, ch={info['channels']}, "
          f"sr={info['sample_rate']}, bits={info['bits']}")
    check("block_align 与 byte_rate 自洽",
          info["block_align"] == info["channels"] * info["bits"] // 8
          and info["byte_rate"] == info["sample_rate"] * info["block_align"],
          f"block_align={info['block_align']}, byte_rate={info['byte_rate']}")

    frames = info["data_bytes"] // info["block_align"]
    wav_dur = frames / info["sample_rate"]
    check("WAV 时长与时间线一致",
          abs(wav_dur - timeline["duration"]) < 0.01,
          f"WAV {wav_dur:.4f}s vs 时间线 {timeline['duration']:.4f}s")

    peak = max(max(abs(x) for x in left), max(abs(x) for x in right))
    rms = math.sqrt(sum(x * x for x in mono) / len(mono))
    dc = sum(mono) / len(mono)
    check("峰值接近 −1 dBFS 且未削波",
          0.85 <= peak <= 0.90,
          f"峰值 {peak:.4f}（{db(peak):.2f} dBFS）")
    check("整体响度合理、直流偏移可忽略",
          -24.0 < db(rms) < -12.0 and abs(dc) < 1e-4,
          f"RMS {db(rms):.2f} dBFS, DC {dc:.2e}")

    # ---- 音高
    picks = [(1, "melody"), (3, "melody"), (6, "melody"), (9, "melody"),
             (11, "melody"), (12, "melody"), (13, "melody"), (16, "melody"),
             (0, "bass"), (10, "bass")]
    pitch_rows = []
    for bar, voice in picks:
        note = next(n for n in timeline["notes"]
                    if n["bar"] == bar and n["voice"] == voice)
        row = measure_pitch(mono, note["start"], note["freq"])
        row.update({"bar": bar, "name": note["name"], "voice": voice})
        pitch_rows.append(row)
    worst = max(abs(r["error_cents"]) for r in pitch_rows)
    check("10 个抽查音的音高误差 ≤ 20 音分", worst <= 20.0,
          f"最大误差 {worst:.2f} 音分；"
          + ", ".join(f"{r['name']}{r['error_cents']:+.1f}" for r in pitch_rows))

    # ---- 停顿
    times, levels = frame_rms(mono)
    pause_rows = []
    for i, p in enumerate(timeline["pauses"], start=1):
        ref = median([lvl for t, lvl in zip(times, levels)
                      if p["start"] - 1.0 <= t < p["start"] - 0.05])
        quiet = quietest_window(mono, p["start"] + 0.02, p["end"], 0.10)
        drop = db(ref) - db(quiet)
        pause_rows.append({"index": i, "seconds": p["seconds"],
                           "ref_dbfs": round(db(ref), 2),
                           "quiet_dbfs": round(db(quiet), 2),
                           "drop_db": round(drop, 2)})
    check("每次停顿内最安静的 100 ms 比前段音乐至少低 8 dB",
          all(r["drop_db"] >= 8.0 for r in pause_rows),
          "; ".join(f"停顿{r['index']} {r['seconds']}s 降 {r['drop_db']:.1f} dB"
                    for r in pause_rows))
    check("停顿长度递增（0.4 < 0.9 < 1.6 s）",
          [p["seconds"] for p in timeline["pauses"]] == [0.4, 0.9, 1.6],
          str([p["seconds"] for p in timeline["pauses"]]))

    # ---- 时间线自洽
    last = max(n["start"] + n["dur"] for n in timeline["notes"])
    check("所有音符落在曲长内，末尾留有混响尾巴",
          last < timeline["duration"] - 1.0,
          f"最后音符结束 {last:.2f}s，曲长 {timeline['duration']:.2f}s")
    check("停顿时段不与音符重叠",
          all(not any(n["start"] < p["end"] - 1e-6
                      and n["start"] + n["dur"] > p["start"] + 1e-6
                      for n in timeline["notes"])
              for p in timeline["pauses"]),
          "停顿区间内无音符起点/时值重叠")

    ok = all(c["ok"] for c in checks)
    report = {
        "piece": timeline["title"],
        "wav_duration_s": round(wav_dur, 4),
        "peak_dbfs": round(db(peak), 2),
        "rms_dbfs": round(db(rms), 2),
        "pitch_checks": pitch_rows,
        "pause_checks": pause_rows,
        "checks": checks,
        "all_passed": ok,
    }
    (OUT / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"《{timeline['title']}》验证报告", "=" * 46]
    for c in checks:
        lines.append(f"[{'PASS' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
    lines += ["", "音高抽查："]
    for r in pitch_rows:
        lines.append(f"  第{r['bar']:>2}小节 {r['name']:<3} "
                     f"{r['expected_hz']:>8.2f} Hz → {r['measured_hz']:>8.2f} Hz "
                     f"({r['error_cents']:+.2f} 音分)")
    lines += ["", "停顿："]
    for r in pause_rows:
        lines.append(f"  停顿{r['index']} {r['seconds']}s：前段 {r['ref_dbfs']:.1f} dBFS，"
                     f"最静 100ms {r['quiet_dbfs']:.1f} dBFS，降 {r['drop_db']:.1f} dB")
    lines += ["", f"结论：{'全部通过' if ok else '存在失败项'}"]
    text = "\n".join(lines) + "\n"
    (OUT / "verification.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
