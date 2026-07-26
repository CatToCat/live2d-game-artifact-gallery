"""NIKKE 资源拉取 / 构建配置。

数据来源：社区 Nikke-db 项目托管的已解包 Spine 资源。
    索引:   https://raw.githubusercontent.com/Nikke-db/Nikke-db.github.io/main/js/json/l2d.json
    资源:   https://nikke-db-legacy.pages.dev/l2d/{id}/{id}_00.skel  (+ .atlas / .png)
            https://nikke-db-legacy.pages.dev/l2d/{id}/cover/{id}_cover_00.skel
            https://nikke-db-legacy.pages.dev/l2d/{id}/aim/{id}_aim_00.skel

NIKKE 立绘 = Spine 4.0 / 4.1 骨骼动画。skel 头 16 字节含版本号 "4.0.x"/"4.1.x"。
"""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # nikke/
DATA_DIR = os.path.join(BASE, "data")
VIEWER_DIR = os.path.join(BASE, "viewer")
MANIFEST_PATH = os.path.join(VIEWER_DIR, "nikke_manifest.json")

# 数据源（优先用 Cloudflare Pages，比 raw.githubusercontent 稳定得多）
INDEX_URL = "https://nikke-db-legacy.pages.dev/js/json/l2d.json"
INDEX_URL_MIRROR = "https://raw.githubusercontent.com/Nikke-db/Nikke-db.github.io/main/js/json/l2d.json"
CDN_BASE = "https://nikke-db-legacy.pages.dev/l2d"
# 渲染好的头像图标（用于列表封面，避免直接用打包 atlas 显示为碎片）
SPRITE_BASE = "https://nikke-db-legacy.pages.dev/images/sprite"
# 备用镜像（pages.dev 不可用时可切换）
CDN_MIRROR = "https://raw.githubusercontent.com/Nikke-db/Nikke-db.github.io/main/l2d"

# 姿态：full body / cover / aim
POSES = ("fb", "cover", "aim")

# 代理（与 azur_lane 保持一致，直连留空即可）
PROXY = os.environ.get("NIKKE_PROXY", "http://127.0.0.1:7897")

# 下载并发
WORKERS = 8

# ── 本地客户端资源解包（从游戏 content-addressed 缓存直接提取）────────────
# 目录结构: <LOCAL_ASSETS>/naps/<hash前2位>/<md5>  (无扩展名)
#   文件头 "UnityFS" = 明文 Unity 包（UnityPy 可直接解）
#   文件头 "NKAB"    = NIKKE 私有加密包（暂不支持）
LOCAL_ASSETS = os.environ.get("NIKKE_LOCAL_ASSETS", "Q:/NIKKE_Assets")
