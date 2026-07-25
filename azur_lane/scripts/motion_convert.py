"""Unity AnimationClip -> Live2D motion3.json 转换器。
处理 BLHX Live2D 的 AnimationClip：解 StreamedClip + ConstantClip 曲线，
用 binding path 的 CRC32 反查 Live2D 参数名，生成标准 motion3.json。
"""
import struct, json, binascii, math


def crc32(s):
    return binascii.crc32(s.encode("utf-8")) & 0xFFFFFFFF


class StreamedClipReader:
    """解 Unity StreamedClip 的 uint32 数组为关键帧。
    格式：每帧 = [time(float), keyCount(uint), (curveIndex, coeff[4])*keyCount]
    coeff 是 Hermite 曲线系数，coeff[3] 是该曲线在该帧的 value。
    """
    def __init__(self, data_u32):
        # data_u32: list[int] (uint32)。转成 bytes 便于按 float/int 读
        self.buf = b"".join(struct.pack("<I", x & 0xFFFFFFFF) for x in data_u32)
        self.pos = 0
        self.n = len(self.buf)

    def _u32(self):
        v = struct.unpack_from("<I", self.buf, self.pos)[0]; self.pos += 4; return v
    def _f32(self):
        v = struct.unpack_from("<f", self.buf, self.pos)[0]; self.pos += 4; return v

    def read(self):
        """返回 {curveIndex: [(time, value), ...]}"""
        curves = {}
        while self.pos + 8 <= self.n:
            time = self._f32()
            keycount = self._u32()
            if keycount > 100000:  # 防御异常
                break
            for _ in range(keycount):
                if self.pos + 20 > self.n:
                    return curves
                idx = self._u32()
                # coeff[0..3]，coeff[3] 是 value（Hermite 常数项）
                c0 = self._f32(); c1 = self._f32(); c2 = self._f32(); c3 = self._f32()
                curves.setdefault(idx, []).append((time, c3))
        return curves


def build_path_map(env):
    """建立 {crc32(相对路径): 参数名} 映射。
    Unity binding path 是 Transform 相对路径(去掉根节点)的 CRC32，如 'Parameters/ParamAngleX'。"""
    gos = {}     # transform pathid -> gameobject 名
    trans = {}   # transform pathid -> typetree
    for o in env.objects:
        if o.type.name == "GameObject":
            gos[o.path_id] = o.read().m_Name
    go_by_pid = {}
    for o in env.objects:
        if o.type.name == "GameObject":
            go_by_pid[o.path_id] = o.read().m_Name
    tr_of_go = {}
    for o in env.objects:
        if o.type.name == "Transform":
            d = o.read_typetree()
            trans[o.path_id] = d
            tr_of_go[d["m_GameObject"]["m_PathID"]] = o.path_id

    def full_path(tr_pid):
        parts = []
        cur = tr_pid
        seen = set()
        while cur in trans and cur not in seen:
            seen.add(cur)
            d = trans[cur]
            parts.append(go_by_pid.get(d["m_GameObject"]["m_PathID"], "?"))
            fpid = d["m_Father"]["m_PathID"]
            if fpid == 0:
                break
            cur = fpid
        return list(reversed(parts))

    m = {}
    for tr_pid, d in trans.items():
        parts = full_path(tr_pid)
        if len(parts) <= 1:
            continue
        name = parts[-1]
        # 去掉根节点后的相对路径
        rel = "/".join(parts[1:])
        m[crc32(rel)] = name
        # 也登记纯名字兜底
        m.setdefault(crc32(name), name)
    return m


def clip_to_motion3(tt, path_map, fps=30.0):
    """把一个 AnimationClip 的 typetree 转成 motion3.json dict。"""
    mc = tt["m_MuscleClip"]["m_Clip"]["data"]
    stream = mc["m_StreamedClip"]
    const = mc["m_ConstantClip"]
    binding = tt["m_ClipBindingConstant"]["genericBindings"]
    stop_time = tt["m_MuscleClip"]["m_StopTime"]

    # binding index -> 参数名（用 path 的 crc 反查）
    def bind_name(i):
        if i < len(binding):
            p = binding[i]["path"]
            return path_map.get(p, None)
        return None

    curves_out = []  # motion3 的 Curve 列表

    # 1) StreamedClip 曲线
    sc = StreamedClipReader(stream["data"])
    streamed = sc.read()   # {curveIndex: [(t,v)]}
    stream_curve_count = stream["curveCount"]
    for idx, kfs in streamed.items():
        name = bind_name(idx)
        if not name or not kfs:
            continue
        seg = []
        for t, v in kfs:
            seg += [t, v]
        curves_out.append(("Parameter", name, kfs))

    # 2) ConstantClip 曲线（恒定值，从 streamCount 之后的 index 开始）
    const_data = const["data"]
    for j, v in enumerate(const_data):
        idx = stream_curve_count + j
        name = bind_name(idx)
        if not name:
            continue
        # 常量曲线：起止两个关键帧
        curves_out.append(("Parameter", name, [(0.0, v), (stop_time, v)]))

    # 组装 motion3.json
    motion_curves = []
    total_segments = 0
    total_points = 0
    for target, pid, kfs in curves_out:
        # 过滤哨兵帧(time 为极端负值)，只保留 time>=0
        kfs = [(t, v) for t, v in kfs if t > -1e30]
        if not kfs:
            continue
        # 去重同时间点、按时间排序
        kfs = sorted(kfs, key=lambda x: x[0])
        seg = [round(kfs[0][0], 4), round(kfs[0][1], 6)]
        for t, v in kfs[1:]:
            seg += [0, round(t, 4), round(v, 6)]   # 0 = Linear segment
            total_segments += 1
        total_points += len(kfs)
        motion_curves.append({"Target": target, "Id": pid, "Segments": seg})

    motion = {
        "Version": 3,
        "Meta": {
            "Duration": round(stop_time, 4),
            "Fps": fps,
            "Loop": True,
            "AreBeziersRestricted": True,
            "CurveCount": len(motion_curves),
            "TotalSegmentCount": total_segments,
            "TotalPointCount": total_points,
            "UserDataCount": 0,
            "TotalUserDataSize": 0,
        },
        "Curves": motion_curves,
    }
    return motion


if __name__ == "__main__":
    import sys, UnityPy, os
    UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.51f1"
    bundle = sys.argv[1]
    outdir = sys.argv[2]
    env = UnityPy.load(open(bundle, "rb").read())
    pmap = build_path_map(env)
    os.makedirs(outdir, exist_ok=True)
    for o in env.objects:
        if o.type.name == "AnimationClip":
            tt = o.read_typetree()
            name = tt["m_Name"]
            motion = clip_to_motion3(tt, pmap)
            with open(os.path.join(outdir, f"{name}.motion3.json"), "w", encoding="utf-8") as f:
                json.dump(motion, f, ensure_ascii=False)
            print(f"  {name}: {motion['Meta']['CurveCount']} curves, {motion['Meta']['Duration']}s")
