# 《檐下雨》15 秒竖屏切片

把已有原创曲剪成 15 秒竖屏，字幕只落在段落内、三次停顿处留白。时间点全部取自
`projects/first-work/out/timeline.json`，不手填。

## 复现

```
python3.11 build_short.py
```

产物：`out/eaves_rain_15s.mp4`（720×1280，H.264/AAC，15.1 s，含 AAC 填充）、
`out/short_report.json`、`out/check.png`（2/8/13.5 s 三帧对照）。

## 时间线（相对切片起点 1.4 s）

| 段 | 字幕 | 起止 (s) |
|---|---|---|
| A1 | A1 · 第一次陈述　Dm – Bb – Gm – Am | 0.029–5.743 |
| A2 | A2 · 应答　同样的和弦，句尾换回 Dm | 6.143–11.857 |
| B | B · 抬起来　Bb – Gm – Am – Dm | 12.757–15.0 |

停顿 7.14–7.54、13.26–14.16 对应 5.74–6.14、11.86–12.76，字幕刻意留白。

## 两个 ffmpeg 颜色坑（2026-11-15 已修）

1. **screen 混合在 rgb24 下会错色**：背景本该是深蓝 0x0b1220，`blend=all_mode=screen` 输出却成了紫色（128,0,170 量级），
   逐级取样后确认是 blend 这一步；改用 `format=rgba` + `colorkey` + `overlay` 才正确。
2. **showwaves 的 colors 十六进制按 0xAARRGGBB 解释**：写 `0x4a7fb5` 会被当成 A=0x4a、R=0x7f、G=0xb5、B=0x4a，
   于是波形变成绿色；加 `0xff` 前缀（`0xff6fa8dc`）才得到想要的浅蓝。

验证方式不是“看起来对”，而是抽帧读左上像素：修复后 (10,17,31) 深蓝、波峰 (115,151,237) 浅蓝。
