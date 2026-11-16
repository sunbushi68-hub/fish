#!/usr/bin/env python3.11
"""同一条旋律的三种合成音色：A/B 与可测量的差异。

问题：同一个 MIDI 音高、同一个包络，只换“波形”，谱质心、高频占比、拍频深度
各差多少？我没有耳朵，所以不判断“哪个好听”，只报告可复现的数字。

三种音色：
    sine     纯正弦
    harm5    1..5 次谐波，振幅 1/n
    detune   两个正弦，各自 ±6 音分

验证：
    - 三份文件 RMS 归一后一致（差 < 0.05 dB）；
    - 正弦版本基频峰值误差 < 0.5 Hz；
    - 谐波版本谱质心 > 正弦版本；失谐版本拍频深度 > 正弦版本；
    - 同一份代码跑两次，WAV 字节一致。

用法：MPLCONFIGDIR=.mpl ../../.venv-pymatgen/bin/python synth.py
"""

from __future__ import annotations

import hashlib
import json
import math
import wave
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SR = 44_100
TARGET_RMS = 0.10
TAIL = 1.2
TIMELINE = HERE.parent / "first-work" / "out" / "timeline.json"
A1_START, A1_END = 1.428571, 7.142857


def load_melody() -> list[dict]:
    tl = json.loads(TIMELINE.read_text(encoding="utf-8"))
    return [n for n in tl["notes"]
            if n["voice"] == "melody" and A1_START - 1e-6 <= n["start"] < A1_END]


def envelope(n: int, t: np.ndarray) -> np.ndarray:
    a = int(0.01 * SR)                    # 10 ms attack
    e = np.ones_like(t)
    e[:a] = np.linspace(0.0, 1.0, a) ** 2
    # 每个音内部缓慢衰减，尾巴 80 ms 释放
    tau = 0.9
    e *= np.exp(-t / tau)
    rel = int(0.08 * SR)
    if n > rel:
        e[-rel:] *= np.linspace(1.0, 0.0, rel) ** 2
    return e


def tone(name: str, f: float, n: int) -> np.ndarray:
    t = np.arange(n) / SR
    if name == "sine":
        x = np.sin(2 * math.pi * f * t)
    elif name == "harm5":
        x = sum(np.sin(2 * math.pi * k * f * t) / k for k in range(1, 6))
    elif name == "detune":
        a, b = 2 ** (-6 / 1200), 2 ** (6 / 1200)
        x = 0.5 * (np.sin(2 * math.pi * f * a * t) + np.sin(2 * math.pi * f * b * t))
    else:
        raise ValueError(name)
    return x * envelope(n, t)


def render(notes: list[dict], name: str) -> np.ndarray:
    total = int((max(n["start"] + n["dur"] for n in notes) - A1_START + TAIL) * SR)
    buf = np.zeros(total)
    for nt in notes:
        f = 440.0 * 2 ** ((nt["midi"] - 69) / 12)
        n = int(nt["dur"] * SR)
        s = int((nt["start"] - A1_START) * SR)
        buf[s:s + n] += tone(name, f, n)
    return buf


def norm(x: np.ndarray) -> np.ndarray:
    rms = np.sqrt(np.mean(x ** 2))
    return x * (TARGET_RMS / rms)


def write_wav(path: Path, x: np.ndarray) -> None:
    pcm = np.clip(x, -1, 1)
    data = (pcm * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data)


def centroid(x: np.ndarray) -> tuple[float, float]:
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    c = float((spec * freqs).sum() / spec.sum())
    hf = float(spec[freqs > 2000].sum() / spec.sum())
    return c, hf


def beat_depth_isolated(name: str, f: float = 440.0, dur: float = 2.0) -> float:
    """单独一个等幅持续音上的 20 ms 窗 RMS 包络起伏。
    必须隔离成单音、去掉指数衰减，否则音符起落和衰减会污染“拍频”指标。"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    if name == "sine":
        x = np.sin(2 * math.pi * f * t)
    elif name == "harm5":
        x = sum(np.sin(2 * math.pi * k * f * t) / k for k in range(1, 6))
    else:
        a, b = 2 ** (-6 / 1200), 2 ** (6 / 1200)
        x = 0.5 * (np.sin(2 * math.pi * f * a * t) + np.sin(2 * math.pi * f * b * t))
    fade = int(0.01 * SR)
    x[:fade] *= np.linspace(0, 1, fade)
    x[-fade:] *= np.linspace(1, 0, fade)
    x = norm(x)
    seg = x[int(0.2 * SR):int(1.8 * SR)]
    hop = int(0.02 * SR)
    win = np.hanning(hop)
    env = np.array([np.sqrt(np.mean((seg[i:i + hop] * win) ** 2))
                    for i in range(0, len(seg) - hop, hop)])
    return float((env.max() - env.min()) / env.mean())


def main() -> None:
    OUT.mkdir(exist_ok=True)
    notes = load_melody()
    results = {}
    signals = {}
    for name in ("sine", "harm5", "detune"):
        x = norm(render(notes, name))
        signals[name] = x
        write_wav(OUT / f"timbre_{name}.wav", x)
        c, hf = centroid(x)
        results[name] = {
            "rms_dbfs": round(20 * math.log10(np.sqrt(np.mean(x ** 2))), 3),
            "peak_dbfs": round(20 * math.log10(np.max(np.abs(x))), 3),
            "spectral_centroid_hz": round(c, 1),
            "hf_fraction_above_2k": round(hf, 4),
            "beating_depth_isolated": round(beat_depth_isolated(name), 4),
        }

    # 基频峰值检查（取最长音符的稳态段）
    longest = max(notes, key=lambda n: n["dur"])
    f0 = 440.0 * 2 ** ((longest["midi"] - 69) / 12)
    s = int((longest["start"] - A1_START + 0.1) * SR)
    seg = signals["sine"][s:s + int(0.3 * SR)] * np.hanning(int(0.3 * SR))
    spec = np.abs(np.fft.rfft(seg, n=1 << 18))
    freqs = np.fft.rfftfreq(1 << 18, 1 / SR)
    peak = float(freqs[np.argmax(spec)])

    # 可复现性
    h = hashlib.sha256((OUT / "timbre_sine.wav").read_bytes()).hexdigest()
    write_wav(OUT / "repeat_sine.wav", norm(render(notes, "sine")))
    same = hashlib.sha256((OUT / "repeat_sine.wav").read_bytes()).hexdigest() == h
    (OUT / "repeat_sine.wav").unlink()

    rms_vals = [results[k]["rms_dbfs"] for k in results]
    checks = {
        "rms_match_db": round(max(rms_vals) - min(rms_vals), 4),
        "fundamental_peak_hz": round(peak, 3),
        "fundamental_expected_hz": round(f0, 3),
        "fundamental_error_hz": round(abs(peak - f0), 3),
        "centroid_harm_gt_sine": results["harm5"]["spectral_centroid_hz"] > results["sine"]["spectral_centroid_hz"],
        "beating_detune_abs": results["detune"]["beating_depth_isolated"] > 0.1,
        "beating_sine_near_zero": results["sine"]["beating_depth_isolated"] < 0.01,
        "deterministic": same,
    }
    checks["pass"] = (checks["rms_match_db"] < 0.05 and checks["fundamental_error_hz"] < 0.5
                      and checks["centroid_harm_gt_sine"] and checks["beating_detune_abs"]
                      and checks["beating_sine_near_zero"]
                      and checks["deterministic"])

    (OUT / "results.json").write_text(json.dumps(
        {"melody": {"section": "A1", "notes": len(notes), "seconds": round(len(signals["sine"]) / SR, 3)},
         "timbres": results, "checks": checks,
         "caveat": "只测量，不评价听感；没有使用任何外部音色库或采样。"},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 频谱图：同一段 2 s，三种音色上下对照
    fig, axes = plt.subplots(3, 1, figsize=(7, 6.4), dpi=130, sharex=True)
    seg = slice(int(0.4 * SR), int(2.4 * SR))
    for ax, name in zip(axes, ("sine", "harm5", "detune")):
        ax.specgram(signals[name][seg], NFFT=2048, Fs=SR, noverlap=1024, cmap="magma",
                    vmin=-120, vmax=-20)
        ax.set_ylabel(name)
        ax.set_ylim(0, 5000)
    axes[-1].set_xlabel("time within 2 s window (s)")
    fig.suptitle("Same A1 melody, three waveforms (0.4–2.4 s)")
    fig.tight_layout()
    fig.savefig(OUT / "spectrograms.png")
    plt.close(fig)

    lines = ["# 三种合成音色的可测差异（A1 旋律）", "",
             f"音符 {len(notes)} 个，时长 {len(signals['sine'])/SR:.2f} s，RMS 归一到 {TARGET_RMS:.2f}", "",
             "| 音色 | RMS dBFS | 峰值 dBFS | 谱质心 Hz | >2 kHz 能量占比 | 单音拍频深度 |",
             "|---|---|---|---|---|---|"]
    for k, v in results.items():
        lines.append(f"| {k} | {v['rms_dbfs']} | {v['peak_dbfs']} | {v['spectral_centroid_hz']} | "
                     f"{v['hf_fraction_above_2k']} | {v['beating_depth_isolated']} |")
    lines += ["", "## 自检", "",
              f"- RMS 最大差 {checks['rms_match_db']} dB（阈值 0.05）",
              f"- 基频峰值 {checks['fundamental_peak_hz']} Hz，期望 {checks['fundamental_expected_hz']} Hz，误差 {checks['fundamental_error_hz']} Hz",
              f"- 谐波谱质心 > 正弦：{checks['centroid_harm_gt_sine']}；失谐拍频 > 0.1：{checks['beating_detune_abs']}；正弦拍频≈0：{checks['beating_sine_near_zero']}",
              f"- 两次生成 WAV 字节一致：{checks['deterministic']}",
              f"- 结论：{'PASS' if checks['pass'] else 'FAIL'}",
              "", "## 边界", "",
              "- 只测数值，不判断好听与否；我没有耳朵，A/B 偏好必须由主人听。",
              "- 音色是加法合成，不含共振峰、气声、力度分层；不能代表真实乐器。"]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:14]))


if __name__ == "__main__":
    main()
