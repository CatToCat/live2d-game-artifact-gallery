"""项目路径与配置中心。所有脚本从这里取路径，改结构只需改这里。"""
import os

# 项目根 = 本文件的上级目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 目录结构
DATA_DIR       = os.path.join(ROOT, "data")
MODELS_DIR     = os.path.join(DATA_DIR, "models")        # Live2D 模型还原产物
PAINTINGS_DIR  = os.path.join(DATA_DIR, "paintings")     # 立绘 PNG
CACHE_DIR      = os.path.join(ROOT, "cache", "AssetBundles")  # 下载的原始 bundle
CONFIG_DIR     = os.path.join(ROOT, "config")
HASHES_DIR     = os.path.join(CONFIG_DIR, "hashes")      # 版本清单 CSV
CFG_JSON_DIR   = os.path.join(CONFIG_DIR, "cfg_json")    # 角色配置(分组/排序用)
VIEWER_DIR     = os.path.join(ROOT, "viewer")
MANIFEST_PATH  = os.path.join(VIEWER_DIR, "manifest.json")

# 各类 bundle 子目录
PAINTING_BUNDLE = os.path.join(CACHE_DIR, "painting")
LIVE2D_BUNDLE   = os.path.join(CACHE_DIR, "live2d")

# EN 服 CDN / 网关（bilibili CN 服见 README）
CDN  = "https://blhxusstatic.yo-star.com/android"
GATE = ("blhxusgate.yo-star.com", 80)
USER_AGENT = "AzurLaneAssetBot/1.0"

# 代理（海外 CDN；在 GitHub Actions 等海外环境可关掉）
USE_PROXY  = True
PROXY_HTTP = "http://127.0.0.1:7897"
PROXY_SOCKS = ("127.0.0.1", 7897)

# 要处理的资源类型（版本 hashname -> 本地清单名）
WANT_TYPES = {"paintinghash": "PAINTING", "l2dhash": "L2D", "pichash": "PIC"}

UNITY_FALLBACK_VERSION = "2022.3.51f1"

# ---- 社区元数据（皮肤分组/名称/发布次序）----
# CDN 上的资源名不含"哪个角色哪个皮肤"，靠这份配置表补充。
# 官方 sharecfgdata/ship_skin_template 是蛮啾自定义二进制容器（非 Unity/非压缩/
# 非单字节异或，字段名亦被编码），自行解析需逆向 il2cpp，故复用社区已 dump 的成果。
# 按顺序尝试，第一个通过完整性校验的即采用。
SKIN_TPL_NAME = "ship_skin_template.json"
SKIN_TPL_SOURCES = [
    # 主源：JSON，直接可用
    ("Fernando2603/raw", "json",
     "https://raw.githubusercontent.com/Fernando2603/AzurLaneData/main/sharecfgdata/ship_skin_template.json"),
    # 备源1：同一文件的 jsDelivr 镜像（换 host，raw 被墙时仍可达）
    ("Fernando2603/jsdelivr", "json",
     "https://cdn.jsdelivr.net/gh/Fernando2603/AzurLaneData@main/sharecfgdata/ship_skin_template.json"),
    # 备源2：AzurLaneTools 的 Lua 原始脚本（更新更勤，需转换）
    ("AzurLaneTools/lua", "lua",
     "https://raw.githubusercontent.com/AzurLaneTools/AzurLaneLuaScripts/main/EN/sharecfgdata/ship_skin_template.lua"),
]
# 完整性下限：带 painting 字段的条目数低于此值视为残缺文件，拒绝写入。
# （上游 sharecfg/ 下存在 148KB 残缺版，解析出 0 条 painting，必须挡掉）
SKIN_TPL_MIN_ENTRIES = 2000
