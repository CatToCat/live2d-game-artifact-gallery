"""从 gate 握手拿版本，下载各类型 hash 清单 CSV 到 config/hashes/。
gate 是 raw TCP socket，需要 SOCKS5 代理(海外环境可关)。
"""
import os, sys, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C

import azlassets.protobuf as pb
from azlassets.versioncontrol import parse_version_string


def _install_socks():
    if not C.USE_PROXY:
        return
    import socks
    class P(socks.socksocket):
        def __init__(self):
            super().__init__()
            self.set_proxy(socks.SOCKS5, *C.PROXY_SOCKS)
            self.settimeout(25)
    for a in ("disconnect", "send_command", "recv_command", "recv_bytes"):
        setattr(P, a, getattr(pb.ConnectionSocket, a))
    pb.ConnectionSocket = P


def handshake(retries=10):
    for i in range(retries):
        try:
            r = pb.get_version_response(*C.GATE)
            if r:
                return list(r.pb.version)
            print(f"  握手重试 {i+1}: 空响应", flush=True)
        except Exception as e:
            print(f"  握手重试 {i+1}: {e}", flush=True)
    raise SystemExit("gate 握手失败")


def fetch():
    _install_socks()
    proxies = {"http": C.PROXY_HTTP, "https": C.PROXY_HTTP} if C.USE_PROXY else None
    os.makedirs(C.HASHES_DIR, exist_ok=True)
    versions = handshake()
    result = {}
    for v in versions:
        v = v.strip()
        if not v.startswith("$"):
            continue
        try:
            vr = parse_version_string(v)
        except Exception:
            continue
        if vr.version_type.hashname in C.WANT_TYPES:
            label = C.WANT_TYPES[vr.version_type.hashname]
            csv = None
            for attempt in range(5):
                try:
                    resp = requests.get(f"{C.CDN}/hash/{vr.rawstring}", proxies=proxies,
                                        timeout=30, headers={"user-agent": C.USER_AGENT})
                    resp.raise_for_status()
                    csv = resp.text
                    break
                except Exception as e:
                    print(f"    {label} 拉取重试 {attempt+1}: {e}", flush=True)
            if csv is None:
                print(f"    {label} 拉取失败，跳过", flush=True)
                continue
            path = os.path.join(C.HASHES_DIR, f"{label}.csv")
            open(path, "w", encoding="utf-8").write(csv)
            n = csv.count("\n")
            result[label] = n
            print(f"  {label}: {n} 条 -> {path}", flush=True)
    return result


if __name__ == "__main__":
    fetch()
