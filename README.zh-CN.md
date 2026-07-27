# Native Pixel Art

[English](README.md) | [简体中文](README.zh-CN.md)

Native Pixel Art 是一个确定性的、项目感知的像素画编译器，同时也是一个 Codex Skill。它用于产出尺寸严格、调色板受控、透明度二值化、网格可复现并经过独立验证的游戏 PNG 资源。

本项目把图像生成结果视为**前驱图**，而不是最终权威资源。最终资源在本地编译，记录为 `grid.json`，再从网格重新渲染、从磁盘重新打开，并且只有在所有硬性验证规则通过后才会被接受。

## 适用场景

当资源必须满足普通图片生成或直接缩放无法稳定保证的技术约束时，适合使用本项目：

- 精灵、图标、瓦片、头像、特效或精灵表必须具有精确原生尺寸；
- 必须使用固定调色板、精确颜色数或最大颜色数；
- 必须全不透明，或只允许二值透明度；
- 动画必须共享调色板，并满足帧布局、锚点和基线规则；
- 新资源需要匹配现有游戏项目的视觉风格；
- 编译过程需要确定性和可机器读取的构建记录；
- 只有验证成功后，资源才允许正式复制到项目目录。

本项目有两种使用方式：

1. 作为 `native-pixel-art` Codex Skill 使用；
2. 作为独立的 `pixel-art` 命令行工具使用。

## 核心保证

- `final.png` 的尺寸与请求的原生尺寸完全一致；
- 可见颜色符合调色板和颜色数量规则；
- Alpha 只能是 `0` 或 `255`；
- 完全透明像素的 RGB 固定为 `0,0,0`；
- `grid.json` 是权威像素表示；
- 预览图是严格的整数倍最近邻放大；
- 动画各帧共享同一调色板并遵守精灵表布局；
- 硬性验证失败会返回非零退出码，并阻止正式发布；
- 除非显式启用 `overwrite`，否则不会覆盖已有输出。

## 环境要求

- Python 3.11 或更高版本
- Windows、macOS 或 Linux
- 可选：用于无界面图像生成的 OpenAI API Key 和 `openai` 扩展依赖
- 可选：用于导出 `.aseprite` 文件的 Aseprite

## 安装

### 使用 uv

```bash
git clone https://github.com/hyfzero/native-pixel-art.git
cd native-pixel-art
uv sync --extra dev
uv run pixel-art --help
```

如需无界面 OpenAI 图像生成：

```bash
uv sync --extra dev --extra openai
```

### 使用 pip

```bash
git clone https://github.com/hyfzero/native-pixel-art.git
cd native-pixel-art
python -m venv .venv
```

激活虚拟环境后安装：

```bash
python -m pip install -e ".[dev]"
pixel-art --help
```

如需 OpenAI 图像生成：

```bash
python -m pip install -e ".[dev,openai]"
```

安装后执行健康检查：

```bash
pixel-art doctor
```

如果使用 `uv` 且没有激活虚拟环境，请在命令前加 `uv run`，例如 `uv run pixel-art doctor`。

## 快速开始：编译本地图片

下面的离线命令把现有 PNG 编译成严格的 16×16 二色资源：

```bash
pixel-art compile source.png \
  --width 16 \
  --height 16 \
  --palette "#000000,#FFFFFF" \
  --output output/icon
```

PowerShell 使用反引号续行：

```powershell
pixel-art compile source.png `
  --width 16 `
  --height 16 `
  --palette "#000000,#FFFFFF" `
  --output output/icon
```

命令会输出 `final.png` 的路径。输出目录还会包含权威网格、预览图、调色板条、清单和验证报告。

正式工作建议使用带版本的 YAML 或 JSON 请求：

```yaml
schema_version: 2
asset_id: moon_icon
description: A small crescent moon icon with a clean, readable silhouette.
asset_type: static
style_profile: generic
width: 16
height: 16

palette:
  mode: fixed
  colors: ["#000000", "#FFFFFF"]
  color_count: 2
  count_rule: exact
  source: request

alpha:
  mode: binary

background:
  mode: transparent
  color: "#000000"

composition:
  subject_scale: 0.8
  alignment: center
  padding: 1

references:
  mode: none
  minimum: 0
  maximum: 0

cleanup:
  remove_isolated_pixels: true
  minimum_cluster_size: 2
  binary_alpha: true
  connectivity: 4

export:
  output_dir: output/moon_icon
  preview_scale: 12
  save_manifest: true
  save_intermediate: true
  overwrite: false
  promote: false
  aseprite: auto
```

使用请求文件编译：

```bash
pixel-art compile source.png --config request.yaml
```

## 主要工作流

### 1. 离线编译

把本地插画、渲染图、草图、生成图或精灵表作为前驱图：

```bash
pixel-art compile precursor.png --config request.yaml
```

编译器会依次：

1. 解析项目配置和风格配置的默认值；
2. 按需加载项目参考图；
3. 分离背景并裁切主体；
4. 把主体放到受控工作画布上；
5. 降采样到原生帧尺寸；
6. 选择或提取调色板；
7. 量化颜色并清理连通像素簇；
8. 应用请求中定义的有界像素补丁；
9. 写入 `grid.json`；
10. 从网格渲染 `final.png`；
11. 独立验证磁盘上的 PNG 和预览图；
12. 原子化发布临时输出目录。

此工作流不会访问网络。

### 2. 无界面 OpenAI 图像生成

先安装 `openai` 扩展，并设置 `OPENAI_API_KEY`。

PowerShell：

```powershell
$env:OPENAI_API_KEY = "your-api-key"
```

Bash：

```bash
export OPENAI_API_KEY="your-api-key"
```

使用显式请求：

```yaml
schema_version: 2
asset_id: forest_ranger
description: A small side-view forest ranger with a readable hat and bow.
asset_type: static
width: 32
height: 32
palette:
  mode: adaptive
  color_count: 8
  count_rule: maximum
  source: source
references:
  mode: none
  minimum: 0
  maximum: 0
generation:
  provider: openai
  variants: 3
  allow_image_generation: true
  model: gpt-image-2
  quality: medium
export:
  output_dir: output/forest_ranger
```

然后运行：

```bash
pixel-art generate --config ranger.yaml
```

后端会生成多个候选图，并按轮廓、留白、覆盖率、对比度、颜色复杂度和结构损失评分，随后编译得分最高的候选图。项目会拒绝 `seed`，因为当前配置的图像模型并未声明支持种子复现。

### 3. Codex ImageGen 交接

请求中设置：

```yaml
generation:
  provider: codex_imagegen
  variants: 3
  allow_image_generation: true
```

运行：

```bash
pixel-art generate --config request.yaml
```

命令会准备 `imagegen_handoff.json`、参考图联系表和参考图统计。随后在 Codex 中将这些本地参考图交给 ImageGen，保存选中的前驱图，再进行编译：

```bash
pixel-art compile selected-precursor.png --config request.yaml
```

交接命令会按后端交接返回，而不会假装 CLI 已经调用了只能在应用内使用的 ImageGen 工具。

### 4. 动画精灵表

下面是一个 4×1 布局、每帧 32×32 的四帧行走动画：

```yaml
schema_version: 2
asset_id: hero_walk
description: Four-frame side-view walk loop.
asset_type: animation
width: 32
height: 32
palette:
  mode: fixed
  colors: ["#000000", "#FEFEFE"]
  color_count: 2
  count_rule: exact
alpha:
  mode: binary
references:
  mode: none
  minimum: 0
  maximum: 0
animation:
  frame_width: 32
  frame_height: 32
  frame_count: 4
  columns: 4
  rows: 1
  baseline_tolerance: 2
  anchor_tolerance: 2
  actions:
    - name: walk
      start: 0
      count: 4
      fps: 8
export:
  output_dir: output/hero_walk
```

编译现有前驱精灵表：

```bash
pixel-art animate --source precursor-sheet.png --config animation.yaml
```

最终精灵表尺寸必须严格等于 `frame_width × columns` 乘以 `frame_height × rows`。请求帧不能为空，未使用的单元格必须为空，锚点和基线漂移必须处于容差内。

### 5. 独立验证

使用原请求验证 PNG：

```bash
pixel-art validate output/moon_icon/final.png --config request.yaml
```

也可以直接传递约束：

```bash
pixel-art validate \
  --input output/moon_icon/final.png \
  --width 16 \
  --height 16 \
  --max-colors 2 \
  --palette "#000000,#FFFFFF" \
  --report output/moon_icon/manual-validation.json
```

验证器会重新打开文件，并且不会调用编译器的修复函数。硬性失败时退出码为 `4`。

### 6. 调色板和预览工具

提取确定性的感知调色板：

```bash
pixel-art palette extract source.png --colors 8 --output palette.json
pixel-art palette extract source.png --colors 8 --output palette.png
```

生成严格的最近邻整数倍预览：

```bash
pixel-art preview final.png --scale 12 --output preview.png
```

分析单张图片或整个目录：

```bash
pixel-art analyze-style \
  --input assets/characters \
  --name room_characters \
  --output style.json
```

## 请求配置说明

请求中出现未知字段会直接报错，这可以尽早发现拼写错误和过期配置。

| 区域 | 重要字段 | 含义 |
| --- | --- | --- |
| 身份 | `schema_version`、`asset_id`、`description`、`asset_type` | 稳定资源身份和设计意图；`asset_id` 必须是 snake_case。 |
| 几何 | `width`、`height` | 静态资源和瓦片的原生尺寸。 |
| 动画 | `frame_width`、`frame_height`、`frame_count`、`columns`、`rows`、`actions` | 单帧尺寸和精灵表契约。 |
| 调色板 | `mode`、`colors`、`color_count`、`count_rule`、`source` | 固定、自适应、项目配置或语义调色板行为。 |
| Alpha | `mode`、`transparent_counts_as_color` | 二值透明或完全不透明输出。 |
| 背景 | `mode`、`color` | 透明、纯色或保留背景。 |
| 构图 | `subject_scale`、`alignment`、`padding` | 原生尺寸缩减前的主体布局。 |
| 参考图 | `mode`、`paths`、`category`、`minimum`、`maximum` | 显式或自动选择项目参考图。 |
| 生成 | `provider`、`variants`、`allow_image_generation`、`model`、`quality` | 离线、Codex 交接或 OpenAI 无界面生成。 |
| 清理 | `remove_isolated_pixels`、`minimum_cluster_size`、`connectivity`、`protected_mask` | 连通区域清理规则。 |
| 补丁 | `operation`、`frame`、`x`、`y`、`width`、`height`、`color`、`transparent` | 用于语义像素修复的有界网格修改。 |
| 导出 | `output_dir`、`preview_scale`、`overwrite`、`promote`、`promote_to`、`aseprite` | 输出、覆盖和正式发布行为。 |

生成的 JSON Schema 位于 [`schemas/request.schema.json`](schemas/request.schema.json)，完整字段说明见 [`references/request_contract.md`](references/request_contract.md)。

### 调色板模式

- `fixed`：只允许出现列出的颜色；
- `adaptive`：从源图或参考图中确定性提取调色板；
- `profile`：使用项目风格配置的默认值；
- `semantic`：按已配置的语义角色和遮罩分配颜色预算。

`count_rule: exact` 要求计入统计的颜色数严格等于 `color_count`。固定调色板下，每个列出的颜色还必须实际使用。工具不会为了通过验证而插入无意义的填充像素。

### 背景和透明度

- `background.mode: transparent`：估计并去除可分离的边界背景；
- `background.mode: solid`：合成到 `background.color`；
- `background.mode: preserve`：保留源图背景行为；
- `alpha.mode: binary`：把 Alpha 阈值化为 `0` 或 `255`；
- `alpha.mode: opaque`：把透明区域合成到背景颜色。

同时使用固定调色板和纯色背景时，背景颜色必须属于固定调色板。

### 像素补丁

补丁作用于权威帧网格，而不是直接修改 `final.png`：

```yaml
patches:
  - operation: set_pixel
    frame: 0
    x: 7
    y: 5
    color: "#FFFFFF"
  - operation: fill_rect
    frame: 0
    x: 3
    y: 12
    width: 2
    height: 1
    transparent: true
```

补丁颜色必须属于权威调色板。补丁只应用于眼睛、轮廓断点或动画锚点等范围明确、具有语义意义的修复。

## 项目感知集成

在游戏仓库中，项目专属策略建议放在：

```text
tools/pixel_art/
├── project.yaml
├── profiles/
│   └── your_profile.yaml
├── reference_catalog.yaml
└── requests/
```

`tools/pixel_art/project.yaml` 示例：

```yaml
schema_version: 1
work_dir: .godot/pixel_art_work
reference_catalog: reference_catalog.yaml
promotion_roots:
  - assets/generated
profiles:
  game_world_duotone: profiles/game_world_duotone.yaml
  room_color: profiles/room_color.yaml
```

风格配置示例：

```yaml
schema_version: 1
name: game_world_duotone
request_defaults:
  palette:
    mode: fixed
    colors: ["#000000", "#FEFEFE"]
    color_count: 2
    count_rule: exact
  style:
    dithering: off
  references:
    mode: auto
    minimum: 3
    maximum: 6
```

生成或刷新参考图目录：

```bash
pixel-art profile-project --project-root /path/to/game
```

当前分析器扫描 `assets/` 下的 PNG，识别包含 `game_world` 和 `room` 的路径，根据目录推断资源类别，并写入：

- `tools/pixel_art/reference_catalog.yaml`
- `tools/pixel_art/style_stats.json`

提交前应人工复核生成的类别和权重。自动参考图选择会综合风格配置匹配、资源类别、配置权重和与目标原生尺寸的对数距离进行排序。

检查项目集成：

```bash
pixel-art doctor --project-root /path/to/game
```

## 输出契约

一次普通编译可以生成：

```text
output/<asset_id>/
├── final.png
├── grid.json
├── preview_12x.png
├── palette.png
├── manifest.json
├── validation_report.json
├── candidate_scores.json          # 仅生成候选图时存在
├── intermediate/                  # save_intermediate 为 true 时存在
├── references/
│   ├── reference_stats.json
│   └── reference_contact_sheet.png
└── <asset_id>.aseprite            # 可用且被请求时存在
```

`manifest.json` 记录规范化请求、提示词规划、调色板、参考图、候选评分、帧指标、编译统计、文件哈希、后端元数据、语义审查和正式发布位置。

## 安全发布到项目

正式发布会把通过验证的产物复制到项目资源目录：

```yaml
export:
  output_dir: .godot/pixel_art_work/goblin_16
  promote: true
  promote_to: assets/generated/enemies
  overwrite: false
```

只有硬性验证成功后才会执行发布。配置了 `promotion_roots` 时，超出允许根目录的目标会被拒绝。发布过程会先暂存文件并建立备份，局部失败时可以回滚。

发布后的文件名：

- `<asset_id>.png`
- `<asset_id>.grid.json`
- `<asset_id>.pixel-art.json`
- 可选的 `<asset_id>.aseprite`

## 退出码

| 退出码 | 含义 |
| ---: | --- |
| `0` | 成功 |
| `2` | 配置、Schema、输入或编译错误 |
| `3` | 图像后端不可用、被拒绝或需要应用内交接 |
| `4` | 资源硬性验证失败 |
| `5` | 必需的 doctor 检查失败 |
| `6` | 输出已存在且未启用覆盖 |

## 常见问题

### 输出已经存在

使用新的输出目录，或显式允许覆盖：

```bash
pixel-art compile source.png --config request.yaml --overwrite
```

### 精确调色板验证失败

不要添加无关像素来凑颜色数。应改进前驱图、选择更合适的调色板、在需求允许时把 `exact` 改为 `maximum`，或增加具有语义意义的补丁。

### 小细节消失

可以提高原生尺寸、简化源图、减少视觉噪声、关闭像素簇清理、降低 `minimum_cluster_size`，或用遮罩/有界补丁保护刻意保留的细节。

### 主体触碰边界

增大 `composition.padding`、减小 `composition.subject_scale`，或改善前驱图的前景/背景分离。

### OpenAI 生成失败

确认以下三项：

1. 已安装 `openai` 可选依赖；
2. 已设置 `OPENAI_API_KEY`；
3. 已设置 `generation.allow_image_generation: true`。

然后运行 `pixel-art doctor`。

### 找不到 Aseprite

使用 `export.aseprite: auto` 将其设为可选，使用 `off` 关闭导出，或使用 `required` 让缺失 Aseprite 时构建失败。

## 更多文档

- [开发手册](DEVELOPMENT.zh-CN.md)
- [请求契约](references/request_contract.md)
- [完整请求示例](references/examples.md)
- [项目风格配置](references/project_styles.md)
- [调色板规则](references/palette_rules.md)
- [连通像素簇规则](references/cluster_rules.md)
- [提示词规划规则](references/prompting.md)

## 许可证

项目当前未包含许可证文件。在公开分发或按明确许可证接收外部贡献前，请先添加许可证。
