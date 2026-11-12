#!/usr/bin/env python3.11
"""对称性判定到底能“容忍”多大的畸变？——用 SrTiO3 立方钙钛矿做一个有界的数值实验。

问题（只此一个）：
    SpacegroupAnalyzer 给出的空间群，随着 symprec（Å）变化，在多大的
    真实畸变下会从 Pm-3m 变成别的群？阈值是否就等于 symprec 本身？

模型（不是实验数据，是构造出来的周期性 Structure，单位 Å、度）：
    SrTiO3 立方钙钛矿，a0 = 3.905 Å（文献常用室温值，本轮未联网核对，
    仅作为输入假设；结论只依赖“阈值 ~ symprec”这一量纲关系）。
      Sr (0.5,0.5,0.5)  Ti (0,0,0)  O (0.5,0,0) (0,0.5,0) (0,0,0.5)

两种畸变：
    A. 轴向应变 s：c = a0(1+s)，预期降到 P4/mmm；
    B. 顶点氧沿 z 位移 d（Å），预期降到 P4mm。

网格：symprec ∈ {1e-5 … 1e-1} Å，angle_tolerance = 5°，6 个振幅 × 2 种畸变
= 60 次判定；另做 4 次切应变检查 angle_tolerance 的作用。

用法：
    MPLCONFIGDIR=.mpl .venv-pymatgen/bin/python analysis.py
产物：
    out/results.json、out/summary.md、out/boundary.png
"""

from __future__ import annotations

import json
import platform
from importlib.metadata import version
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pymatgen.core import Lattice, Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
A0 = 3.905                     # Å
SPECIES = ["Sr", "Ti", "O", "O", "O"]
FRAC = [[0.5, 0.5, 0.5], [0.0, 0.0, 0.0], [0.5, 0.0, 0.0], [0.0, 0.5, 0.0], [0.0, 0.0, 0.5]]
SYMPREC = [1e-5, 1e-4, 1e-3, 1e-2, 1e-1]
STRAINS = [0.0, 1e-5, 1e-4, 1e-3, 3e-3, 1e-2]
DISPLACEMENTS = [0.0, 1e-4, 1e-3, 3e-3, 1e-2, 3e-2]
ANGLE_TOL = 5.0


def cubic() -> Lattice:
    return Lattice.cubic(A0)


def strained(s: float) -> Structure:
    lat = Lattice.from_parameters(A0, A0, A0 * (1.0 + s), 90.0, 90.0, 90.0)
    return Structure(lat, SPECIES, FRAC, coords_are_cartesian=False)


def displaced(d: float) -> Structure:
    frac = [list(f) for f in FRAC]
    frac[4][2] = 0.5 + d / A0          # 顶点氧沿 z 方向移动 d 埃
    return Structure(cubic(), SPECIES, frac, coords_are_cartesian=False)


def group(struct: Structure, symprec: float, angle_tolerance: float = ANGLE_TOL) -> str:
    return SpacegroupAnalyzer(struct, symprec=symprec, angle_tolerance=angle_tolerance).get_space_group_symbol()


def sweep(builder, values, unit: str) -> dict:
    rows = []
    for symprec in SYMPREC:
        symbols = [group(builder(v), symprec) for v in values]
        high = symbols[0]
        first_break = next((v for v, s in zip(values, symbols) if s != high), None)
        rows.append({
            "symprec_A": symprec,
            "symbols": symbols,
            "high_symmetry": high,
            "first_break_at": first_break,
            "predicted_break_at": symprec if unit == "A" else symprec / A0,
        })
    return {"unit": unit, "values": values, "rows": rows}


def main() -> None:
    strain = sweep(strained, STRAINS, "relative")
    disp = sweep(displaced, DISPLACEMENTS, "A")

    # 切应变：唯一角度变成 90+γ，看 angle_tolerance 是否重要
    shear = []
    for gamma in [0.01, 0.1, 1.0, 5.0]:
        lat = Lattice.from_parameters(A0, A0, A0, 90.0, 90.0, 90.0 + gamma)
        st = Structure(lat, SPECIES, FRAC)
        shear.append({"gamma_deg": gamma,
                      "symbol_symprec_1e-3": group(st, 1e-3),
                      "symbol_symprec_1e-2_at_1deg": group(st, 1e-2, 1.0)})

    # 粗网格只能给出“区间”，用二分把阈值收紧到 0.1%
    def bisect(builder, symprec: float) -> dict | None:
        lo, hi = symprec * 0.1, symprec * 10.0
        if group(builder(lo), symprec) != "Pm-3m" or group(builder(hi), symprec) == "Pm-3m":
            return None
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if group(builder(mid), symprec) != "Pm-3m":
                hi = mid
            else:
                lo = mid
            if hi - lo <= 1e-3 * hi:
                break
        return {"lo": lo, "hi": hi, "mid": 0.5 * (lo + hi)}

    refined = {"displacement": {}, "strain": {}}
    for sp in (1e-4, 1e-3, 1e-2):
        refined["displacement"][f"{sp:g}"] = bisect(displaced, sp)
        refined["strain"][f"{sp:g}"] = bisect(strained, sp)
    disp_ratios = [v["mid"] / float(k) for k, v in refined["displacement"].items() if v]
    strain_ratios = [v["mid"] / (float(k) / A0) for k, v in refined["strain"].items() if v]

    results = {
        "question": "空间群判定的畸变阈值是否与 symprec 同量级？",
        "structure": {"formula": "SrTiO3", "a0_A": A0, "source": "构造的周期性 Structure，a0 为文献常用值，未联网核对"},
        "parameters": {"symprec_A": SYMPREC, "angle_tolerance_deg": ANGLE_TOL,
                       "strain_values": STRAINS, "displacement_A": DISPLACEMENTS},
        "strain_probe": strain,
        "displacement_probe": disp,
        "shear_probe": shear,
        "threshold_over_symprec": {"displacement_mean": float(np.mean(disp_ratios)) if disp_ratios else None,
                                   "displacement_std": float(np.std(disp_ratios)) if disp_ratios else None,
                                   "strain_mean": float(np.mean(strain_ratios)) if strain_ratios else None,
                                   "strain_std": float(np.std(strain_ratios)) if strain_ratios else None},
        "refined_thresholds": refined,
        "grid_note": "粗网格 6 个振幅只能确定阈值所在区间；refined_thresholds 为二分收紧后的结果。",
        "software": {"python": platform.python_version(), "pymatgen": version("pymatgen-core"),
                     "spglib": version("spglib"), "numpy": np.__version__},
        "caveat": "全部为构造结构与几何判定，不是合成、不是实验、不是 Materials Project 数据。",
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 图：每个 symprec 下第一次“掉出高对称”的振幅
    fig, ax = plt.subplots(figsize=(6, 4.2), dpi=140)
    xs = [r["symprec_A"] for r in disp["rows"] if r["first_break_at"]]
    ys = [r["first_break_at"] for r in disp["rows"] if r["first_break_at"]]
    ax.loglog(xs, ys, "o-", label="measured (O displacement)")
    ax.loglog([1e-5, 1e-1], [1e-5, 1e-1], "--", color="gray", label="y = symprec")
    ax.set_xlabel("symprec (Å)")
    ax.set_ylabel("first breaking displacement d (Å)")
    ax.set_title("SrTiO3: symmetry tolerance vs. real distortion")
    ax.legend()
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "boundary.png")
    plt.close(fig)

    lines = ["# 对称性容差实验（SrTiO3，构造结构）", "",
             f"软件：pymatgen-core {results['software']['pymatgen']} / spglib {results['software']['spglib']} / Python {results['software']['python']}",
             f"角度容差固定 {ANGLE_TOL}°，a0 = {A0} Å（输入假设）", "",
             "## 位移探针：顶点氧移动 d", "",
             "| symprec (Å) | " + " | ".join(f"d={d:g}" for d in DISPLACEMENTS) + " |",
             "|---|" + "---|" * len(DISPLACEMENTS)]
    for r in disp["rows"]:
        lines.append(f"| {r['symprec_A']:g} | " + " | ".join(r["symbols"]) + " |")
    lines += ["", "## 应变探针：c = a0(1+s)", "",
              "| symprec (Å) | " + " | ".join(f"s={s:g}" for s in STRAINS) + " |",
              "|---|" + "---|" * len(STRAINS)]
    for r in strain["rows"]:
        lines.append(f"| {r['symprec_A']:g} | " + " | ".join(r["symbols"]) + " |")
    lines += ["", "## 切应变（angle_tolerance 的作用）", ""]
    for s in shear:
        lines.append(f"- γ={s['gamma_deg']:g}° → symprec=1e-3, atol=5°: {s['symbol_symprec_1e-3']}；"
                     f"symprec=1e-2, atol=1°: {s['symbol_symprec_1e-2_at_1deg']}")
    lines += ["", "## 二分收紧后的阈值（每次判定都是新构造的结构）", "",
              "| symprec (Å) | 位移阈值 d* (Å) | d*/symprec | 应变阈值 s* | s*·a0/symprec |",
              "|---|---|---|---|---|"]
    for k in refined["displacement"]:
        d = refined["displacement"][k]
        st_ = refined["strain"][k]
        lines.append(f"| {k} | {d['mid']:.6g} | {d['mid'] / float(k):.3f} | "
                     f"{st_['mid']:.3g} | {st_['mid'] * A0 / float(k):.3f} |")
    lines += ["", "## 读法", "",
              f"- 位移阈值 / symprec：{results['threshold_over_symprec']['displacement_mean']:.2f} "
              f"± {results['threshold_over_symprec']['displacement_std']:.2f}（3 个 symprec 的二分结果）",
              f"- 应变阈值换算成绝对长度后 / symprec：{results['threshold_over_symprec']['strain_mean']:.2f} "
              f"± {results['threshold_over_symprec']['strain_std']:.2f}",
              "- 粗网格得到的 1–10 倍散布主要是采样分辨率造成的，不能当成物理常数；二分后倍数大致稳定。",
              "- 高于阈值时 Pm-3m 只是容差把畸变吃掉了，不是结构真的立方；低于阈值才被识别为 P4mm/P4/mmm。",
              "- 这是几何与数值判定，不是实验结论；a0 未经本轮文献核对。"]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:14]))
    print("... threshold/symprec =", results["threshold_over_symprec"])


if __name__ == "__main__":
    main()
