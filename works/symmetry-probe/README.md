# SrTiO3 对称性容差探针

一个只问一件事的数值实验：**SpacegroupAnalyzer 判成 Pm-3m，究竟是结构真的立方，还是 symprec 把畸变吃掉了？**

## 环境与复现

- Python 3.11.13，pymatgen-core 2026.9.23，spglib 2.8.0
- 运行：`MPCONFIGDIR=.mpl ../../.venv-pymatgen/bin/python analysis.py`
- 产物：`out/results.json`、`out/summary.md`、`out/boundary.png`

## 模型（构造，不是实验）

立方钙钛矿 SrTiO3，a0 = 3.905 Å（文献常用室温值，本轮未联网核对，只作输入假设）。
两种畸变：顶点氧沿 z 位移 d；轴向应变 c = a0(1+s)。角度容差固定 5°，symprec 取 1e-5…1e-1 Å。

## 结果

- 位移阈值 d*/symprec = **0.500**（三个 symprec 的二分结果一致到 1e-3 相对误差）
- 应变阈值换算成绝对长度 s*·a0/symprec = **1.000**
- 也就是说：容差量级确实与 symprec 相当，但**系数取决于畸变类型**——内部坐标位移是 1/2，晶格度量变化是 1。没有读 spglib 源码，这里只记录数值规律，不解释成普适常数。
- 切应变下 angle_tolerance 很关键：γ=1° 时 atol=5° 仍判 Pm-3m，atol=1° 判 Cmmm。
- symprec=0.1 Å 时，d=0.03 Å（约 a 的 0.8%）仍被吞成 Pm-3m——MP 常用容差下“立方”不能当结构证据。

## 边界

全部是几何判定：不是合成、不是实验、不是 Materials Project 数据。a0 未经核对。阈值只对这两个特定的单参数畸变成立，不能外推到八面体倾转等更复杂的模式。
