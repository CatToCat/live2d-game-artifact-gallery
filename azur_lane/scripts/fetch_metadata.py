"""拉取社区皮肤元数据(ship_skin_template.json) -> config/cfg_json/。

为什么不自己解官方文件：
  官方 CDN 上确有 `sharecfgdata/ship_skin_template`(见 AZL.csv)，但它是蛮啾自定义
  二进制容器 —— 无 UnityFS 头、非 zlib/gzip、非单字节异或，连字段名都被编码
  (搜不到 'painting'/'shop_id' 明文)。自行解析需逆向 libil2cpp，成本过高，
  故复用社区已 dump 的成果。

设计要点：
  - 多源按序回落(config.SKIN_TPL_SOURCES)，任一通过校验即停
  - 完整性校验：带 painting 字段的条目数 >= SKIN_TPL_MIN_ENTRIES
    (上游 sharecfg/ 下有个 148KB 残缺版，painting 解析结果为 0，必须挡掉)
  - 原子写入 + 失败保留旧文件：所有源都失败时不动现有文件，只告警
  - 支持 lua 源(AzurLaneTools 的原始脚本)，只提取 gen_manifest 需要的标量字段

用法:
  python fetch_metadata.py            # 需要时更新(默认)
  python fetch_metadata.py --force    # 强制重新拉取
"""
import os, sys, json, re, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import requests

DST = os.path.join(C.CFG_JSON_DIR, C.SKIN_TPL_NAME)

# gen_manifest.py 实际用到的字段(其余如 desc/smoke/bound_bone 一律丢弃)
LUA_WANT_STR = ("name", "painting", "prefab")
LUA_WANT_INT = ("id", "ship_group", "group_index", "shop_id", "skin_type")

_ENTRY_RE = re.compile(r"ship_skin_template\[(\d+)\]\s*=\s*\{", re.S)


def _proxies():
    return {"http": C.PROXY_HTTP, "https": C.PROXY_HTTP} if C.USE_PROXY else None


def parse_lua(text):
    """从 Lua 脚本提取皮肤表。只取顶层标量字段，忽略嵌套表(smoke/bound_bone 等)。

    做法：定位每个 `ship_skin_template[id] = {` 起点，在下一个起点之前的片段里
    用正则抓所需字段。因为嵌套表里不会出现 `painting = "..."` 这类键名，
    直接正则足够且不必写完整 Lua parser。
    """
    starts = [(m.start(), int(m.group(1))) for m in _ENTRY_RE.finditer(text)]
    out = {}
    for i, (pos, sid) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        seg = text[pos:end]
        e = {"id": sid}
        for k in LUA_WANT_STR:
            m = re.search(rf'\b{k}\s*=\s*"((?:[^"\\]|\\.)*)"', seg)
            if m:
                e[k] = m.group(1)
        for k in LUA_WANT_INT:
            m = re.search(rf'\b{k}\s*=\s*(-?\d+)', seg)
            if m:
                e[k] = int(m.group(1))
        out[str(sid)] = e
    return out


def count_valid(skins):
    """带 painting 且有 id 的条目数 —— 用作完整性指标。"""
    n = 0
    for k, v in skins.items():
        if k == "all" or not isinstance(v, dict):
            continue
        if v.get("painting") and v.get("id") is not None:
            n += 1
    return n


def _write_atomic(path, payload):
    """先写临时文件再替换，避免中途失败留下半截 JSON。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def current_count():
    if not os.path.exists(DST):
        return 0
    try:
        return count_valid(json.load(open(DST, encoding="utf-8")))
    except Exception:
        return 0


def fetch(force=False):
    """返回 (是否更新, 生效条目数)。全部源失败时不改动现有文件。"""
    have = current_count()
    print(f"  当前本地元数据: {have} 条" + ("" if have else " (无/损坏)"))

    errors = []
    for label, kind, url in C.SKIN_TPL_SOURCES:
        try:
            r = requests.get(url, proxies=_proxies(), timeout=120,
                             headers={"user-agent": C.USER_AGENT})
            r.raise_for_status()
            if kind == "lua":
                r.encoding = r.encoding or "utf-8"
                skins = parse_lua(r.text)
            else:
                skins = r.json()
            n = count_valid(skins)
            if n < C.SKIN_TPL_MIN_ENTRIES:
                # 残缺文件(如上游 sharecfg/ 那份 148KB 版本)在此被拦下
                errors.append(f"{label}: 仅 {n} 条有效(<{C.SKIN_TPL_MIN_ENTRIES})，疑似残缺，跳过")
                print(f"  ✗ {errors[-1]}", flush=True)
                continue
            if not force and n < have:
                errors.append(f"{label}: {n} 条 < 本地 {have} 条，疑似回退，跳过")
                print(f"  ✗ {errors[-1]}", flush=True)
                continue
            _write_atomic(DST, skins)
            print(f"  ✓ {label}: {n} 条 -> {DST}", flush=True)
            return True, n
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__} {e}")
            print(f"  ✗ {label} 失败: {type(e).__name__} {e}", flush=True)

    if have:
        print("  ! 所有元数据源均不可用，保留现有文件继续(新皮肤可能未分组)", flush=True)
        return False, have
    print("  !! 所有元数据源均不可用且本地无可用文件；", flush=True)
    print("     新皮肤将缺少名称/分组/发布次序(skin id = -1)。", flush=True)
    return False, 0


if __name__ == "__main__":
    ok, n = fetch(force="--force" in sys.argv)
    print(f"{'已更新' if ok else '未更新'}，生效 {n} 条")
