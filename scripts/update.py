"""一键自动更新：拉最新清单 -> 增量下载 -> 还原变化的资源 -> 刷新 manifest。
用法:
  python update.py            # 完整增量更新(立绘+Live2D)
  python update.py --full     # 忽略缓存，全量重下重建
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


def main(full=False):
    print("=" * 50)
    print("碧蓝航线资源自动更新")
    print("=" * 50)

    # 1) 拉最新清单
    print("\n[1/4] 获取最新版本清单...")
    from fetch_manifests import fetch
    fetch()

    # 2) 计算增量
    print("\n[2/4] 计算增量...")
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
    print("\n[3/4] 下载并还原...")
    from dl_from_csv import download
    import build

    total_changed = sum(len(v) for v in to_download.values())
    if total_changed == 0 and not full:
        print("  无变化，已是最新。")
    else:
        # 下载(dl_from_csv 内部按 size 判断，已有的自动跳过)
        download(list(C.WANT_TYPES.values()))
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
    print("\n[4/4] 刷新 manifest...")
    import gen_manifest
    gen_manifest.generate()
    _save_prev_hashes()

    print("\n更新完成。启动查看器: python -m http.server 8000  然后打开 /viewer/")


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


if __name__ == "__main__":
    main(full="--full" in sys.argv)
