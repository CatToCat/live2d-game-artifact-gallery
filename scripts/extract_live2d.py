import UnityPy, os, sys, json

def extract_model(bundle, out_dir, model_name):
    os.makedirs(out_dir, exist_ok=True)
    with open(bundle, "rb") as fp:
        env = UnityPy.load(fp.read())   # 用 bytes 加载，兼容无扩展名文件
    moc = None
    physics = None
    textures = {}
    for o in env.objects:
        t = o.type.name
        if t == "MonoBehaviour":
            try:
                tt = o.read_typetree()
            except Exception:
                continue
            if "_bytes" in tt and tt.get("_bytes"):
                b = tt["_bytes"]
                data = bytes(b) if not isinstance(b, (bytes, bytearray)) else b
                # moc3 magic = 'MOC3'
                if data[:4] == b"MOC3":
                    moc = data
        elif t == "TextAsset":
            d = o.read()
            raw = bytes(d.m_Script) if not isinstance(d.m_Script, str) else d.m_Script.encode("utf-8","surrogateescape")
            if d.m_Name.endswith("physics3") or raw[:20].find(b'"Physics"')>=0 or b'"PhysicsSettings"' in raw[:200] or d.m_Name.lower().find("physics")>=0:
                physics = raw
        elif t == "Texture2D":
            d = o.read()
            textures[d.m_Name] = d.image

    # 写 moc3
    if moc:
        with open(os.path.join(out_dir, f"{model_name}.moc3"), "wb") as fp:
            fp.write(moc)
    else:
        print(f"  [WARN] no moc3 for {model_name}")

    # 写贴图（按名字排序 -> texture_00 .. texture_NN）
    tex_files = []
    for name in sorted(textures.keys()):
        fn = f"{name}.png"
        textures[name].save(os.path.join(out_dir, fn))
        tex_files.append(fn)

    # 写 physics
    physics_file = None
    if physics:
        physics_file = f"{model_name}.physics3.json"
        with open(os.path.join(out_dir, physics_file), "wb") as fp:
            fp.write(physics)

    # 生成 model3.json
    refs = {"Moc": f"{model_name}.moc3", "Textures": tex_files}
    if physics_file:
        refs["Physics"] = physics_file
    model3 = {
        "Version": 3,
        "FileReferences": refs,
        "Groups": [
            {"Target": "Parameter", "Name": "EyeBlink", "Ids": []},
            {"Target": "Parameter", "Name": "LipSync", "Ids": []},
        ],
    }
    with open(os.path.join(out_dir, f"{model_name}.model3.json"), "w", encoding="utf-8") as fp:
        json.dump(model3, fp, ensure_ascii=False, indent=2)

    print(f"  {model_name}: moc3={'ok' if moc else 'MISSING'} tex={len(tex_files)} physics={'ok' if physics else 'no'}")
    return moc is not None

if __name__ == "__main__":
    # 单文件调试：python extract_live2d.py <bundle路径> <输出目录> <模型名>
    import sys
    if len(sys.argv) >= 4:
        extract_model(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        print("用法: python extract_live2d.py <bundle> <out_dir> <name>")
        print("批量还原请用: python build.py live2d")
