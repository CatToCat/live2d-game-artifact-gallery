# live2d-game-artifact-gallery

游戏资源解包 & 展示平台。从游戏客户端提取**立绘、Live2D 模型、音频**等美术制品，
还原成网页可直接查看的格式，并提供带搜索/分组/排序/动作播放的查看器。

> 当前已完整支持 **碧蓝航线（Azur Lane）**；架构设计为可扩展到其他游戏，
> 每个游戏的资源定位/解密/重建逻辑以插件式脚本接入。

**碧蓝航线现状**：
- **立绘**：6026 张（按皮肤分组，3145 个皮肤组）
- **Live2D**：266 个模型，每个含 14 个动作（idle / home / 触摸 / 任务 / 结婚 等）
- 支持**本地一键自动更新**：拉取最新版本 → 增量下载 → 还原 → 刷新查看器

**NIKKE（胜利女神）现状**：
- **立绘 / 模型**：Spine 骨骼动画，支持 **立绘(fb) / 半身(cover) / 瞄准(aim)** 三种姿态
- 查看器自动识别 **Spine 4.0 / 4.1** 版本并加载对应 runtime（EsotericSoftware 官方 spine-player），
  正确处理预乘 alpha（premultipliedAlpha），透明背景，自带动作切换/播放控件
- 数据来源：社区 [`Nikke-db`](https://github.com/Nikke-db/Nikke-db.github.io) 已解包的 Spine 资源

---

## 目录结构

```
live2d-game-artifact-gallery/
├── viewer/                  # 网页查看器（纯静态，浏览器打开即用）
│   ├── index.html           #   主页面
│   ├── manifest.json        #   资源清单（分组/排序信息，由脚本生成）
│   └── vendor/              #   pixi.js / pixi-live2d-display / Cubism Core
├── data/                    # 还原产物（查看器直接读取）
│   ├── models/<name>/       #   Live2D：moc3 + 贴图 + physics3 + motions/ + model3.json
│   └── paintings/<name>.png #   立绘 PNG
├── cache/AssetBundles/      # 下载的原始 Unity bundle（增量更新对比用，~10GB）
│   ├── painting/  live2d/  paintingface/ ...
├── config/
│   ├── hashes/*.csv         #   各资源类型的版本清单（path,size,md5）
│   └── cfg_json/            #   角色配置（皮肤分组/发布顺序，来自社区数据库）
├── scripts/                 # 所有处理脚本
│   ├── config.py            #   路径与配置中心（改结构只改这里）
│   ├── update.py            #   ★ 一键自动更新入口
│   ├── fetch_manifests.py   #   握手拿版本 + 下载 hash 清单
│   ├── dl_from_csv.py       #   按清单下载 bundle（多线程 + 断点续传）
│   ├── build.py             #   从 bundle 还原立绘 + Live2D（含动作）
│   ├── rebuild_painting.py  #   立绘重建（Mesh+图集碎片 → 完整 PNG）
│   ├── extract_live2d.py    #   Live2D 提取（moc3/贴图/physics/model3.json）
│   ├── motion_convert.py    #   AnimationClip → motion3.json（动作）
│   └── gen_manifest.py      #   生成查看器 manifest（分组/代表图/排序）
├── requirements.txt
└── README.md
```

---

## 快速开始（查看已有资源）

无需任何依赖，直接起个静态服务器：

```bash
cd live2d-game-artifact-gallery
python -m http.server 8000
# 浏览器打开 http://127.0.0.1:8000/viewer/
```

- **Live2D 模型** 页：左侧搜索/排序舰装，点击加载，右侧动作按钮播放动作。
  拖拽平移、滚轮缩放、移动鼠标视线跟随，物理与呼吸已还原。
- **立绘画廊** 页：按皮肤分组，卡片是代表图（优先完整人物立绘），
  点进去看该皮肤的全部立绘（默认/换装/破损/部件）。搜索支持拼音名和英文名。

---

## 安装依赖（需要更新资源时）

```bash
pip install -r requirements.txt
```

依赖说明：
- `azlassets` —— 碧蓝航线资源工具（用于版本握手 + 拉取 hash 清单）
- `UnityPy` —— 解析 Unity AssetBundle
- `Pillow` / `numpy` —— 立绘 Mesh 重建
- `requests` / `PySocks` —— 下载 + 代理

---

## 数据来源

| 内容 | 来源 |
|------|------|
| 资源 CDN（EN 国际服） | `https://blhxusstatic.yo-star.com/android`（Yostar） |
| 版本网关 | `blhxusgate.yo-star.com:80`（raw TCP + protobuf 握手） |
| 角色分组/发布顺序 | 社区数据库 [`Fernando2603/AzurLaneData`](https://github.com/Fernando2603/AzurLaneData) 的 `ship_skin_template.json` |

> **CN（bilibili）服**：CDN `https://line3-patch-blhx.bilibiligame.net`，
> 网关 `line1-login-bili-blhx.bilibiligame.net`。改 `scripts/config.py` 的 `CDN`/`GATE` 即可切换。

### 资源下载 URL 规则
- hash 清单：`{CDN}/hash/{versionhash}`（版本握手后获得 versionhash）
- 资源文件：`{CDN}/resource/{md5}`（md5 来自清单第 3 列）

---

## 自动更新

```bash
cd live2d-game-artifact-gallery/azur_lane/scripts
python update.py             # 增量更新：只处理相比上次有变化的资源
python update.py --full      # 全量重建（忽略缓存）
python update.py --skip-meta # 跳过社区元数据更新
```

流程：
1. **拉社区元数据** → 皮肤名/分组/发布次序（多源回落，失败不阻断）
2. **握手拿版本** → 下载最新 hash 清单到 `config/hashes/`
3. **增量对比** → 与 `config/hashes_prev/` 比对，找出新增/变更的资源
4. **下载 + 还原** → 只下变化的 bundle（对变化项强制 md5 校验），重建对应立绘/模型/动作
5. **刷新 manifest** → 更新查看器分组数据，回写首页/README 计数，保存本次清单供下次对比

### 元数据说明
角色名 / 分组 / 发布次序来自社区仓库（官方那份配置表是自定义加密二进制，
需逆向 il2cpp 才能解，详见 `azur_lane/DATASOURCE.md`）。
`fetch_metadata.py` 按序尝试三个源（主源 JSON → jsDelivr 镜像 → AzurLaneTools 的 Lua），
带完整性校验（条目数下限，挡掉上游的残缺文件）、防回退、原子写入；
全部源失败时保留现有文件继续，只是新皮肤可能暂时未分组。

### 网络说明
- 脚本默认走本地代理 `127.0.0.1:7897`（海外 CDN，国内需要）。
  在海外服务器 / GitHub Actions 上运行时，把 `azur_lane/scripts/config.py` 的 `USE_PROXY = False`。
- gate 握手是 **raw TCP socket**（不走 HTTP 代理），代理时用 SOCKS5；
  资源下载走 HTTPS（HTTP 代理）。
- 官方 CDN 有限流，偶发连接重置；脚本已内置重试，必要时隔几十秒重跑。

---

## 单步执行（调试用）

```bash
cd live2d-game-artifact-gallery/azur_lane/scripts
python fetch_metadata.py             # 只更新社区元数据（--force 强制）
python fetch_manifests.py            # 只拉最新清单
python dl_from_csv.py L2D            # 只下 Live2D 的 bundle（PAINTING/PIC/L2D）
python dl_from_csv.py --verify L2D   # 同上 + md5 校验（可发现同尺寸的内容改动）
python build.py live2d               # 只还原 Live2D（含动作）
python build.py painting             # 只还原立绘
python gen_manifest.py               # 只重新生成查看器 manifest
```

---

## 技术要点

- **立绘重建**：碧蓝航线立绘贴图是打乱的碎片图集，需用 Mesh 的顶点 + UV
  做三角形仿射变换重排回完整图（`rebuild_painting.py`）。已处理多贴图合成、
  透明区垃圾像素剔除等边缘情况。
- **Live2D 动作**：AnimationClip 的动画数据是 Unity StreamedClip 二进制曲线，
  用 binding path 的 CRC32 反查 Live2D 参数名（`Parameters/ParamXxx`），
  转成标准 `motion3.json`（`motion_convert.py`）。
- **分组**：以皮肤 id（`ship_skin_template.json` 的 `id`）为分组键，
  id 递增对应发布顺序；代表图优先级 `_n_rw > _rw > _n > main`。

---

## NIKKE 管线

NIKKE 的立绘/模型是 **Spine 骨骼动画**（`.skel` + `.atlas` + `.png`），非 Live2D。
支持两种数据源：**(A)** 社区 [`Nikke-db`](https://github.com/Nikke-db/Nikke-db.github.io)
已解包托管的资源；**(B)** 从本地游戏客户端缓存直接解包（数据最全最新）。

### A. 从 Nikke-db 拉取（快速、无需游戏本体）

```bash
cd nikke/scripts

# 1. 拉取资源（读取 Nikke-db 索引 l2d.json，按角色下载 fb/cover/aim + 头像图标）
python fetch_nikke.py                 # 全部角色
python fetch_nikke.py c010 c470       # 指定角色
python fetch_nikke.py --limit 60      # 前 60 个（快速验证）

# 2. 生成查看器 manifest（识别姿态 + Spine 版本 + 封面）
python gen_nikke_manifest.py

# 3.（可选）为缺少现成头像图标的角色，用无头浏览器渲染 Spine 生成缩略图
#    需先在仓库根启动 http server，并安装 playwright
CHROMIUM_PATH=<chrome.exe> node gen_thumbs.mjs http://127.0.0.1:8000 ../data
```

- 数据源索引：`https://nikke-db-legacy.pages.dev/js/json/l2d.json`
- 资源规律：`.../l2d/{id}/{id}_00.skel|.atlas|.png`（+ `/cover/`、`/aim/` 变体）
- 头像图标：`.../images/sprite/si_{id}_00_s.png`

### B. 从本地客户端缓存直接解包（数据最全）

游戏客户端把资源以 **content-addressed** 方式缓存在
`<客户端资源目录>/naps/<hash前2位>/<md5>`（无扩展名）。文件头分两种：
- `UnityFS` —— 明文 Unity 包，**约 76%**，UnityPy 可直接解；
- `NKAB`   —— NIKKE 私有加密包，约 24%，暂不支持。

```bash
cd nikke/scripts
# 指定客户端资源目录（默认 Q:/NIKKE_Assets）
export NIKKE_LOCAL_ASSETS=Q:/NIKKE_Assets

python extract_local.py               # 扫全部 256 个桶
python extract_local.py --buckets 00 01   # 只扫指定桶
python extract_local.py --limit 30    # 前 N 个桶（快速验证）

python gen_nikke_manifest.py          # 再生成 manifest
```

- 解包内容：角色技能演出立绘 `c###_00_skillcut`（归为 **skillcut** 姿态）、
  活动剧情 `EventScene_*`、过场 `liberation/MVG/Glass` 等。
- 实测一次全盘：扫 25266 个明文包 → 提取 **345 套 Spine / 344 个角色场景**，缺贴图 0。
- 支持断点续跑（已提取的 skel 存在则跳过）。

**关键技术点**
- **版本自适应**：读 `.skel` 头部 16 字节的版本串（`4.0.x` / `4.1.x`），
  前端选择 `spine-player4.0.js` / `spine-player4.1.js`（`shared/vendor/`）。
- **正确渲染**：`premultipliedAlpha: true` + 透明背景。此前用 pixi-spine 未处理预乘
  alpha 导致立绘发灰/发黑；换用 EsotericSoftware 官方 spine-player 后还原正确。
- **动画回退**：部分 skillcut/场景模型默认动画名不是 `idle`，查看器在 `success`
  回调里按实际可用动画智能选择（默认名 → 含 idle 的 → 第一个），避免报错。
- **封面缩略图**：优先用 Nikke-db 渲染好的头像图标；缺失时用无头浏览器渲染
  Spine、自动裁剪透明边生成缩略图，避免直接显示打乱的图集碎片。

---

## 说明

本工具仅用于个人学习与研究。提取的立绘、Live2D / Spine 模型版权归属各游戏方
（碧蓝航线：Manjuu / Yongshi / Yostar；NIKKE：SHIFT UP / Level Infinite），
请勿商用或公开再分发。
