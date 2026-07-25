"""生成 NIKKE Spine 资源的 manifest。
扫描 data/nikke/<角色>/，每个角色找主 skel/atlas + 封面图，输出 viewer/nikke_manifest.json
"""
import os, json, glob

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NIKKE_DIR = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "viewer", "nikke_manifest.json")

def atlas_png(atlas_path):
    try:
        with open(atlas_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.endswith(".png"):
                    return line
    except Exception:
        pass
    return None

def main():
    chars = []
    if not os.path.isdir(NIKKE_DIR):
        print("无 data/nikke 目录"); return
    for role in sorted(os.listdir(NIKKE_DIR)):
        rdir = os.path.join(NIKKE_DIR, role)
        if not os.path.isdir(rdir):
            continue
        skels = sorted(glob.glob(os.path.join(rdir, "*.skel")))
        if not skels:
            continue
        skel = os.path.basename(skels[0])
        atlas_files = sorted(glob.glob(os.path.join(rdir, "*.atlas")))
        atlas = os.path.basename(atlas_files[0]) if atlas_files else None
        cover = None
        if atlas:
            png = atlas_png(os.path.join(rdir, atlas))
            if png and os.path.exists(os.path.join(rdir, png)):
                cover = png
        if not cover:
            pngs = glob.glob(os.path.join(rdir, "*.png"))
            if pngs:
                cover = os.path.basename(pngs[0])
        chars.append({
            "name": role,
            "dir": f"../data/{role}",
            "skel": skel,
            "atlas": atlas,
            "cover": f"../data/{role}/{cover}" if cover else None,
        })
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"characters": chars}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"NIKKE 角色 {len(chars)} -> {OUT}")

if __name__ == "__main__":
    main()
