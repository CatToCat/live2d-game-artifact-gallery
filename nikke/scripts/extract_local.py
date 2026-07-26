"""从本地游戏客户端缓存直接解包 NIKKE 立绘 / Spine 模型。

数据源：Q:/NIKKE_Assets/naps/<hash前2位>/<md5>  （content-addressed 缓存）
  - 文件头 "UnityFS" = 明文 Unity 包，UnityPy 可直接解
  - 文件头 "NKAB"    = NIKKE 私有加密包（跳过）

流程：
  1. 遍历 naps/ 下所有桶，逐包检测文件头。
  2. 对明文 UnityFS 包：若含 TextAsset(*.skel) 则视为 Spine 模型包，
     提取该包内 *.skel / *.atlas + atlas 引用的 Texture2D 贴图。
  3. 按 skel 名解析角色 id 与姿态，归类到 nikke/data/{id}/[cover|aim]/。

skel 命名规律（与 Nikke-db 对齐）：
  c233_00_skillcut       -> id=c233, pose=fb
  c010_cover_00          -> id=c010, pose=cover
  c010_aim_00            -> id=c010, pose=aim
  EventScene_LifeAgain_01-> id=eventscene_lifeagain（活动，pose=fb）
  liberation_3           -> id=liberation_3（pose=fb）

用法：
  python extract_local.py                 # 全盘扫描
  python extract_local.py --buckets 00 01 # 只扫指定桶
  python extract_local.py --limit 30      # 前 N 个桶（快速验证）
"""
import os
import re
import argparse

import UnityPy

import config as C


def read_text_asset(obj):
    """返回 (name, bytes)。UnityPy 的 m_Script 可能是 str 或 bytes。"""
    data = obj.read()
    nm = data.m_Name
    raw = data.m_Script
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "surrogateescape")
    return nm, raw


def atlas_pages(atlas_bytes):
    """解析 atlas 文本，返回引用的 png 文件名列表。"""
    pages = []
    for line in atlas_bytes.decode("utf-8", "ignore").splitlines():
        line = line.strip().lstrip("\ufeff")
        if line.endswith(".png") and line not in pages:
            pages.append(line)
    return pages


def classify(skel_name):
    """由 skel 文件名解析出 (id, pose, out_stem)。

    返回归类信息，让输出文件名与 Nikke-db 约定一致，方便 manifest 复用。
    """
    stem = skel_name[:-5] if skel_name.endswith(".skel") else skel_name

    # 角色技能演出立绘: c233_00_skillcut / c101_01_skillcut(皮肤)
    m = re.match(r"^(c\d{3})(?:_(\d{2}))?_skillcut$", stem)
    if m:
        cid, skin = m.group(1), m.group(2)
        if skin and skin != "00":
            cid = f"{cid}_{skin}"
        return cid, "skillcut", stem

    # 角色常规立绘: c010_00 / c101_01
    m = re.match(r"^(c\d{3})(?:_(\d{2}))?(?:_(cover|aim))?$", stem)
    if m:
        cid, skin, pose = m.group(1), m.group(2), m.group(3)
        if skin and skin != "00":
            cid = f"{cid}_{skin}"
        pose = pose or "fb"
        return cid, pose, stem

    # 显式 cover/aim: xxx_cover_00 / xxx_aim_00
    m = re.match(r"^(.+?)_(cover|aim)_\d{2}$", stem)
    if m:
        return m.group(1), m.group(2), stem

    # 其它（EventScene / liberation / MVG / Glass 等）：整体作为一个 id
    cid = stem.lower()
    return cid, "fb", stem


def out_dir_for(cid, pose):
    base = os.path.join(C.DATA_DIR, cid)
    return base if pose == "fb" else os.path.join(base, pose)

def process_bundle(path, stats):
    """处理单个明文 UnityFS 包；若含 skel 则提取整套 Spine 资源。"""
    try:
        env = UnityPy.load(path)
    except Exception:
        stats["load_fail"] += 1
        return

    # 先收集包内所有 TextAsset / Texture2D
    text_assets = {}   # name -> bytes
    textures = {}      # name(带/不带.png) -> PIL Image
    skels = []
    for o in env.objects:
        t = o.type.name
        if t == "TextAsset":
            try:
                nm, raw = read_text_asset(o)
                text_assets[nm] = raw
                if nm.endswith(".skel"):
                    skels.append(nm)
            except Exception:
                pass
        elif t == "Texture2D":
            try:
                d = o.read()
                textures[d.m_Name] = d.image
            except Exception:
                pass

    if not skels:
        return

    # 每个 skel 生成一套输出
    for skel_name in skels:
        cid, pose, stem = classify(skel_name)
        atlas_name = stem + ".atlas"
        atlas_bytes = text_assets.get(atlas_name)
        if atlas_bytes is None:
            # 有些包 atlas 名不带 stem 后缀，尝试任意 .atlas
            cand = [n for n in text_assets if n.endswith(".atlas")]
            if len(cand) == 1:
                atlas_name, atlas_bytes = cand[0], text_assets[cand[0]]
        if atlas_bytes is None:
            stats["no_atlas"] += 1
            continue

        odir = out_dir_for(cid, pose)
        os.makedirs(odir, exist_ok=True)

        skel_out = os.path.join(odir, stem + ".skel")
        # 断点续跑：已提取过（skel 存在且非空）则跳过
        if os.path.exists(skel_out) and os.path.getsize(skel_out) > 0:
            stats["skipped"] += 1
            continue

        # 写 skel / atlas（用 stem 统一命名，便于 manifest：{stem}.skel/.atlas）
        with open(skel_out, "wb") as f:
            f.write(text_assets[skel_name])
        with open(os.path.join(odir, stem + ".atlas"), "wb") as f:
            f.write(atlas_bytes)

        # 写 atlas 引用的贴图
        pages = atlas_pages(atlas_bytes)
        missing = []
        for png in pages:
            key = png[:-4] if png.endswith(".png") else png
            img = textures.get(key) or textures.get(png)
            if img is None:
                missing.append(png)
                continue
            img.save(os.path.join(odir, png))
        if missing:
            stats["tex_missing"] += 1
        stats["spine"] += 1
        stats["ids"].add(cid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buckets", nargs="*", help="只扫描指定桶（如 00 01）")
    ap.add_argument("--limit", type=int, default=0, help="只扫前 N 个桶")
    args = ap.parse_args()

    naps = os.path.join(C.LOCAL_ASSETS, "naps")
    if not os.path.isdir(naps):
        print(f"找不到本地资源目录: {naps}")
        return

    buckets = args.buckets or sorted(os.listdir(naps))
    if args.limit:
        buckets = buckets[: args.limit]

    stats = {"unityfs": 0, "nkab": 0, "spine": 0, "no_atlas": 0,
             "tex_missing": 0, "load_fail": 0, "skipped": 0, "ids": set()}

    for i, bk in enumerate(buckets):
        d = os.path.join(naps, bk)
        if not os.path.isdir(d):
            continue
        files = os.listdir(d)
        for fn in files:
            p = os.path.join(d, fn)
            try:
                with open(p, "rb") as f:
                    head = f.read(7)
            except Exception:
                continue
            if head[:4] == b"NKAB":
                stats["nkab"] += 1
                continue
            if head != b"UnityFS":
                continue
            stats["unityfs"] += 1
            process_bundle(p, stats)
        print(f"  [{i+1}/{len(buckets)}] 桶 {bk} 完成  "
              f"(明文 {stats['unityfs']}, NKAB {stats['nkab']}, "
              f"Spine {stats['spine']}, 角色 {len(stats['ids'])})", flush=True)

    print("\n=== 解包完成 ===")
    print(f"明文包 {stats['unityfs']}  NKAB加密 {stats['nkab']}  加载失败 {stats['load_fail']}")
    print(f"提取 Spine 套数 {stats['spine']}  跳过(已存在) {stats['skipped']}  角色/场景 {len(stats['ids'])}")
    print(f"缺贴图 {stats['tex_missing']}  无 atlas {stats['no_atlas']}")


if __name__ == "__main__":
    main()
