#!/usr/bin/env python3.11
"""把 out/timeline.json 导出成标准 MIDI 文件，并用一个独立的字节级解析器回读验证。

只依赖标准库：写 SMF（format 1，PPQ=480），再用 parser() 解回来逐音比对，
证明“导出的 MIDI 与时间线一致”，而不是只证明脚本没报错。

用法：
    python3.11 midi.py
产物：
    out/eaves_rain.mid
    out/midi_verification.txt / .json
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
PPQ = 480
VOICE_CHANNEL = {"melody": 0, "bass": 1}


# ---------------------------------------------------------------- 写 SMF

def vlq(n: int) -> bytes:
    if n < 0:
        raise ValueError("negative delta")
    buf = [n & 0x7F]
    n >>= 7
    while n:
        buf.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(buf))


def meta(kind: int, payload: bytes) -> bytes:
    return b"\xff" + bytes([kind]) + vlq(len(payload)) + payload


def build_midi(tl: dict) -> tuple[bytes, int]:
    """返回 (SMF 字节, 每个 tick 的秒数 * 1e6)。"""
    quarter_s = 2.0 * tl["tempo"]["eighth_seconds"]      # 6/8 里一拍 = 四分音符
    tick_s = quarter_s / PPQ
    tempo_us = round(quarter_s * 1_000_000)

    # 轨道 0：曲名 / 速度 / 拍号
    t0 = b""
    t0 += vlq(0) + meta(0x03, tl["title"].encode("utf-8"))
    t0 += vlq(0) + meta(0x51, tempo_us.to_bytes(3, "big"))
    t0 += vlq(0) + meta(0x58, bytes([6, 3, 24, 8]))       # 6/8
    t0 += vlq(0) + meta(0x2F, b"")

    tracks = [t0]
    for voice, channel in VOICE_CHANNEL.items():
        events = []                                       # (tick, order, bytes)
        for n in tl["notes"]:
            if n["voice"] != voice:
                continue
            on = round(n["start"] / tick_s)
            off = round((n["start"] + n["dur"]) / tick_s)
            vel = max(1, min(127, round(n.get("amp", 0.5) * 127)))
            events.append((on, 1, bytes([0x90 | channel, n["midi"], vel])))
            events.append((off, 0, bytes([0x80 | channel, n["midi"], 64])))
        events.sort()

        body = vlq(0) + meta(0x03, voice.encode())
        body += vlq(0) + bytes([0xC0 | channel, 0])
        last = 0
        for tick, _, msg in events:
            body += vlq(tick - last) + msg
            last = tick
        body += vlq(0) + meta(0x2F, b"")
        tracks.append(body)

    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), PPQ)
    return header + b"".join(b"MTrk" + struct.pack(">I", len(t)) + t for t in tracks), tick_s


# ---------------------------------------------------------------- 读 SMF（独立实现）

def read_vlq(data: bytes, i: int) -> tuple[int, int]:
    value = 0
    while True:
        b = data[i]
        i += 1
        value = (value << 7) | (b & 0x7F)
        if not b & 0x80:
            return value, i


def parse(data: bytes) -> dict:
    if data[:4] != b"MThd":
        raise ValueError("no MThd")
    hlen, fmt, ntrks, div = struct.unpack(">IHHH", data[4:14])
    assert hlen == 6 and fmt == 1 and div == PPQ, (hlen, fmt, div)
    pos = 14
    tempo_us = None
    notes = []                                            # (chan, pitch, on_tick, off_tick)
    names = []
    for _ in range(ntrks):
        assert data[pos:pos + 4] == b"MTrk"
        (length,) = struct.unpack(">I", data[pos + 4:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        pos += 8 + length
        i = 0
        tick = 0
        status = None
        open_notes = {}
        while i < len(chunk):
            delta, i = read_vlq(chunk, i)
            tick += delta
            b = chunk[i]
            if b == 0xFF:
                kind = chunk[i + 1]
                ln, j = read_vlq(chunk, i + 2)
                payload = chunk[j:j + ln]
                if kind == 0x51:
                    tempo_us = int.from_bytes(payload, "big")
                elif kind == 0x03:
                    names.append(payload.decode("utf-8"))
                i = j + ln
                if kind == 0x2F:
                    break
                continue
            if b & 0x80:
                status = b
                i += 1
            hi, chan = status & 0xF0, status & 0x0F
            if hi in (0x80, 0x90):
                pitch, vel = chunk[i], chunk[i + 1]
                i += 2
                if hi == 0x90 and vel > 0:
                    open_notes[(chan, pitch)] = tick
                else:
                    on = open_notes.pop((chan, pitch))
                    notes.append((chan, pitch, on, tick))
            elif hi == 0xC0:
                i += 1
            else:
                raise ValueError(f"unexpected status {status:#x}")
        assert not open_notes, f"unclosed notes: {open_notes}"
    notes.sort()
    return {"tempo_us": tempo_us, "notes": notes, "track_names": names}


# ---------------------------------------------------------------- 主流程

def main() -> None:
    tl = json.loads((OUT / "timeline.json").read_text(encoding="utf-8"))
    data, tick_s = build_midi(tl)
    again, _ = build_midi(json.loads((OUT / "timeline.json").read_text(encoding="utf-8")))
    deterministic = hashlib.sha256(data).hexdigest() == hashlib.sha256(again).hexdigest()
    (OUT / "eaves_rain.mid").write_bytes(data)

    got = parse(data)
    expected = round(2.0 * tl["tempo"]["eighth_seconds"] * 1_000_000)
    want = []
    for n in tl["notes"]:
        on = round(n["start"] / tick_s)
        off = round((n["start"] + n["dur"]) / tick_s)
        want.append((VOICE_CHANNEL[n["voice"]], n["midi"], on, off))
    want.sort()

    diffs = []
    assert len(got["notes"]) == len(want), (len(got["notes"]), len(want))
    for a, b in zip(got["notes"], want):
        if a[:2] != b[:2] or abs(a[2] - b[2]) > 1 or abs(a[3] - b[3]) > 1:
            diffs.append({"got": a, "want": b})

    report = {
        "midi_sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "deterministic": deterministic,
        "format": 1,
        "ppq": PPQ,
        "tempo_us_per_quarter": got["tempo_us"],
        "tempo_expected": expected,
        "tracks": len(got["track_names"]),
        "note_count": len(got["notes"]),
        "note_count_expected": len(tl["notes"]),
        "max_tick_error_allowed": 1,
        "mismatches": diffs,
        "track_names": got["track_names"],
        "pass": deterministic and not diffs and got["tempo_us"] == expected,
    }
    (OUT / "midi_verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "MIDI 回读验证",
        f"sha256: {report['midi_sha256']}",
        f"字节数: {report['bytes']}",
        f"两次生成字节一致: {deterministic}",
        f"tempo: {got['tempo_us']} us/四分音符 (期望 {expected})",
        f"音符数: {len(got['notes'])} / 时间线 {len(tl['notes'])}",
        f"起点与时长最大容差: ±1 tick (±{tick_s * 1000:.3f} ms)",
        f"不匹配: {len(diffs)}",
        f"结论: {'PASS' if report['pass'] else 'FAIL'}",
    ]
    (OUT / "midi_verification.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
