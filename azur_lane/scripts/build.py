"""从 cache/AssetBundles/ 的 bundle 还原全部资源：
  立绘 PNG -> data/paintings/
  Live2D 模型(moc3+贴图+physics+motion+model3) -> data/models/
用法:
  python build.py painting   # 只还原立绘
  python build.py live2d     # 只还原 Live2D(含动作)
  python build.py            # 全部
稳定优先：立绘用 2 路子进程串行(防内存崩溃)，可断点续传。
"""
import os, sys, glob, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def build_paintings():
    """立绘：调 _paint_worker.py 分 2 路子进程串行还原(稳定)。"""
    texs = sorted(f for f in glob.glob(os.path.join(C.PAINTING_BUNDLE, "*_tex")) if os.path.isfile(f))
    os.makedirs(C.PAINTINGS_DIR, exist_ok=True)
    done_file = os.path.join(SCRIPTS, ".paint_done.txt")
    done = set(x for x in open(done_file).read().split("\n") if x) if os.path.exists(done_file) else set()
    todo = [f for f in texs if f not in done]
    print(f"立绘: 总 {len(texs)}, 待处理 {len(todo)}", flush=True)
    while todo:
        NPAR = 2
        chunks = [todo[i::NPAR] for i in range(NPAR)]
        lists = []
        for i, ch in enumerate(chunks):
            lf = os.path.join(SCRIPTS, f".paint_chunk_{i}.txt")
            open(lf, "w").write("\n".join(ch))
            lists.append(lf)
        procs = [subprocess.Popen([PY, "-u", os.path.join(SCRIPTS, "_paint_worker.py"), lf]) for lf in lists]
        for p in procs:
            p.wait()
        done = set(x for x in open(done_file).read().split("\n") if x) if os.path.exists(done_file) else set()
        todo = [f for f in texs if f not in done]
        print(f"  本轮后完成 {len(done)}/{len(texs)}", flush=True)
        if not procs:
            break
    print("立绘还原完成", flush=True)


def build_live2d(only=None):
    """Live2D：还原 moc3+贴图+physics+model3，并生成 motion。
    only: 可选的 'live2d/<name>' 或 '<name>' 集合，只重建这些模型（增量更新用）。
    """
    import UnityPy
    UnityPy.config.FALLBACK_UNITY_VERSION = C.UNITY_FALLBACK_VERSION
    from extract_live2d import extract_model
    from motion_convert import build_path_map, clip_to_motion3

    bundles = sorted(f for f in glob.glob(os.path.join(C.LIVE2D_BUNDLE, "*")) if os.path.isfile(f))
    if only:
        want = {p.split("/")[-1] for p in only}
        bundles = [b for b in bundles if os.path.basename(b) in want]
    os.makedirs(C.MODELS_DIR, exist_ok=True)
    print(f"Live2D: {len(bundles)} 模型", flush=True)
    ok = fail = 0
    for i, b in enumerate(bundles, 1):
        name = os.path.basename(b)
        model_dir = os.path.join(C.MODELS_DIR, name)
        try:
            has = extract_model(b, model_dir, name)
            if not has:
                fail += 1
                continue
            # 生成动作
            env = UnityPy.load(open(b, "rb").read())
            pmap = build_path_map(env)
            motions_dir = os.path.join(model_dir, "motions")
            os.makedirs(motions_dir, exist_ok=True)
            entries = {}
            for o in env.objects:
                if o.type.name == "AnimationClip":
                    try:
                        tt = o.read_typetree()
                        mn = tt["m_Name"]
                        motion = clip_to_motion3(tt, pmap)
                        if motion["Meta"]["CurveCount"] == 0:
                            continue
                        fn = f"{mn}.motion3.json"
                        json.dump(motion, open(os.path.join(motions_dir, fn), "w", encoding="utf-8"),
                                  ensure_ascii=False, separators=(",", ":"))
                        entries.setdefault(mn, []).append({"File": f"motions/{fn}"})
                    except Exception:
                        continue
            if entries:
                m3p = os.path.join(model_dir, f"{name}.model3.json")
                m3 = json.load(open(m3p, encoding="utf-8"))
                m3["FileReferences"]["Motions"] = entries
                json.dump(m3, open(m3p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  FAIL {name}: {e}", flush=True)
        if i % 30 == 0 or i == len(bundles):
            print(f"  {i}/{len(bundles)} ok={ok} fail={fail}", flush=True)
    print(f"Live2D 还原完成 ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    names = set(sys.argv[2:]) or None      # 可选：只重建指定模型
    if what in ("painting", "all"):
        build_paintings()
    if what in ("live2d", "all"):
        build_live2d(only=names)
