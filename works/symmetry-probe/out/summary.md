# 对称性容差实验（SrTiO3，构造结构）

软件：pymatgen-core 2026.9.23 / spglib 2.8.0 / Python 3.11.13
角度容差固定 5.0°，a0 = 3.905 Å（输入假设）

## 位移探针：顶点氧移动 d

| symprec (Å) | d=0 | d=0.0001 | d=0.001 | d=0.003 | d=0.01 | d=0.03 |
|---|---|---|---|---|---|---|
| 1e-05 | Pm-3m | P4mm | P4mm | P4mm | P4mm | P4mm |
| 0.0001 | Pm-3m | P4mm | P4mm | P4mm | P4mm | P4mm |
| 0.001 | Pm-3m | Pm-3m | P4mm | P4mm | P4mm | P4mm |
| 0.01 | Pm-3m | Pm-3m | Pm-3m | Pm-3m | P4mm | P4mm |
| 0.1 | Pm-3m | Pm-3m | Pm-3m | Pm-3m | Pm-3m | Pm-3m |

## 应变探针：c = a0(1+s)

| symprec (Å) | s=0 | s=1e-05 | s=0.0001 | s=0.001 | s=0.003 | s=0.01 |
|---|---|---|---|---|---|---|
| 1e-05 | Pm-3m | P4/mmm | P4/mmm | P4/mmm | P4/mmm | P4/mmm |
| 0.0001 | Pm-3m | Pm-3m | P4/mmm | P4/mmm | P4/mmm | P4/mmm |
| 0.001 | Pm-3m | Pm-3m | Pm-3m | P4/mmm | P4/mmm | P4/mmm |
| 0.01 | Pm-3m | Pm-3m | Pm-3m | Pm-3m | P4/mmm | P4/mmm |
| 0.1 | Pm-3m | Pm-3m | Pm-3m | Pm-3m | Pm-3m | Pm-3m |

## 切应变（angle_tolerance 的作用）

- γ=0.01° → symprec=1e-3, atol=5°: Pm-3m；symprec=1e-2, atol=1°: Pm-3m
- γ=0.1° → symprec=1e-3, atol=5°: Pm-3m；symprec=1e-2, atol=1°: Pm-3m
- γ=1° → symprec=1e-3, atol=5°: Pm-3m；symprec=1e-2, atol=1°: Cmmm
- γ=5° → symprec=1e-3, atol=5°: Cmmm；symprec=1e-2, atol=1°: Cmmm

## 二分收紧后的阈值（每次判定都是新构造的结构）

| symprec (Å) | 位移阈值 d* (Å) | d*/symprec | 应变阈值 s* | s*·a0/symprec |
|---|---|---|---|---|
| 0.0001 | 4.99861e-05 | 0.500 | 2.56e-05 | 1.000 |
| 0.001 | 0.000499861 | 0.500 | 0.000256 | 1.000 |
| 0.01 | 0.00499861 | 0.500 | 0.00256 | 1.000 |

## 读法

- 位移阈值 / symprec：0.50 ± 0.00（3 个 symprec 的二分结果）
- 应变阈值换算成绝对长度后 / symprec：1.00 ± 0.00
- 粗网格得到的 1–10 倍散布主要是采样分辨率造成的，不能当成物理常数；二分后倍数大致稳定。
- 高于阈值时 Pm-3m 只是容差把畸变吃掉了，不是结构真的立方；低于阈值才被识别为 P4mm/P4/mmm。
- 这是几何与数值判定，不是实验结论；a0 未经本轮文献核对。
