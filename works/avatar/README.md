# 蓝色鲸鱼头像 / Blue Whale Avatar

大肥鱼自己设计并绘制的原创头像（2026-11-12）。

## 设计

一只侧身的蓝色小鲸鱼：白色蝴蝶结、腮红、喷水和小气泡，扁平配色，正方形构图，适合做聊天头像。其中 DeepSeek 蓝色系是角色的配色习惯，画面本身不包含任何第三方商标或素材。

## 方法（软件绘图，不是扩散模型）

- 源码为手写 SVG（`whale_avatar.svg`），路径、渐变、圆形全部手算坐标。
- 用 Python 的 CairoSVG 渲染成 1024x1024 的 PNG（`whale_avatar.png`）。
- 没有使用文生图模型；没有引用、描摹或拼贴网络图片。

## 文件

- `whale_avatar.svg` - 可编辑矢量源码，直接用编辑器或文本工具改颜色、形状、构图。
- `whale_avatar.png` - 渲染产物，1024x1024，207766 字节。

## 修改

改 SVG 里的 `fill` / `cx` / `cy` / `d` 即可；重新渲染：

```python
import cairosvg
cairosvg.svg2png(url="whale_avatar.svg", write_to="whale_avatar.png",
                 output_width=1024, output_height=1024)
```
