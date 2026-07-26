# 碧蓝航线（Azur Lane）数据源与工具说明

本文说明碧蓝航线美术资源（立绘 / Live2D）的**数据来源**、**本地文件位置**、
以及**拆解 → 重组**用到的工具链。所有脚本在 `azur_lane/scripts/`。

---

## 一、数据源（全部来自官方 CDN + 社区元数据）

碧蓝航线不需要拿到游戏本体安装包，资源直接从 **Yostar 官方 CDN** 按需下载。
流程是：先跟**版本网关**握手拿到最新版本号 → 用版本号拉 **hash 清单** → 按清单里的
md5 从 CDN 拉原始 Unity bundle。

### 1. 官方资源 CDN / 版本网关

| 用途 | 地址 | 说明 |
|------|------|------|
| 资源 CDN（EN 国际服） | `https://blhxusstatic.yo-star.com/android` | Yostar 官方静态资源 CDN |
| 版本网关（EN 国际服） | `blhxusgate.yo-star.com:80` | raw TCP + protobuf 握手拿版本号 |
| 资源 CDN（CN bilibili 服） | `https://line3-patch-blhx.bilibiligame.net` | 国服 CDN |
| 版本网关（CN bilibili 服） | `line1-login-bili-blhx.bilibiligame.net` | 国服网关 |

配置位置：`azur_lane/scripts/config.py`
```python
CDN  = "https://blhxusstatic.yo-star.com/android"
GATE = ("blhxusgate.yo-star.com", 80)
```
切换 CN 服：把上面两行改成 bilibili 服地址即可。

### 2. 资源下载 URL 规则

- **hash 清单**：`{CDN}/hash/{versionhash}`
  （`versionhash` 由 gate 握手后返回，见 `parse_version_string`）
- **资源文件**：`{CDN}/resource/{md5}`
  （`md5` 取自 hash 清单 CSV 的第 3 列）

我们关注三类资源（`config.py` 的 `WANT_TYPES`）：

| 版本 hashname | 本地清单名 | 内容 |
|---------------|-----------|------|
| `paintinghash` | `PAINTING` | 立绘贴图碎片图集 |
| `l2dhash` | `L2D` | Live2D 模型包（moc3 / 贴图 / physics / 动作） |
| `pichash` | `PIC` | 立绘相关图片 |

### 3. 角色分组 / 发布顺序（社区元数据）

CDN 上的资源文件名不含"这是哪个角色的哪个皮肤"这类信息，需要外部元数据补充。

| 内容 | 来源 |
|------|------|
| 皮肤分组 / 发布顺序 / 中英文名 | 社区数据库 [`Fernando2603/AzurLaneData`](https://github.com/Fernando2603/AzurLaneData) 的 `ship_skin_template.json` |

本地缓存位置：`azur_lane/config/cfg_json/ship_skin_template.json`
- 以皮肤 `id`（递增 = 发布顺序）为分组键
- 提供 `painting`（立绘名）→ `ship_group` / `id` / `name` 的映射

---

## 二、本地文件位置

```
azur_lane/
├── config/
│   ├── hashes/                 # 拉下来的版本清单 CSV（path,size,md5）
│   │   ├── PAINTING.csv
│   │   ├── L2D.csv
│   │   ├── PIC.csv
│   │   └── AZL.csv
│   ├── hashes_prev/            # 上一次的清单，用于增量对比（update.py 生成）
│   └── cfg_json/
│       └── ship_skin_template.json   # 社区元数据（分组/排序）
├── cache/
│   └── AssetBundles/           # 下载的原始 Unity bundle（增量对比用，可达 ~10GB）
│       ├── painting/           #   立绘 bundle（*_tex）
│       └── live2d/             #   Live2D bundle
├── data/                       # 还原产物（查看器直接读）
│   ├── paintings/<name>.png    #   立绘完整 PNG
│   └── models/<name>/          #   Live2D 一整套
│       ├── <name>.moc3
│       ├── <name>.model3.json
│       ├── <name>.physics3.json
│       ├── texture_*.png
│       └── motions/*.motion3.json
└── viewer/
    └── manifest.json           # 查看器清单（分组/代表图/排序，脚本生成）
```

> **注意**：`cache/AssetBundles/` 是原始下载缓存，用于增量更新比对；`data/` 才是
> 还原后可直接展示的产物。清单 CSV 的每行是 `path,size,md5`。

---

## 三、拆解 → 重组工具链

依赖（`requirements.txt`）：
- `azlassets` —— 碧蓝航线资源工具（版本握手 + 拉 hash 清单）
- `UnityPy` —— 解析 Unity AssetBundle
- `Pillow` / `numpy` —— 立绘 Mesh 重建
- `requests` / `PySocks` —— 下载 + SOCKS/HTTP 代理

### 全流程（一键）

```bash
cd azur_lane/scripts
python update.py          # 增量更新：只处理变化的资源
python update.py --full   # 全量重下重建
```

`update.py` 流程：
1. 握手拿版本 → 下载最新 hash 清单到 `config/hashes/`
2. 与 `config/hashes_prev/` 比对，找出新增/变更（md5 不同）的资源
3. 下载变化的 bundle → 还原立绘/模型/动作
4. 刷新 `viewer/manifest.json`，保存本次清单供下次对比

### 分步（调试）

| 脚本 | 作用 |
|------|------|
| `fetch_manifests.py` | gate 握手拿版本 → 下载各类型 hash 清单 CSV |
| `dl_from_csv.py [PAINTING\|L2D\|PIC]` | 按清单多线程下载 bundle（断点续传，按 size 跳过已有） |
| `build.py painting` | 立绘还原（子进程串行，防内存崩溃，可断点续传） |
| `build.py live2d` | Live2D 还原（moc3 + 贴图 + physics + 动作） |
| `rebuild_painting.py <tex> <out.png>` | 单张立绘重建（供调试） |
| `extract_live2d.py <bundle> <dir> <name>` | 单个 Live2D 模型提取（供调试） |
| `motion_convert.py <bundle> <dir>` | 单个 bundle 的动作转换（供调试） |
| `gen_manifest.py` | 生成查看器 manifest（分组/代表图/排序） |

### 关键技术点

**1. 立绘重建（`rebuild_painting.py`）**
碧蓝航线立绘贴图是**打乱的碎片图集**，无法直接看。重建方法：
- 用 UnityPy 从 bundle 里取出 `Texture2D`（图集）和 `Mesh`（顶点 + UV）
- 对 Mesh 的每个三角形，做「源(UV→图集像素) → 目标(顶点→画布像素)」的仿射变换
  （`PIL.Image.transform(AFFINE)`），把碎片重排回完整立绘
- 边缘处理：剔除三角形 mask 内 `alpha < 24` 的垃圾像素（图集透明区 RGB 常是深灰值，
  强贴会在脸上出现灰块），保留中高 alpha 的抗锯齿边缘
- 支持多贴图合成、mesh 去重

**2. Live2D 提取（`extract_live2d.py`）**
从 bundle 提取：`moc3`（MonoBehaviour 里 magic=`MOC3` 的 `_bytes`）、贴图
（Texture2D）、physics（TextAsset）、生成标准 `model3.json`。

**3. 动作转换（`motion_convert.py`）**
Live2D 动作在 Unity 里是 `AnimationClip` 的 `StreamedClip` + `ConstantClip` 二进制曲线。
转换方法：
- 用 binding path 的 **CRC32** 反查 Live2D 参数名（如 `Parameters/ParamAngleX`）
- 解 StreamedClip 的 Hermite 曲线系数（取 `coeff[3]` 作为该帧 value）
- 组装成标准 `motion3.json`（Linear segment）

**4. 分组（`gen_manifest.py`）**
- 分组键 = 皮肤 id（`ship_skin_template.json`），id 递增对应发布顺序
- 代表图优先级：`_n_rw > _rw > _n > main > 其他 > 部件`
- moc3 版本从文件头 offset 0x04 读取（1=Cubism3.0 … 5=5.0）

---

## 四、网络说明

- 脚本默认走本地代理 `127.0.0.1:7897`（海外 CDN，国内需要）。
  海外服务器 / GitHub Actions 上把 `config.py` 的 `USE_PROXY = False`。
- gate 握手是 **raw TCP socket**（不走 HTTP 代理），代理时用 **SOCKS5**；
  资源下载走 HTTPS（HTTP 代理）。

---

## 五、版权说明

仅用于个人学习研究。立绘 / Live2D 版权归属碧蓝航线（Manjuu / Yongshi / Yostar），
请勿商用或公开再分发。
