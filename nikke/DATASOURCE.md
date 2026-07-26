# NIKKE（胜利女神）数据源与工具说明

本文说明 NIKKE 美术资源（Spine 骨骼动画立绘/模型）的**数据来源**、**本地文件位置**、
以及**拆解 → 重组**工具链。所有脚本在 `nikke/scripts/`。

> NIKKE 的立绘/模型是 **Spine 骨骼动画**（`.skel` + `.atlas` + `.png`），**不是 Live2D**。
> 每套资源包含骨骼数据 `.skel`、图集描述 `.atlas`、贴图页 `.png`。

---

## 一、数据源（两条路，可二选一或互补）

### 路线 A：社区 Nikke-db（快速，无需游戏本体）

社区项目 [`Nikke-db`](https://github.com/Nikke-db/Nikke-db.github.io) 已把 Spine 资源
解包并托管在 CDN 上，直接按角色 id 下载即可。

| 用途 | 地址 |
|------|------|
| 角色索引 `l2d.json`（name/id/version） | `https://nikke-db-legacy.pages.dev/js/json/l2d.json` |
| 索引镜像 | `https://raw.githubusercontent.com/Nikke-db/Nikke-db.github.io/main/js/json/l2d.json` |
| Spine 资源根 | `https://nikke-db-legacy.pages.dev/l2d` |
| 渲染好的头像图标（列表封面用） | `https://nikke-db-legacy.pages.dev/images/sprite` |
| 资源镜像 | `https://raw.githubusercontent.com/Nikke-db/Nikke-db.github.io/main/l2d` |

配置位置：`nikke/scripts/config.py`

**资源 URL 规律**（三种姿态）：
```
fb   (立绘全身): {CDN}/l2d/{id}/{id}_00.skel | .atlas | .png
cover(半身):     {CDN}/l2d/{id}/cover/{id}_cover_00.skel | .atlas | .png
aim  (瞄准):     {CDN}/l2d/{id}/aim/{id}_aim_00.skel | .atlas | .png
头像图标:        {CDN}/images/sprite/si_{id}_00_s.png
```
- `.atlas` 是文本文件，里面列出引用的所有 `.png` 页，脚本据此逐个下载贴图。
- Cloudflare Pages（`pages.dev`）会对**缺少 UA / Referer 的请求返回 403**，
  抓取时必须伪装浏览器 UA + 带 `Referer: https://nikke-db-legacy.pages.dev/`。

### 路线 B：本地游戏客户端缓存（数据最全最新）

游戏客户端把资源以 **content-addressed** 方式缓存在本地，可直接解包，
覆盖 Nikke-db 未收录的角色/皮肤/剧情演出。

**本地文件位置**（默认，可用环境变量 `NIKKE_LOCAL_ASSETS` 覆盖）：
```
<客户端资源目录>/naps/<hash前2位>/<md5>     # 无扩展名，共 256 个桶(00~ff)
```
默认路径：`Q:/NIKKE_Assets`（Windows PC 客户端资源目录）。

每个缓存文件头分两种：

| 文件头 | 类型 | 占比 | 是否可解 |
|--------|------|------|----------|
| `UnityFS` | 明文 Unity 包 | 约 76%（25266 个） | ✅ UnityPy 直接解 |
| `NKAB` | NIKKE 私有加密包 | 约 24%（8073 个） | ❌ 暂不支持（见下） |

> **重要**：常规立绘 **fb / cover / aim 几乎都在 NKAB 加密包里**，明文包只有
> skillcut / eventscene / 剧情过场。而本项目缓存的 NKAB 全部是 **v4**，
> **目前没有公开可用的 v4 解密器**，故本地拆不出 fb/cover/aim，需走路线 A 从 CDN 获取。
> 详见 [`NKAB_ENCRYPTION.md`](./NKAB_ENCRYPTION.md)。

> 实测一次全盘扫描：25266 个明文包 → `.skel` 共 588 套（skillcut 434 / eventscene 82 /
> 剧情 70 / fb 仅 2），基本不含 fb/cover/aim。

---

## 二、本地文件位置（本项目内）

```
nikke/
├── raw/
│   └── naps/                   # (可选) 本地客户端资源缓存的软链/拷贝
├── data/                       # 还原产物（查看器直接读）
│   └── <id>/                   #   角色 id，如 c010 / c101_01(皮肤) / eventscene_*
│       ├── <stem>.skel         #     骨骼数据（fb 姿态直接放根目录）
│       ├── <stem>.atlas        #     图集描述
│       ├── <page>.png          #     贴图页
│       ├── _icon.png           #     列表封面头像（Nikke-db 下载或本地渲染）
│       ├── cover/              #     半身姿态
│       └── aim/                #     瞄准姿态
│   ├── _fetched.json           #   本次抓取的角色元数据（供 manifest）
│   └── _l2d_index.json         #   (可选) 缓存的 l2d.json 索引
└── viewer/
    └── nikke_manifest.json     # 查看器清单（姿态/Spine版本/分类/封面）
```

**姿态 / 分类命名规律**：

| skel 名 | id | pose |
|---------|-----|------|
| `c010_00` | c010 | fb（立绘全身） |
| `c101_01` | c101_01（皮肤） | fb |
| `c010_cover_00` | c010 | cover（半身） |
| `c010_aim_00` | c010 | aim（瞄准） |
| `c233_00_skillcut` | c233 | skillcut（技能演出立绘，本地解包才有） |
| `EventScene_*` | eventscene_* | fb（活动剧情） |
| `liberation_* / MVG / Glass` | 同名 | fb（过场/剧情） |

manifest 分类（`categorize`）：`character` / `event` / `story` / `misc`。

---

## 三、拆解 → 重组工具链

依赖：`requests`（下载）、`UnityPy`（解本地 Unity 包）、`playwright` + Node（可选，渲染缩略图）。

### 路线 A：从 Nikke-db 拉取

```bash
cd nikke/scripts

# 1. 拉资源（读 l2d.json 索引，按角色下 fb/cover/aim + 头像图标）
python fetch_nikke.py                 # 全部角色
python fetch_nikke.py c010 c470       # 指定角色
python fetch_nikke.py --limit 60      # 前 60 个（快速验证）

# 补漏：l2d.json 索引不全（如 c515 等未收录），但 CDN 上实际存在。
# 扫描本地已有目录，逐个探测 CDN 补抓姿态：
python fetch_nikke.py --scan-existing --only-missing

# 2. 生成查看器 manifest
python gen_nikke_manifest.py

# 3.（可选）为缺头像的角色，用无头浏览器渲染 Spine 生成缩略图
#    需先在仓库根启动 http server，并安装 playwright
CHROMIUM_PATH=<chrome路径> node gen_thumbs.mjs http://127.0.0.1:8000 ../data
```

### 路线 B：从本地客户端缓存解包

```bash
cd nikke/scripts
export NIKKE_LOCAL_ASSETS=Q:/NIKKE_Assets   # 指定客户端资源目录

python extract_local.py               # 扫全部 256 个桶
python extract_local.py --buckets 00 01   # 只扫指定桶
python extract_local.py --limit 30    # 前 N 个桶（快速验证）

python gen_nikke_manifest.py          # 再生成 manifest
```

`extract_local.py` 流程：遍历 `naps/` 下所有桶 → 检测文件头 → 对 `UnityFS` 明文包，
若含 `TextAsset(*.skel)` 则视为 Spine 包 → 提取 `.skel`/`.atlas` + atlas 引用的
`Texture2D` 贴图 → 按 skel 名解析 id/姿态归类。支持断点续跑（skel 已存在则跳过）。

### 脚本一览

| 脚本 | 作用 |
|------|------|
| `fetch_nikke.py` | 路线 A：从 Nikke-db CDN 拉 Spine 资源（多线程，断点续传，补漏扫描） |
| `extract_local.py` | 路线 B：从本地客户端 content-addressed 缓存解包明文 Unity 包 |
| `gen_nikke_manifest.py` | 扫 `data/` → 识别姿态 + Spine 版本 + 分类 + 封面 → 生成 manifest |
| `gen_thumbs.mjs` | 无头浏览器渲染 Spine → 自动裁剪透明边 → 生成头像缩略图 |
| `config.py` | 数据源 URL / 姿态 / 代理 / 本地资源目录配置 |

---

## 四、关键技术点

**1. Spine 版本自适应**
读 `.skel` 头部（前 64 字节内匹配 `[34]\.[0-9]+\.[0-9]+`）拿到版本串（`4.0.x` / `4.1.x`），
只取主次版本（`4.0` / `4.1`）。前端据此选择 `spine-player4.0.js` / `spine-player4.1.js`
（`shared/vendor/`，EsotericSoftware 官方 spine-player）。

**2. 正确渲染（预乘 alpha）**
必须 `premultipliedAlpha: true` + 透明背景。早期用 pixi-spine 未处理预乘 alpha
导致立绘发灰/发黑；改用官方 spine-player 后还原正确。

**3. 动画回退**
部分 skillcut / 剧情场景模型默认动画名不是 `idle`。查看器在 `success` 回调里
按实际可用动画智能选择：默认名 → 含 `idle` 的 → 第一个，避免报错。

**4. 封面缩略图**
优先用 Nikke-db 渲染好的头像图标 `si_{id}_00_s.png`（存为 `_icon.png`）；
缺失时用无头浏览器渲染 Spine、自动裁剪透明边生成缩略图，避免直接显示打乱的 atlas 碎片。
（Cloudflare Pages 对缺失文件返回 200 + HTML，需按 `content-type` 甄别是否真为图片。）

---

## 五、版权说明

仅用于个人学习研究。Spine 立绘 / 模型版权归属 NIKKE（SHIFT UP / Level Infinite），
请勿商用或公开再分发。
