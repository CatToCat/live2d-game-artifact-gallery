"""一键自动更新：拉元数据 -> 拉最新清单 -> 增量下载 -> 还原变化的资源 -> 刷新 manifest。
用法:
  python update.py            # 完整增量更新(立绘+Live2D)
  python update.py --full     # 忽略缓存，全量重下重建
  python update.py --skip-meta  # 跳过社区元数据更新
只处理相比上次有变化(新增/hash变更)的资源，已有的跳过。

依赖: azlassets(拿版本/清单), UnityPy, Pillow, numpy, requests, PySocks(代理)
"""
import os, sys, shutil, glob, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PREV_HASHES = os.path.join(C.CONFIG_DIR, "hashes_prev")   # 上次的清单，用于对比


def _rows(csv_path):
    d = {}
    if not os.path.exists(csv_path):
        return d
    for line in open(csv_path, encoding="utf-8"):
        p = line.strip().split(",")
        if len(p) >= 3:
            d[p[0]] = (int(p[1]) if p[1].isdigit() else 0, p[2])  # path -> (size, md5)
    return d


def changed_files(label):
    """对比新旧清单，返回 (变化的 path 集合)。首次全量。"""
    new = _rows(os.path.join(C.HASHES_DIR, f"{label}.csv"))
    old = _rows(os.path.join(PREV_HASHES, f"{label}.csv"))
    changed = set()
    for path, (size, md5) in new.items():
        if path not in old or old[path][1] != md5:
            changed.add(path)
    return changed, new


def main(full=False, skip_meta=False):
    print("=" * 50)
    print("碧蓝航线资源自动更新")
    print("=" * 50)

    # 0) 社区元数据(皮肤名/分组/发布次序)。失败不阻断，仅影响新皮肤的分组。
    print("\n[1/5] 更新社区元数据...")
    if skip_meta:
        print("  已跳过 (--skip-meta)")
    else:
        try:
            from fetch_metadata import fetch as fetch_meta
            fetch_meta()
        except Exception as e:
            print(f"  元数据更新异常({type(e).__name__}: {e})，继续后续步骤")

    # 1) 拉最新清单
    print("\n[2/5] 获取最新版本清单...")
    from fetch_manifests import fetch
    fetch()

    # 2) 计算增量
    print("\n[3/5] 计算增量...")
    to_download = {}     # label -> set(path)
    for label in C.WANT_TYPES.values():
        if full:
            ch, new = None, _rows(os.path.join(C.HASHES_DIR, f"{label}.csv"))
            to_download[label] = set(new.keys())
        else:
            ch, new = changed_files(label)
            to_download[label] = ch
        print(f"  {label}: {len(to_download[label])} 个变化")

    # 3) 增量下载 + 还原
    print("\n[4/5] 下载并还原...")
    from dl_from_csv import download
    import build

    total_changed = sum(len(v) for v in to_download.values())
    if total_changed == 0 and not full:
        print("  无变化，已是最新。")
    else:
        # 已知变化的文件强制 md5 校验：清单里 hash 变了但字节数没变时，
        # 光比大小会误判为"已存在"而跳过，导致内容永远停留在旧版本。
        for label in C.WANT_TYPES.values():
            paths = to_download.get(label) or set()
            if full:
                download([label])
            elif paths:
                download([label], verify=True, only=paths)
        # 还原：立绘变化则清除对应 done 记录使其重建；简单起见变化多就整体重建
        paint_changed = to_download.get("PAINTING", set()) | to_download.get("PIC", set())
        l2d_changed = to_download.get("L2D", set())
        if paint_changed or full:
            # 移除已变化立绘的 done 记录，触发重建
            _invalidate_paint_done(paint_changed if not full else None)
            build.build_paintings()
        if l2d_changed or full:
            build.build_live2d()

    # 4) 刷新 manifest + 保存本次清单供下次对比
    print("\n[5/5] 刷新 manifest...")
    import gen_manifest
    gen_manifest.generate()
    _save_prev_hashes()
    _sync_counts()

    print("\n更新完成。启动查看器: python -m http.server 8000  然后打开 /azur_lane/viewer/")


def _invalidate_paint_done(changed_paths):
    """使变化的立绘重新构建：从 .paint_done.txt 删除对应行。changed_paths=None 表示全部。"""
    done_file = os.path.join(SCRIPTS, ".paint_done.txt")
    if not os.path.exists(done_file):
        return
    if changed_paths is None:
        os.remove(done_file)
        return
    # changed_paths 是 'painting/xxx' 形式；done 里存的是完整 bundle 路径
    keep = []
    for line in open(done_file, encoding="utf-8"):
        f = line.strip()
        if not f:
            continue
        rel = "painting/" + os.path.basename(f)
        if rel not in changed_paths:
            keep.append(f)
    open(done_file, "w", encoding="utf-8").write("\n".join(keep) + "\n")


def _save_prev_hashes():
    os.makedirs(PREV_HASHES, exist_ok=True)
    for label in C.WANT_TYPES.values():
        src = os.path.join(C.HASHES_DIR, f"{label}.csv")
        if os.path.exists(src):
            shutil.copy(src, os.path.join(PREV_HASHES, f"{label}.csv"))


def _sync_counts():
    """把 manifest 的实际数量回写到首页/README 的硬编码文案，避免手动改漏。"""
    import json, re
    try:
        m = json.load(open(C.MANIFEST_PATH, encoding="utf-8"))
    except Exception as e:
        print(f"  计数同步跳过: 读不到 manifest ({e})")
        return
    n_model = len(m.get("models", []))
    chars = m.get("characters", [])
    n_paint = sum(len(c.get("items", [])) for c in chars)
    n_group = len(chars)
    repo = os.path.dirname(C.ROOT)   # 仓库根(azur_lane 的上级)

    edits = [
        (os.path.join(repo, "index.html"),
         [(r'(<span class="tag">Live2D · )\d+(</span>)', rf'\g<1>{n_model}\g<2>'),
          (r'(<span class="tag">立绘 · )\d+(</span>)', rf'\g<1>{n_paint}\g<2>')]),
        (os.path.join(repo, "README.md"),
         [(r'(- \*\*立绘\*\*：)\d+( 张（按皮肤分组，)\d+( 个皮肤组）)',
           rf'\g<1>{n_paint}\g<2>{n_group}\g<3>'),
          (r'(- \*\*Live2D\*\*：)\d+( 个模型)', rf'\g<1>{n_model}\g<2>')]),
    ]
    for path, subs in edits:
        if not os.path.exists(path):
            continue
        try:
            src = open(path, encoding="utf-8").read()
            out = src
            for pat, rep in subs:
                out = re.sub(pat, rep, out)
            if out != src:
                open(path, "w", encoding="utf-8", newline="").write(out)
                print(f"  计数已同步: {os.path.basename(path)}")
        except Exception as e:
            print(f"  计数同步失败 {os.path.basename(path)}: {e}")


if __name__ == "__main__":
    main(full="--full" in sys.argv, skip_meta="--skip-meta" in sys.argv)
