"""生成 viewer/manifest.json：
  - 立绘按皮肤(skin id)分组，代表图优先 _n_rw > _rw > _n > main
  - Live2D 模型带 id 排序
分组/排序数据来自 config/cfg_json/ship_skin_template.json
"""
import os, sys, json, glob, re
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C

SKIN_TPL = os.path.join(C.CFG_JSON_DIR, "ship_skin_template.json")

PART = ["bg","front","back","shadow","dark_shadow","dark","effect","light",
        "middle","mid","shophx","wjz","jz","pt","tx","s"]
VAR  = ["n","rw","hx","g","ex","hd","bh","h","p","d","renwu"]


def load_skin_map():
    """painting -> {group, id, name, rel}。

    rel = 发布次序权重，取自 shop_id（商店上架序号，随版本递增，是真实的发布时间序）。
    皮肤 id 只是 ship_group*10+group_index（舰船编号），与发布时间无关，不能用来排"最新"。
    无 shop_id 的皮肤（默认皮/非商店皮）用同组兄弟按 group_index 插值估算；仍无从估算则 rel=0。
    """
    skins = json.load(open(SKIN_TPL, encoding="utf-8"))
    p2info = {}
    groups = defaultdict(list)
    for k, v in skins.items():
        if k == "all" or not isinstance(v, dict):
            continue
        p, i, g, nm = v.get("painting"), v.get("id"), v.get("ship_group"), v.get("name", "")
        if p and i is not None:
            shop, gidx = v.get("shop_id"), v.get("group_index")
            info = {"group": g, "id": i, "name": nm,
                    "rel": shop if isinstance(shop, int) and shop > 0 else 0,
                    "gidx": gidx if isinstance(gidx, int) else 0}
            p2info[p.lower()] = info
            if g:
                groups[g].append(info)

    # 兜底：同组内按 group_index 用已知 shop_id 插值，估算缺失皮肤的发布次序
    for items in groups.values():
        known = sorted((x for x in items if x["rel"]), key=lambda x: x["gidx"])
        if not known:
            continue
        for x in items:
            if x["rel"]:
                continue
            lo = [k for k in known if k["gidx"] < x["gidx"]]
            hi = [k for k in known if k["gidx"] > x["gidx"]]
            if lo and hi:
                x["rel"] = (lo[-1]["rel"] + hi[0]["rel"]) // 2
            elif lo:
                x["rel"] = lo[-1]["rel"] + 1
            elif hi:
                x["rel"] = max(hi[0]["rel"] - 1, 1)
    return p2info


def find_info(name, p2info):
    """按 resolve 的同一套后缀剥离规则找皮肤元数据（_hx 等变体继承母皮）。"""
    n = name.lower()
    if n in p2info:
        return p2info[n]
    base, _ = split_suffixes(n)
    if base in p2info:
        return p2info[base]
    base2, _ = split_suffixes(base)
    return p2info.get(base2)


def split_suffixes(name):
    n = name.lower()
    kind = "main"
    toks = n.split("_")
    while len(toks) > 1:
        t = re.sub(r"\d+$", "", toks[-1])
        if t in PART:
            kind = "part"; toks = toks[:-1]
        elif t in VAR:
            if kind != "part": kind = "variant"
            toks = toks[:-1]
        else:
            break
    return "_".join(toks), kind


def resolve(name, p2info):
    n = name.lower()
    if n in p2info:
        info = p2info[n]; return info["group"], info["id"], info["name"], "main"
    base, kind = split_suffixes(n)
    if base in p2info:
        info = p2info[base]; return info["group"], info["id"], info["name"], kind
    base2, k2 = split_suffixes(base)
    if base2 in p2info:
        info = p2info[base2]; return info["group"], info["id"], info["name"], (kind if kind != "main" else k2)
    return None, -1, "", kind


def suffix_count(name):
    return name.count("_")


def moc3_version(moc_path):
    """读 moc3 文件头的版本号(offset 0x04)。1=Cubism3.0, 2=3.3, 3=4.0, 4=4.2, 5=5.0。读不到返回 0。"""
    try:
        with open(moc_path, "rb") as f:
            head = f.read(8)
        if head[:4] != b"MOC3":
            return 0
        return head[4]
    except Exception:
        return 0


def pick_rep(items):
    """代表图优先级：_n_rw > _rw > _n > main > 其他 > 部件。"""
    def score(x):
        n = "_" + x["name"].lower()
        has_rw = "_rw" in n; has_n = "_n" in n; has_hx = "_hx" in n
        kind = x["kind"]
        if kind == "part": tier = 6
        elif has_n and has_rw: tier = 0
        elif has_rw: tier = 1
        elif has_n: tier = 2
        elif kind == "main": tier = 3
        else: tier = 4
        return (tier, 1 if has_hx else 0, suffix_count(x["name"]), len(x["name"]))
    return min(items, key=score)


def generate():
    p2info = load_skin_map()

    # 立绘分组
    paint_files = sorted(glob.glob(os.path.join(C.PAINTINGS_DIR, "*.png")))
    paintings = []
    for f in paint_files:
        name = os.path.splitext(os.path.basename(f))[0]
        group, sid, en, kind = resolve(name, p2info)
        paintings.append({"name": name, "path": f"../data/paintings/{name}.png",
                          "group": group or -1, "skin": sid, "en": en, "kind": kind})

    by_skin = defaultdict(list)
    ungrouped = []
    for p in paintings:
        if p["skin"] and p["skin"] > 0:
            by_skin[p["skin"]].append(p)
        else:
            ungrouped.append(p)

    kind_order = {"main": 0, "variant": 1, "part": 2}
    chars = []
    for sid, items in by_skin.items():
        rep = pick_rep(items)
        items_sorted = sorted(items, key=lambda x: (kind_order.get(x["kind"], 3), suffix_count(x["name"]), x["name"]))
        info = find_info(rep["name"], p2info)
        chars.append({"group": items[0]["group"], "en": rep["en"], "rep": rep["name"],
                      "rep_path": rep["path"], "skin": sid, "rel": (info or {}).get("rel", 0),
                      "items": [{"name": x["name"], "path": x["path"], "kind": x["kind"]} for x in items_sorted]})
    for p in ungrouped:
        chars.append({"group": -1, "en": "", "rep": p["name"], "rep_path": p["path"], "skin": -1, "rel": 0,
                      "items": [{"name": p["name"], "path": p["path"], "kind": p["kind"]}]})

    # Live2D 模型
    paint_names = set(os.path.splitext(os.path.basename(f))[0] for f in paint_files)

    def find_cover(m):
        """为 Live2D 模型匹配立绘封面，优先 _n_rw > _rw > _n > 本名。"""
        cands = [m + "_n_rw", m + "_rw", m + "_n", m]
        if m.endswith("_hx"):
            base = m[:-3]
            cands = [m + "_n_rw", m + "_rw", m + "_n", m,
                     base + "_n_rw_hx", base + "_rw_hx", base + "_n_hx", base + "_hx",
                     base + "_n_rw", base + "_rw", base + "_n", base]
        for c in cands:
            if c in paint_names:
                return f"../data/paintings/{c}.png"
        return None

    models = []
    for d in sorted(os.listdir(C.MODELS_DIR)) if os.path.isdir(C.MODELS_DIR) else []:
        m3 = os.path.join(C.MODELS_DIR, d, f"{d}.model3.json")
        if os.path.exists(m3):
            _, sid, en, _ = resolve(d, p2info)
            ver = moc3_version(os.path.join(C.MODELS_DIR, d, f"{d}.moc3"))
            info = find_info(d, p2info)
            models.append({"name": d, "path": f"../data/models/{d}/{d}.model3.json",
                           "id": sid, "en": en, "cover": find_cover(d), "ver": ver,
                           "rel": (info or {}).get("rel", 0)})

    manifest = {"models": models, "characters": chars}
    os.makedirs(C.VIEWER_DIR, exist_ok=True)
    json.dump(manifest, open(C.MANIFEST_PATH, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    grouped = sum(1 for c in chars if c["skin"] > 0)
    print(f"皮肤组 {len(chars)} (真实 {grouped}), 立绘 {len(paintings)}, 模型 {len(models)}")
    rel_ok = sum(1 for m in models if m["rel"])
    print(f"发布次序(rel) 覆盖: 模型 {rel_ok}/{len(models)}, 皮肤组 {sum(1 for c in chars if c['rel'])}/{len(chars)}")
    print(f"-> {C.MANIFEST_PATH} ({os.path.getsize(C.MANIFEST_PATH)/1024:.0f} KB)")


if __name__ == "__main__":
    generate()
