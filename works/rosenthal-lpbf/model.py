#!/usr/bin/env python3.11
"""LPBF 熔池的 Rosenthal 解析基线：模型能给出什么、又在哪失效。

只问一件事：把激光当成匀速移动的点热源、只靠体导热，算出来的熔池
深度/宽度/长度有多大？先保证实现正确（用可解析的极限做自检），再谈
它和真实熔池的关系——后者本轮不核对文献，不下“偏大/偏小”的结论。

模型（Rosenthal 1946，点源、准稳态、各向同性、无对流、无相变潜热）：
    T(x,y,z) = T0 + ηP/(2πkR) · exp(-v(R+x)/(2α)),  R = √(x²+y²+z²)
    源沿 +x 移动；熔池边界取 T = Tm。
产物：
    out/results.json、out/summary.md、out/map.png
"""

from __future__ import annotations

import json
import math
import platform
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

# Ti-6Al-4V 常用近似值（本轮未逐条核对文献；结论只依赖这些输入和图内关系）
MAT = {"k_W_mK": 7.0, "rho_kg_m3": 4430.0, "cp_J_kgK": 560.0,
       "Tm_K": 1923.0, "T0_K": 298.0, "absorptivity": 0.4}
ALPHA = MAT["k_W_mK"] / (MAT["rho_kg_m3"] * MAT["cp_J_kgK"])
DT = MAT["Tm_K"] - MAT["T0_K"]


def temp(P: float, v: float, x, y, z):
    """K。P 为激光功率 W，v 为扫描速度 m/s。"""
    R = np.sqrt(x * x + y * y + z * z)
    with np.errstate(divide="ignore", invalid="ignore"):
        return MAT["T0_K"] + MAT["absorptivity"] * P / (2 * math.pi * MAT["k_W_mK"] * R) * np.exp(
            -v * (R + x) / (2 * ALPHA))


def solve_depth(P: float, v: float) -> float:
    """沿 -z 找 T=Tm 的深度（米）。"""
    f = lambda d: temp(P, v, 0.0, 0.0, -d) - MAT["Tm_K"]
    lo, hi = 1e-7, 5e-2
    if f(hi) > 0:
        return float("nan")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def main() -> None:
    checks = {}
    P0, v0 = 200.0, 1.0

    # 1) v=0 时熔池是球，半径有闭式：R = ηP/(2πk·ΔT)
    r0_num = solve_depth(P0, 0.0)
    r0_ana = MAT["absorptivity"] * P0 / (2 * math.pi * MAT["k_W_mK"] * DT)
    checks["v0_sphere_radius"] = {"numeric_m": r0_num, "analytic_m": r0_ana,
                                   "rel_error": abs(r0_num - r0_ana) / r0_ana}

    # 2) 熔池尾部长度有闭式：L = ηP/(2πk·ΔT)（x<0 处指数因子=1）
    def rear_length(P, v):
        f = lambda x: temp(P, v, -x, 0.0, 0.0) - MAT["Tm_K"]
        lo, hi = 1e-7, 5e-2
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if f(mid) > 0:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)
    L = rear_length(P0, v0)
    checks["rear_length"] = {"numeric_m": L, "analytic_m": r0_ana,
                             "rel_error": abs(L - r0_ana) / r0_ana}

    # 3) 宽度应严格等于 2×深度（同一方程，x=0 截面上 ±y 对称）
    d = solve_depth(P0, v0)
    checks["width_equals_2depth"] = {"depth_m": d, "width_m": 2 * d}

    # 4) 边界残差
    residual = float(temp(P0, v0, 0.0, 0.0, -d) - MAT["Tm_K"])
    checks["boundary_residual_K"] = residual

    # 5) 单调性：功率↑深度↑；速度↑深度↓
    d_low_p = solve_depth(150.0, v0)
    d_high_p = solve_depth(250.0, v0)
    d_slow = solve_depth(P0, 0.6)
    d_fast = solve_depth(P0, 1.4)
    checks["monotonic"] = {"P150_vs_P250": [d_low_p, d_high_p],
                           "v0.6_vs_v1.4": [d_slow, d_fast],
                           "ok": d_low_p < d_high_p and d_slow > d_fast}

    P_grid = [100.0, 150.0, 200.0, 250.0, 300.0]
    v_grid = [0.6, 0.8, 1.0, 1.2, 1.4]
    table = []
    for P in P_grid:
        for v in v_grid:
            dd = solve_depth(P, v)
            table.append({"P_W": P, "v_m_s": v, "depth_um": dd * 1e6,
                          "width_um": 2 * dd * 1e6,
                          "vol_energy_density_J_mm3": P / (v * 0.10 * 0.03) / 1e9,
                          "depth_over_width": 0.5})

    results = {
        "model": "Rosenthal moving point source, quasi-steady, conduction only",
        "units": "SI input, µm output",
        "material": {**MAT, "alpha_m2_s": ALPHA, "delta_T_K": DT},
        "assumptions": ["point source", "isotropic k", "no convection/Marangoni", "no latent heat",
                        "no powder bed", "no multiple reflection/keyhole", "absorptivity constant"],
        "reference_case": {"P_W": P0, "v_m_s": v0, "depth_um": d * 1e6,
                           "width_um": 2 * d * 1e6, "rear_length_um": L * 1e6},
        "checks": checks,
        "grid": table,
        "software": {"python": platform.python_version(), "numpy": np.__version__},
        "caveat": "解析基准，不是对真实熔池的预测；材料参数为常用近似值，未逐条溯源。",
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")

    depth = np.array([[row["depth_um"] for row in table if row["P_W"] == P] for P in P_grid])
    fig, ax = plt.subplots(figsize=(6.2, 4.2), dpi=140)
    im = ax.imshow(depth, origin="lower", aspect="auto", cmap="viridis")
    ax.set_xticks(range(len(v_grid)), [f"{v:g}" for v in v_grid])
    ax.set_yticks(range(len(P_grid)), [f"{p:g}" for p in P_grid])
    ax.set_xlabel("scan speed v (m/s)")
    ax.set_ylabel("laser power P (W)")
    ax.set_title("Rosenthal melt depth (µm), Ti-6Al-4V baseline")
    for i in range(len(P_grid)):
        for j in range(len(v_grid)):
            ax.text(j, i, f"{depth[i, j]:.0f}", ha="center", va="center",
                    color="white" if depth[i, j] < depth.max() * 0.6 else "black", fontsize=8)
    fig.colorbar(im, ax=ax, label="depth (µm)")
    fig.tight_layout()
    fig.savefig(OUT / "map.png")
    plt.close(fig)

    lines = ["# Rosenthal 解析基线（Ti-6Al-4V，点源、纯导热）", "",
             f"α = {ALPHA:.3e} m²/s，ΔT = {DT:.0f} K，吸收率 η = {MAT['absorptivity']}", "",
             "## 自检（解析 vs 数值）", ""]
    lines.append(f"- v=0 球半径：数值 {r0_num*1e6:.3f} µm，解析 {r0_ana*1e6:.3f} µm，"
                 f"相对误差 {checks['v0_sphere_radius']['rel_error']:.2e}")
    lines.append(f"- 尾部长度：数值 {L*1e6:.3f} µm，解析 {r0_ana*1e6:.3f} µm，"
                 f"相对误差 {checks['rear_length']['rel_error']:.2e}")
    lines.append(f"- 宽度 = 2×深度：{checks['width_equals_2depth']['width_m']*1e6:.3f} = "
                 f"2×{d*1e6:.3f} µm（模型内恒等）")
    lines.append(f"- 边界温度残差：{residual:.2e} K")
    lines.append(f"- 单调性（P 150<250，v 0.6>1.4）：{checks['monotonic']['ok']}")
    lines += ["", "## 参考工况 P=200 W, v=1.0 m/s", "",
              f"- 深度 ≈ {d*1e6:.1f} µm，宽度 ≈ {2*d*1e6:.1f} µm，尾部长度 ≈ {L*1e6:.1f} µm",
              "", "## 网格（深度 µm）", "",
              "| P \\ v | " + " | ".join(f"{v:g}" for v in v_grid) + " |",
              "|---|" + "---|" * len(v_grid)]
    for i, P in enumerate(P_grid):
        lines.append(f"| {P:g} W | " + " | ".join(f"{depth[i, j]:.0f}" for j in range(len(v_grid))) + " |")
    lines += ["", "## 边界（重要）", "",
              "- 这是解析基准，不是熔池仿真，更不是实验。假设里没有粉末、多重反射、匙孔、马兰戈尼对流、潜热。",
              "- 材料参数是常用近似值，本轮没有逐条溯源；只报告模型内关系，不与文献数值比大小。",
              "- 想靠近真实熔池，下一步应读 LPBF 热-流耦合模型的参数设置，而不是继续加解析修正项。"]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
