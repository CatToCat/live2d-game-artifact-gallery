# live2d-game-artifact-gallery

游戏资源解包 & 展示平台。从游戏客户端提取**立绘、Live2D 模型、音频**等美术制品，
还原成网页可直接查看的格式，并提供带搜索/分组/排序/动作播放的查看器。

> 当前已完整支持 **碧蓝航线（Azur Lane）**；架构设计为可扩展到其他游戏，
> 每个游戏的资源定位/解密/重建逻辑以插件式脚本接入。

**碧蓝航线现状**：
- **立绘**：5798 张（按皮肤分组，3043 个皮肤组）
- **Live2D**：259 个模型，每个含 14 个动作（idle / home / 触摸 / 任务 / 结婚 等）
- 支持**本地一键自动更新**：拉取最新版本 → 增量下载 → 还原 → 刷新查看器

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
cd live2d-game-artifact-gallery/scripts
python update.py          # 增量更新：只处理相比上次有变化的资源
python update.py --full   # 全量重建（忽略缓存）
```

流程：
1. **握手拿版本** → 下载最新 hash 清单到 `config/hashes/`
2. **增量对比** → 与 `config/hashes_prev/` 比对，找出新增/变更的资源
3. **下载 + 还原** → 只下变化的 bundle，重建对应立绘/模型/动作
4. **刷新 manifest** → 更新查看器分组数据，保存本次清单供下次对比

### 网络说明
- 脚本默认走本地代理 `127.0.0.1:7897`（海外 CDN，国内需要）。
  在海外服务器 / GitHub Actions 上运行时，把 `scripts/config.py` 的 `USE_PROXY = False`。
- gate 握手是 **raw TCP socket**（不走 HTTP 代理），代理时用 SOCKS5；
  资源下载走 HTTPS（HTTP 代理）。

---

## 单步执行（调试用）

```bash
cd live2d-game-artifact-gallery/scripts
python fetch_manifests.py            # 只拉最新清单
python dl_from_csv.py L2D            # 只下 Live2D 的 bundle（PAINTING/PIC/L2D）
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

## 说明

本工具仅用于个人学习与研究。提取的立绘、Live2D 模型版权归属游戏方
（Manjuu / Yongshi / Yostar），请勿商用或公开再分发。
