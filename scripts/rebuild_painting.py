"""BLHX 立绘重建（纯 PIL + numpy，无需 opencv）。
对 Mesh 每个三角形：源(UV->图集像素) -> 目标(顶点->画布像素) 做仿射变换。
用 PIL.Image.transform(AFFINE) 变换整张图集，再用三角形 mask 贴到画布。
"""
import UnityPy, numpy as np
from PIL import Image, ImageDraw, ImageChops
import sys

def get_mesh_data(mesh):
    """从 UnityPy 导出的 OBJ 解析 顶点/UV/面。"""
    obj = mesh.export()
    V, VT, F = [], [], []
    for line in obj.splitlines():
        if line.startswith("v "):
            _, x, y, z = line.split()
            V.append((float(x), float(y)))
        elif line.startswith("vt "):
            parts = line.split()
            VT.append((float(parts[1]), float(parts[2])))
        elif line.startswith("f "):
            idxs = [int(p.split("/")[0]) - 1 for p in line.split()[1:]]
            F.append(idxs[:3])
    verts = np.array(V, dtype=np.float32)
    uvs = np.array(VT, dtype=np.float32)
    faces = np.array(F, dtype=np.int64).reshape(-1)
    return verts, uvs, faces

def affine_from_tri(src, dst):
    """求把 dst 三角形映射回 src 的仿射系数 (PIL 需要 dst->src 方向)。"""
    # PIL AFFINE: 输出像素(x,y) 用 (a,b,c,d,e,f) 映射到源: sx=a*x+b*y+c, sy=d*x+e*y+f
    A = np.array([
        [dst[0][0], dst[0][1], 1, 0, 0, 0],
        [0, 0, 0, dst[0][0], dst[0][1], 1],
        [dst[1][0], dst[1][1], 1, 0, 0, 0],
        [0, 0, 0, dst[1][0], dst[1][1], 1],
        [dst[2][0], dst[2][1], 1, 0, 0, 0],
        [0, 0, 0, dst[2][0], dst[2][1], 1],
    ], dtype=np.float64)
    b = np.array([src[0][0], src[0][1], src[1][0], src[1][1], src[2][0], src[2][1]], dtype=np.float64)
    try:
        coeffs = np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        return None
    return tuple(coeffs)

def _mesh_arrays(mesh):
    verts, uvs, indices = get_mesh_data(mesh)
    return verts, uvs, indices

def _composite(canvas, atlas, verts, uvs, indices, minx, maxy):
    aw, ah = atlas.size
    for i in range(0, len(indices)-2, 3):
        tri = indices[i:i+3]
        src = [(uvs[t][0]*aw, (1-uvs[t][1])*ah) for t in tri]
        dst = [(vx-minx, maxy-vy) for vx, vy in ((verts[t][0], verts[t][1]) for t in tri)]
        xs = [p[0] for p in dst]; ys = [p[1] for p in dst]
        bx0, by0 = int(np.floor(min(xs))), int(np.floor(min(ys)))
        bx1, by1 = int(np.ceil(max(xs))), int(np.ceil(max(ys)))
        bw, bh = bx1-bx0, by1-by0
        if bw<=0 or bh<=0: continue
        dst_local = [(p[0]-bx0, p[1]-by0) for p in dst]
        coeffs = affine_from_tri(src, dst_local)
        if coeffs is None: continue
        piece = atlas.transform((bw, bh), Image.AFFINE, coeffs, resample=Image.BILINEAR)
        mask = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(mask).polygon(dst_local, fill=255)
        # 关键修复：三角形 mask 里，把 piece 自身近乎全透明(alpha<24)的像素剔除。
        # 图集透明区 RGB 常是垃圾深灰值，若强行按三角形 mask 贴上会显形(脸上灰块)。
        # 仅剔除 alpha<24 的，保留正常边缘抗锯齿(中高 alpha)，避免边缘变硬。
        pa = np.array(piece.getchannel("A"))
        m = np.array(mask)
        m[pa < 24] = 0
        mask = Image.fromarray(m)
        canvas.paste(piece, (bx0, by0), mask)

def rebuild(tex_file, out_png):
    with open(tex_file, "rb") as fp:
        env = UnityPy.load(fp.read())   # bytes 加载，兼容无扩展名
    textures = []
    meshes = []
    for o in env.objects:
        if o.type.name == "Texture2D":
            textures.append(o.read())
        elif o.type.name == "Mesh":
            meshes.append(o.read())
    if not textures:
        print("  no texture"); return
    if not meshes:
        textures[0].image.convert("RGBA").save(out_png)
        print("  no mesh, saved raw"); return

    # 去重完全相同的 mesh（同名+同顶点数视为重复，取一个）
    uniq = []
    seen = set()
    for m in meshes:
        v, u, idx = _mesh_arrays(m)
        if len(v) == 0 or len(idx) < 3:
            continue
        key = (getattr(m, "m_Name", ""), len(v), len(idx),
               round(float(v[:,0].min()),1), round(float(v[:,0].max()),1))
        if key in seen:
            continue
        seen.add(key)
        uniq.append((v, u, idx))
    if not uniq:
        textures[0].image.convert("RGBA").save(out_png)
        print("  no mesh data, saved raw"); return

    # 全局包围盒（覆盖所有 mesh）
    all_x = np.concatenate([v[:,0] for v,_,_ in uniq])
    all_y = np.concatenate([v[:,1] for v,_,_ in uniq])
    minx, maxx, miny, maxy = all_x.min(), all_x.max(), all_y.min(), all_y.max()
    W, H = int(round(maxx-minx)), int(round(maxy-miny))
    if W<=0 or H<=0: print("  bad size"); return

    canvas = Image.new("RGBA", (W, H), (0,0,0,0))
    atlases = [t.image.convert("RGBA") for t in textures]

    # 每个 mesh 配一张贴图：mesh 数<=tex 数时按序配；否则多余 mesh 用第一张
    for mi, (v, u, idx) in enumerate(uniq):
        atlas = atlases[mi] if mi < len(atlases) else atlases[0]
        _composite(canvas, atlas, v, u, idx, minx, maxy)

    canvas.save(out_png)
    print(f"  rebuilt {W}x{H} ({len(uniq)}mesh/{len(atlases)}tex) -> {out_png}")

if __name__ == "__main__":
    rebuild(sys.argv[1], sys.argv[2])
