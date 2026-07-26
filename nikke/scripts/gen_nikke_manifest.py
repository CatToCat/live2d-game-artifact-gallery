"""生成 NIKKE Spine 资源的 manifest。

扫描 data/<id>/ 目录，识别三种姿态：
    fb   : {id}_00.skel|.atlas          （立绘全身，默认）
    cover: cover/{id}_cover_00.skel|.atlas
    aim  : aim/{id}_aim_00.skel|.atlas

同时兼容旧的 EventScene 目录（无姿态子目录，直接放 .skel/.atlas/.png）。
每条记录读取 skel 头部 16 字节，识别 Spine 版本（4.0 / 4.1）供前端选择 runtime。
封面优先用 fb 的首张贴图。
输出 viewer/nikke_manifest.json。
"""
import os
import re
import json
import glob

import config as C

VERSION_RE = re.compile(rb"([34]\.[0-9]+\.[0-9]+)")


def detect_version(skel_path):
    """读 skel 头部识别 Spine 版本，返回 '4.0' / '4.1' / '3.8' 等（主次版本）。"""
    try:
        with open(skel_path, "rb") as f:
            head = f.read(64)
        m = VERSION_RE.search(head)
        if m:
            full = m.group(1).decode()
            return ".".join(full.split(".")[:2])
    except Exception:
        pass
    return "4.1"


def atlas_pages(atlas_path):
    pages = []
    try:
        with open(atlas_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip().lstrip("\ufeff")
                if line.endswith(".png") and line not in pages:
                    pages.append(line)
    except Exception:
        pass
    return pages


def find_pose(rdir, cid, pose):
    """返回该姿态的 {skel, atlas, pages, dir}（相对 rdir），找不到返回 None。

    不假设固定文件名，而是扫描对应目录里实际存在的 skel/atlas，
    以兼容 Nikke-db 命名({cid}_00) 和本地解包命名({cid}_00_skillcut) 等。
    """
    pdir = rdir if pose == "fb" else os.path.join(rdir, pose)
    if not os.path.isdir(pdir):
        return None
    skels = sorted(glob.glob(os.path.join(pdir, "*.skel")))
    atlases = sorted(glob.glob(os.path.join(pdir, "*.atlas")))
    if not skels or not atlases:
        return None
    # fb 目录下可能混有多个 skel（不同来源），优先取与 atlas 同名的一组
    skel = skels[0]
    atlas = atlases[0]
    stem = os.path.splitext(os.path.basename(skel))[0]
    same = os.path.join(pdir, stem + ".atlas")
    if os.path.exists(same):
        atlas = same
    return {
        "sub": "" if pose == "fb" else pose,
        "skel": os.path.basename(skel),
        "atlas": os.path.basename(atlas),
        "pages": atlas_pages(atlas),
        "version": detect_version(skel),
    }


def scan_legacy(rdir, cid):
    """兼容旧 EventScene：任意 .skel + .atlas（无姿态命名规范）。"""
    skels = sorted(glob.glob(os.path.join(rdir, "*.skel")))
    atlases = sorted(glob.glob(os.path.join(rdir, "*.atlas")))
    if not skels or not atlases:
        return None
    skel = os.path.basename(skels[0])
    atlas = os.path.basename(atlases[0])
    return {
        "sub": "",
        "skel": skel,
        "atlas": atlas,
        "pages": atlas_pages(os.path.join(rdir, atlas)),
        "version": detect_version(os.path.join(rdir, skel)),
    }


def load_name_map():
    """构建 id->显示名 映射，多来源合并（优先级低->高）：
      1. 现有 manifest（保留此前已解析出的真实名字，避免被覆盖）
      2. CDN 索引 l2d.json（若能读到）
      3. _fetched.json（本次抓取；扫描补漏时 name 可能是 id 占位）

    注意：_fetched.json 在 --scan-existing 补漏后其 name 多为 id 占位，
    不能让它覆盖来源 1/2 里已有的真实名字，因此占位名（name==id）不参与覆盖。
    """
    names = {}

    # 1. 现有 manifest 的名字（最先加载，作为基础，后续来源仅补充/覆盖为“非占位”名）
    if os.path.exists(C.MANIFEST_PATH):
        try:
            m = json.load(open(C.MANIFEST_PATH, encoding="utf-8"))
            for c in m.get("characters", []):
                if c.get("name") and c["name"] != c["id"]:
                    names[c["id"]] = c["name"]
        except Exception:
            pass

    # 2. CDN 索引 l2d.json（本地缓存或运行时不一定可用，容错处理）
    idx_path = os.path.join(C.DATA_DIR, "_l2d_index.json")
    if os.path.exists(idx_path):
        try:
            for e in json.load(open(idx_path, encoding="utf-8")):
                if e.get("name"):
                    names[e["id"]] = e["name"]
        except Exception:
            pass

    # 3. _fetched.json —— 仅采用“非占位”名字（name != id），避免覆盖真实名
    meta_path = os.path.join(C.DATA_DIR, "_fetched.json")
    if os.path.exists(meta_path):
        try:
            for e in json.load(open(meta_path, encoding="utf-8")):
                nm = e.get("name", e["id"])
                if nm and nm != e["id"]:
                    names[e["id"]] = nm
        except Exception:
            pass

    return names


def categorize(cid):
    """给条目打分类标签，用于前端导航/筛选。

    character : 角色（c### / c###_皮肤）
    event     : 活动剧情立绘（eventscene*）
    story     : 主线过场/剧情（chapter*/mvg*/*glass*/*chap*/liberation*/timeline*）
    misc      : 其它（BB / 道具 / 未归类）
    """
    i = cid.lower()
    if re.match(r"^c\d{3}(_\d+)?$", i):
        return "character"
    if i.startswith("eventscene"):
        return "event"
    if (i.startswith("chapter") or i.startswith("mvg") or i.startswith("liberation")
            or i.startswith("timeline") or "glass" in i or "chap" in i or "anarchyorr" in i):
        return "story"
    return "misc"


def cover_url(cid, pose_info):
    """封面优先用渲染好的头像图标 _icon.png；否则退回姿态首张贴图（可能是碎片 atlas）。"""
    icon = os.path.join(C.DATA_DIR, cid, "_icon.png")
    if os.path.exists(icon) and os.path.getsize(icon) > 0:
        return f"../data/{cid}/_icon.png"
    if pose_info and pose_info.get("pages"):
        sub = pose_info["sub"]
        prefix = f"../data/{cid}/{sub}/" if sub else f"../data/{cid}/"
        return prefix + pose_info["pages"][0]
    return None


def main():
    names = load_name_map()
    chars = []
    if not os.path.isdir(C.DATA_DIR):
        print("无 data 目录")
        return

    for cid in sorted(os.listdir(C.DATA_DIR)):
        rdir = os.path.join(C.DATA_DIR, cid)
        if not os.path.isdir(rdir):
            continue

        poses = {}
        for pose in ("fb", "cover", "aim", "skillcut"):
            info = find_pose(rdir, cid, pose)
            if info:
                poses[pose] = info

        # 若标准命名没找到，尝试旧 EventScene 结构
        if not poses:
            legacy = scan_legacy(rdir, cid)
            if legacy:
                poses["fb"] = legacy

        if not poses:
            continue

        fb = poses.get("fb") or next(iter(poses.values()))
        chars.append({
            "id": cid,
            "name": names.get(cid, cid),
            "dir": f"../data/{cid}",
            "category": categorize(cid),
            "poses": poses,
            "version": fb["version"],
            "cover": cover_url(cid, fb),
        })

    os.makedirs(C.VIEWER_DIR, exist_ok=True)
    json.dump({"characters": chars}, open(C.MANIFEST_PATH, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"NIKKE 角色 {len(chars)} -> {C.MANIFEST_PATH}")
    # 版本 + 分类统计
    from collections import Counter
    vc = Counter(c["version"] for c in chars)
    cc = Counter(c["category"] for c in chars)
    print("版本分布:", dict(vc))
    print("分类分布:", dict(cc))


if __name__ == "__main__":
    main()
