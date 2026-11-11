"""从 Nikke-db CDN 拉取 NIKKE 立绘/模型（Spine）资源。

流程：
  1. 拉取 l2d.json 索引（name/id/version）。
  2. 对每个角色，尝试三种姿态 fb / cover / aim：
       fb   : {id}/{id}_00.skel|.atlas + atlas 引用的所有 .png
       cover: {id}/cover/{id}_cover_00.skel|.atlas + .png
       aim  : {id}/aim/{id}_aim_00.skel|.atlas + .png
  3. 解析 atlas 拿到全部贴图页文件名，逐个下载。
  4. 已存在且大小 >0 的文件跳过（可断点续传）。

用法：
    python fetch_nikke.py             # 拉全部
    python fetch_nikke.py c010 c470   # 只拉指定 id
    python fetch_nikke.py --limit 20  # 只拉前 20 个（快速验证）
"""
import os
import sys
import json
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import config as C


def make_session():
    s = requests.Session()
    if C.PROXY:
        s.proxies.update({"http": C.PROXY, "https": C.PROXY})
    # Cloudflare Pages（nikke-db-legacy.pages.dev）会对缺少 UA/Referer 的请求返回 403，
    # 需伪装为浏览器并带上 Referer 才能正常拿到资源。
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0 Safari/537.36"),
        "Referer": "https://nikke-db-legacy.pages.dev/",
    })
    return s


def fetch_index(session):
    urls = [
        getattr(C, "INDEX_URL", None),
        getattr(C, "INDEX_URL_MIRROR", None),
        getattr(C, "INDEX_URL_LEGACY", None),
    ]
    for url in urls:
        if not url:
            continue
        for attempt in range(3):
            try:
                r = session.get(url, timeout=30)
                r.raise_for_status()
                data = r.json()
                if isinstance(data, list) and len(data) > 50:
                    cached = os.path.join(C.DATA_DIR, "_l2d_index.json")
                    os.makedirs(C.DATA_DIR, exist_ok=True)
                    try:
                        with open(cached, "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                    return data
            except Exception:
                time.sleep(1)
                continue
    # 兜底：若网络拉取失败，尝试使用本地已有缓存
    cached = os.path.join(C.DATA_DIR, "_l2d_index.json")
    if os.path.exists(cached):
        print("  [提示] 使用本地缓存的 l2d.json 索引")
        return json.load(open(cached, encoding="utf-8"))
    raise RuntimeError("无法获取 l2d.json 索引")


def download(session, url, dest):
    """下载单个文件；已存在且非空则跳过。返回 (ok, size, skipped)。"""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True, os.path.getsize(dest), True
    tmp = dest + ".part"
    for attempt in range(3):
        try:
            r = session.get(url, timeout=60, stream=True)
            if r.status_code != 200 or r.headers.get("content-type", "").startswith("text/html"):
                return False, 0, False
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            n = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
                    n += len(chunk)
            os.replace(tmp, dest)
            return True, n, False
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            if attempt < 2:
                time.sleep(0.5)
    return False, 0, False


def parse_atlas_pages(atlas_text):
    """解析 atlas，返回引用的所有 .png 文件名（按出现顺序）。"""
    pages = []
    for line in atlas_text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if line.endswith(".png") and line not in pages:
            pages.append(line)
    return pages


_INDEX_CACHE = None


def get_index_entry(cid):
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        idx_path = os.path.join(C.DATA_DIR, "_l2d_index.json")
        if os.path.exists(idx_path):
            try:
                data = json.load(open(idx_path, encoding="utf-8"))
                _INDEX_CACHE = {e["id"]: e for e in data}
            except Exception:
                _INDEX_CACHE = {}
        else:
            _INDEX_CACHE = {}
    return _INDEX_CACHE.get(cid, {})


def pose_paths(cid, pose, f_name=None):
    """返回 (远端子路径前缀, skel名, atlas名) 用于该姿态。"""
    if not f_name:
        f_name = get_index_entry(cid).get("f")
    if pose == "fb":
        stem = f_name if f_name else f"{cid}_00"
        sub = ""
    else:
        stem = f"{cid}_{pose}_00"
        sub = f"{pose}/"
    return sub, f"{stem}.skel", f"{stem}.atlas"


def get_local_pose(cid, pose, f_name=None):
    """检查本地是否已完整拥有该姿态（skel + atlas + 所有贴图 png）。如果是，直接返回描述字典。"""
    sub, skel_name, atlas_name = pose_paths(cid, pose, f_name)
    local_dir = os.path.join(C.DATA_DIR, cid, sub.rstrip("/")) if sub else os.path.join(C.DATA_DIR, cid)
    skel_path = os.path.join(local_dir, skel_name)
    atlas_path = os.path.join(local_dir, atlas_name)
    if not (os.path.exists(skel_path) and os.path.getsize(skel_path) > 0 and
            os.path.exists(atlas_path) and os.path.getsize(atlas_path) > 0):
        # 兼容已有以 f_name(小写) 为目录名的情况（例如 eventscene_terminusticket_01）
        if f_name and pose == "fb":
            alt_dir = os.path.join(C.DATA_DIR, f_name.lower())
            if os.path.isdir(alt_dir):
                alt_skel = os.path.join(alt_dir, skel_name)
                alt_atlas = os.path.join(alt_dir, atlas_name)
                if (os.path.exists(alt_skel) and os.path.getsize(alt_skel) > 0 and
                        os.path.exists(alt_atlas) and os.path.getsize(alt_atlas) > 0):
                    return {
                        "pose": pose,
                        "sub": "",
                        "skel": skel_name,
                        "atlas": atlas_name,
                        "pages": parse_atlas_pages(open(alt_atlas, "r", encoding="utf-8", errors="ignore").read()),
                    }
        return None
    try:
        with open(atlas_path, "r", encoding="utf-8", errors="ignore") as f:
            pages = parse_atlas_pages(f.read())
    except Exception:
        return None
    if not pages:
        return None
    for p in pages:
        png_path = os.path.join(local_dir, p)
        if not (os.path.exists(png_path) and os.path.getsize(png_path) > 0):
            return None
    return {
        "pose": pose,
        "sub": sub,
        "skel": skel_name,
        "atlas": atlas_name,
        "pages": pages,
    }


def fetch_pose(session, cid, pose, f_name=None):
    """拉取某角色某姿态。返回 dict 描述（None 表示该姿态不存在）。"""
    local_info = get_local_pose(cid, pose, f_name)
    if local_info:
        return local_info

    sub, skel_name, atlas_name = pose_paths(cid, pose, f_name)
    base_url = f"{C.CDN_BASE}/{cid}/{sub}"
    local_dir = os.path.join(C.DATA_DIR, cid, sub.rstrip("/")) if sub else os.path.join(C.DATA_DIR, cid)

    # 先探测 atlas 是否存在
    atlas_url = base_url + atlas_name
    ra = None
    for _ in range(3):
        try:
            ra = session.get(atlas_url, timeout=30)
            if ra.status_code == 200 and ra.content:
                if not ra.headers.get("content-type", "").startswith("text/html"):
                    break
        except Exception:
            pass
        time.sleep(0.5)
    if ra is None or ra.status_code != 200 or not ra.content or ra.headers.get("content-type", "").startswith("text/html"):
        return None
    atlas_text = ra.content.decode("utf-8", "ignore")
    pages = parse_atlas_pages(atlas_text)
    if not pages:
        return None

    # 写 atlas
    os.makedirs(local_dir, exist_ok=True)
    with open(os.path.join(local_dir, atlas_name), "wb") as f:
        f.write(ra.content)

    # 下载 skel
    ok_skel, _, _ = download(session, base_url + skel_name,
                             os.path.join(local_dir, skel_name))
    if not ok_skel:
        return None

    # 下载全部贴图页
    for png in pages:
        download(session, base_url + png, os.path.join(local_dir, png))

    return {
        "pose": pose,
        "sub": sub,
        "skel": skel_name,
        "atlas": atlas_name,
        "pages": pages,
    }


def fetch_character(session, entry):
    cid = entry["id"]
    f_val = entry.get("f")
    if not f_val:
        f_val = get_index_entry(cid).get("f")
    name = entry.get("name")
    if not name or name == cid:
        name = get_index_entry(cid).get("name", cid)

    result = {"id": cid, "name": name, "poses": {}}
    if "version" in entry:
        result["version"] = entry["version"]
    if f_val:
        result["f"] = f_val

    # only_missing=True 时只补抓本地尚不存在的姿态（用于扫描补漏，不重复下载）
    only_missing = entry.get("only_missing", False)
    for pose in C.POSES:
        if only_missing and _pose_exists_local(cid, pose, f_val):
            continue
        info = fetch_pose(session, cid, pose, f_val)
        if info:
            result["poses"][pose] = info
    if not result["poses"]:
        return None
    # 头像图标（渲染好的 128x128，用作列表封面）
    icon = fetch_icon(session, cid)
    if icon:
        result["icon"] = icon
    return result


def _pose_exists_local(cid, pose, f_name=None):
    """本地是否已存在该姿态的 skel（用于扫描模式跳过已抓取的姿态）。"""
    sub, skel_name, _ = pose_paths(cid, pose, f_name)
    local_dir = (os.path.join(C.DATA_DIR, cid, sub.rstrip("/"))
                 if sub else os.path.join(C.DATA_DIR, cid))
    skel = os.path.join(local_dir, skel_name)
    if os.path.exists(skel) and os.path.getsize(skel) > 0:
        return True
    if f_name and pose == "fb":
        alt_skel = os.path.join(C.DATA_DIR, f_name.lower(), skel_name)
        if os.path.exists(alt_skel) and os.path.getsize(alt_skel) > 0:
            return True
    return False


def fetch_icon(session, cid):
    """下载 si_{id}_00_s.png 头像图标；返回本地文件名或 None。
    Cloudflare Pages 对缺失文件返回 200 + HTML，需按 content-type 甄别。"""
    dest = os.path.join(C.DATA_DIR, cid, "_icon.png")
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return "_icon.png"
    url = f"{C.SPRITE_BASE}/si_{cid}_00_s.png"
    try:
        r = session.get(url, timeout=30)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    if not r.headers.get("content-type", "").startswith("image"):
        return None
    dest = os.path.join(C.DATA_DIR, cid, "_icon.png")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(r.content)
    return "_icon.png"


def scan_existing_ids():
    """扫描 data/ 下已有的角色目录，返回符合 cNNN[_skin] 命名的 id 列表。

    用于补漏：Nikke-db 的 l2d.json 索引并不完整（例如 c515 及大量角色未收录），
    但 CDN 上其 fb/cover/aim 资源实际存在。这些角色往往只由 extract_local.py
    从本地客户端缓存提取到 skillcut，缺少常规立绘/半身/瞄准。
    """
    import re
    ids = []
    for name in sorted(os.listdir(C.DATA_DIR)):
        p = os.path.join(C.DATA_DIR, name)
        if not os.path.isdir(p):
            continue
        # 仅处理标准角色 id（c + 3位数字，可带 _NN 皮肤后缀）
        if re.match(r"^c\d{3}(_\d{2})?$", name):
            ids.append(name)
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", help="只拉取指定角色 id")
    ap.add_argument("--limit", type=int, default=0, help="只拉前 N 个角色")
    ap.add_argument("--new-only", action="store_true",
                    help="仅拉取本地 manifest 尚未收录的新角色/新条目")
    ap.add_argument("--scan-existing", action="store_true",
                    help="不依赖索引，扫描 data/ 已有角色目录逐个补抓 CDN 上的 fb/cover/aim")
    ap.add_argument("--only-missing", action="store_true",
                    help="仅补抓本地尚不存在的姿态（配合 --scan-existing 使用，避免重复下载）")
    args = ap.parse_args()

    session = make_session()

    if args.scan_existing:
        ids = scan_existing_ids()
        if args.ids:
            wanted = set(args.ids)
            ids = [i for i in ids if i in wanted]
        if args.limit:
            ids = ids[: args.limit]
        # 扫描模式下无索引名字，用 id 占位
        index = [{"id": i, "name": i, "only_missing": args.only_missing}
                 for i in ids]
        print(f"扫描到 {len(index)} 个已有角色目录，逐个探测 CDN 补抓姿态")
    else:
        print("拉取索引 ...")
        index = fetch_index(session)
        print(f"索引共 {len(index)} 个条目")

        if args.new_only and os.path.exists(C.MANIFEST_PATH):
            try:
                m = json.load(open(C.MANIFEST_PATH, encoding="utf-8"))
                have_ids = set(c["id"] for c in m.get("characters", []))
                index = [e for e in index if e["id"] not in have_ids and (not e.get("f") or e["f"].lower() not in have_ids)]
                print(f"过滤后剩余 {len(index)} 个未收录新条目")
            except Exception:
                pass

        if args.ids:
            wanted = set(args.ids)
            index = [e for e in index if e["id"] in wanted]
        if args.limit:
            index = index[: args.limit]
        print(f"本次处理 {len(index)} 个角色")

    os.makedirs(C.DATA_DIR, exist_ok=True)
    results = []
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=C.WORKERS) as ex:
        futs = {ex.submit(fetch_character, make_session(), e): e for e in index}
        done = 0
        for fut in as_completed(futs):
            e = futs[fut]
            done += 1
            try:
                r = fut.result()
            except Exception as ex_err:
                print(f"  [{done}/{len(index)}] {e['id']:14s} 失败: {ex_err}")
                continue
            if r:
                poses = ",".join(r["poses"].keys())
                results.append(r)
                print(f"  [{done}/{len(index)}] {e['id']:14s} OK ({poses})")
            else:
                print(f"  [{done}/{len(index)}] {e['id']:14s} 无资源，跳过")

    # 保存本次抓取到的角色元数据，并与已有历史合并，供 manifest 生成使用
    meta_path = os.path.join(C.DATA_DIR, "_fetched.json")
    all_meta = {}
    if os.path.exists(meta_path):
        try:
            for item in json.load(open(meta_path, encoding="utf-8")):
                all_meta[item["id"]] = item
        except Exception:
            pass
    for item in results:
        all_meta[item["id"]] = item

    json.dump(list(all_meta.values()), open(meta_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n完成 {len(results)}/{len(index)} 个角色，用时 {time.time()-t0:.1f}s")
    print(f"元数据已合并 ({len(all_meta)} 条) -> {meta_path}")


if __name__ == "__main__":
    main()
