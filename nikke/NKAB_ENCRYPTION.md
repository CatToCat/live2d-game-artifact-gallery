# NIKKE NKAB 加密调研笔记

本文记录对 NIKKE 本地客户端缓存中 **NKAB 加密包**的调研结论：为什么本地
`extract_local.py` 只能拆出 skillcut / 剧情演出，而拆不出常规立绘（fb）/ 半身（cover）/
瞄准（aim），以及 NKAB 加密的原理与破解现状。

> **一句话结论**：常规立绘 fb/cover/aim 被 **NKAB v4 加密**保护，而目前**没有公开可用的
> v4 解密器**（公开实现只到 v3，已过时）。因此本地拆不出这三种姿态，只能走 Nikke-db CDN
> 消费其已解密的成品。

---

## 一、问题现象

- 本地缓存（`nikke/raw/naps/`，256 桶、约 26GB、33339 个文件）跑 `extract_local.py`，
  能拆出 **skillcut（技能演出）/ eventscene（活动）/ liberation·Glass·mvg（剧情过场）**，
  但**几乎拆不出 fb / cover / aim**。
- 表现为大量角色目录里只有 `skillcut/` 子目录（例如 `c515` 最初只有技能演出）。
- 全盘扫描 25266 个明文包，找到的 `.skel` 分布：

  | 类型 | 数量 |
  |------|------|
  | skillcut | 434 |
  | eventscene | 82 |
  | other（liberation / Glass / mvg 等剧情） | 70 |
  | **fb（c###）** | **仅 2 个**（c821_01，孤例） |
  | **cover** | **0** |
  | **aim** | **0** |

## 二、根因

缓存文件头分两类：

| 文件头 | 类型 | 占比 | 本地可解 |
|--------|------|------|----------|
| `UnityFS` | 明文 Unity 包 | 约 76%（25266 个） | ✅ UnityPy 直接解 |
| `NKAB`   | NIKKE 私有加密包 | 约 24%（**8073 个**） | ❌ `extract_local.py` 明确跳过 |

**常规立绘 fb/cover/aim 就在那 8073 个 NKAB 加密包里**（明文包里几乎没有），
而 `extract_local.py` 遇到 `NKAB` 头直接跳过，所以本地拆不出。

这也解释了整个数据链路：
```
游戏客户端缓存 naps/
  ├─ UnityFS 明文包 (76%) → UnityPy 直接解 → skillcut / eventscene / 剧情
  └─ NKAB 加密包   (24%) → 需先解密 → UnityFS → 才能提取 → fb / cover / aim
```

---

## 三、NKAB 加密原理

### 3.1 v3（公开、已过时）

社区大佬 **Razmoth** 逆向出了 v3 算法（其原始仓库 `Razmoth/Nikke` 现已因法律原因被
GitHub 下架，访问返回 HTTP 451）。基于该算法的开源实现是
[`iceynano/Nikke-NKAB-Decrypter`](https://github.com/iceynano/Nikke-NKAB-Decrypter)（C#，仅解密）。

**v3 `DecryptV3` 流程**：

1. **头部反混淆**：文件**末尾 2 字节**存一个混淆值 `obfuscateValue`；头部一串 int16
   字段（headerSize / keyVersion / keyIndex / encryptMode / encryptFlags / blockCount）
   都被它偏移过，反解方式为 `真实值 = (读到的值 + obfuscateValue) & 0xFFFF`。
2. **密钥派生**：内置 4 套硬编码密钥表（V0/V2/V3/V4，各 5 把 256-bit key，从游戏二进制
   dump/hook 得到）。取 `keyA = 密钥表[keyVersion][keyIndex]`，与文件内的 `keyB`（32 字节）
   拼接后做 **SHA256**，得到最终 AES key。
3. **AES 分块解密**：AES（ECB 或 CBC，由 encryptMode 决定），按 16 字节分块；用
   `encryptFlags` 的位掩码（`0x8000 >> (blockIndex % 16)`）判断每块是否加密（**非全块加密**）。
   还支持只加密头部/尾部若干块（`blockCount` 高/低字节）以降低游戏运行时开销。

> 破解的真正门槛是那几张 **keyA 密钥表**；算法本体是标准 AES + SHA256。

### 3.2 v4（本项目缓存的实际版本，**无公开解密器**）

对本项目缓存里 **8073 个 NKAB 包全量探测，version 字段全部 = 4**。用 v3 的头部逻辑去解，
得到的 keyVersion/keyIndex 全是垃圾值（如 37013、49406，远超合理范围 0–4）→
**证明 v4 的头部布局与 v3 不同**，v3 解密器对 v4 直接失效
（`iceynano` 的 `DecryptV3` 里 `if header.Version != 3 return`）。

**逆向出的 v4 头部字节布局**（对 200 个包做逐字节稳定性统计得出）：

```
偏移        内容                         稳定性
0x00-0x07   magic "NKAB" + version=4     固定
0x08-0x13   12 字节                       每包不同（IV / 加密头）
0x14-0x33   32 字节                       ★ 跨所有包完全相同（v3 没有的新结构）
0x34+       数据体                         每包不同
```

其中 `0x14` 起的 **32 字节固定常量**（`2f 73 5d 32 21 5f 16 53 c8 f5 5f bf 31 21 ff d5
7a 3d 4f 83 ef 7b 73 db cd 2a 45 70 d6 77 6c 4b`）是 v3 完全没有的新特征，
推测为某种固定加密头 / 密钥标识，是 v4 的关键差异。

**现状**：
- GitHub 公开实现只有 v3（iceynano，2024 年更新）。
- Razmoth 原始逆向仓库已被下架（451）。
- 代码搜索找不到任何 `DecryptV4` / v4 密钥表的公开实现。

**因此 v4 破解原理尚未掌握**。缺的不是算法框架（AES+SHA256 是通用的），而是两个私有要素：
1. v4 头部字段的确切语义（那 12 字节和 32 字节常量各代表什么）；
2. v4 的 keyA 密钥表（需从**当前**游戏客户端 dump/hook，即 Razmoth/0xDC00 当年做的事）。

自行逆向 v4 需要 hook 运行中的游戏进程 dump 内存密钥、或反编译 `libil2cpp.so`——
属于对游戏客户端的逆向工程，工作量大且有法律风险。

---

## 四、结论与建议

| 方案 | 可行性 | 说明 |
|------|--------|------|
| 本地拆 fb/cover/aim（NKAB v4 解密） | ❌ 暂不可行 | 无公开 v4 解密器；需自行逆向游戏客户端，成本高、有法律风险 |
| **走 Nikke-db CDN 消费成品**（现方案） | ✅ 推荐 | Nikke-db 私下持有 v4 解密能力并把成品传 CDN，直接下载即可 |

**当前采用方案**：`fetch_nikke.py` 从 Nikke-db CDN 拉取已解密的 fb/cover/aim。

由于 Nikke-db 的索引 `l2d.json` 收录不全（如 c515 等未收录，但 CDN 上资源实际存在），
已用 `--scan-existing --only-missing` 模式绕过索引、按已有目录逐个探测补抓：

```bash
cd nikke/scripts
export NIKKE_PROXY=<代理>          # 如需代理
python fetch_nikke.py --scan-existing --only-missing
python gen_nikke_manifest.py
```

该修复已把 181 个「只有 skillcut」的角色补齐了 fb/cover/aim（c103/c105 天生无 cover/aim，
CDN 上确认不存在，非遗漏）。

**后续若要本地自给自足**，前置条件是社区/自己公开出 **NKAB v4 解密器**（含 v4 密钥表）。
在此之前，`extract_local.py` 只能拆明文包，NKAB 分支维持跳过。

---

## 五、参考

- iceynano/Nikke-NKAB-Decrypter（v3，C#）：https://github.com/iceynano/Nikke-NKAB-Decrypter
- Razmoth/Nikke（原始 v3 逆向，已被 GitHub 下架 / 451）
- Nikke-db（已解包资源 CDN）：https://github.com/Nikke-db/Nikke-db.github.io

## 六、版权说明

仅用于个人学习研究记录。相关加密算法与密钥的版权/权利归属游戏方（SHIFT UP / Level Infinite），
本文不提供任何密钥或可用于绕过版权保护的完整实现。
