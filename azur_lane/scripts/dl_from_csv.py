"""按 config/hashes/<TYPE>.csv 下载 bundle 到 cache/AssetBundles/。
requests 多线程，断点续传(已存在且大小一致则跳过)。
用法: python dl_from_csv.py [PAINTING|L2D|PIC ...]  不传则全下。
      python dl_from_csv.py --verify L2D    # 额外校验 md5(慢，但能发现同尺寸改动)
"""
import os, sys, hashlib, requests, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C

proxies = {"http": C.PROXY_HTTP, "https": C.PROXY_HTTP} if C.USE_PROXY else None
sess = requests.Session()
if proxies:
    sess.proxies = proxies
sess.headers["user-agent"] = C.USER_AGENT


def rows(csv_path):
    out = []
    for line in open(csv_path, encoding="utf-8"):
        p = line.strip().split(",")
        if len(p) >= 3:
            try:
                out.append((p[0], int(p[1]), p[2]))
            except ValueError:
                pass
    return out


def file_md5(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def dl(row, verify=False):
    path, size, md5 = row
    dst = os.path.join(C.CACHE_DIR, path.replace("/", os.sep))
    if os.path.exists(dst) and os.path.getsize(dst) == size:
        # 默认只比大小(快)。verify=True 时再比 md5，
        # 以捕获"内容变了但字节数没变"的改动 —— 这种情况下光看大小会漏更新。
        if not verify or file_md5(dst) == md5:
            return "skip"
    for _ in range(3):
        try:
            r = sess.get(f"{C.CDN}/resource/{md5}", timeout=90)
            r.raise_for_status()
            if len(r.content) != size:
                return "badsize"
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(r.content)
            return "ok"
        except Exception:
            continue
    return "err"


def download(types=None, verify=False, only=None):
    """only: 可选的 path 集合，只处理其中的条目(增量更新用)。"""
    types = types or list(C.WANT_TYPES.values())
    for t in types:
        csv_path = os.path.join(C.HASHES_DIR, f"{t}.csv")
        if not os.path.exists(csv_path):
            print(f"  跳过 {t}: 无清单 {csv_path}")
            continue
        rs = rows(csv_path)
        if only is not None:
            rs = [r for r in rs if r[0] in only]
        if not rs:
            print(f"{t}: 无需下载")
            continue
        print(f"{t}: {len(rs)} 文件" + ("  [md5 校验]" if verify else ""), flush=True)
        ok = skip = err = 0
        with cf.ThreadPoolExecutor(max_workers=24) as ex:
            for i, s in enumerate(ex.map(lambda r: dl(r, verify), rs), 1):
                if s == "ok": ok += 1
                elif s == "skip": skip += 1
                else: err += 1
                if i % 200 == 0 or i == len(rs):
                    print(f"  {i}/{len(rs)} ok={ok} skip={skip} err={err}", flush=True)
        print(f"{t} 完成: ok={ok} skip={skip} err={err}", flush=True)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    download(args or None, verify="--verify" in sys.argv)
