"""立绘还原 worker：串行处理一个文件列表，跳过坏文件，记录进度。被 build.py 调用。"""
import os, sys, contextlib, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION = C.UNITY_FALLBACK_VERSION
from rebuild_painting import rebuild

DONE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".paint_done.txt")

files = [x for x in open(sys.argv[1]).read().split("\n") if x.strip()]
fout = open(DONE, "a")
for f in files:
    name = os.path.basename(f)[:-4]  # 去掉 _tex
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            rebuild(f, os.path.join(C.PAINTINGS_DIR, name + ".png"))
        fout.write(f + "\n")
        fout.flush()
    except BaseException:
        pass
