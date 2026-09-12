#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PixCake 官方全平台镜像同步器（跑在 GitHub Actions runner 上）。

做的事：
  1. 调官方 get_software API 拿 stable(type=5) + beta(type=6) 三平台(arm64/intel/win)当前版本；
  2. 叠加一份「历史 stable 版本-build」回填清单（官方 CDN 仍保留、实测可下的老版本）；
  3. 对每个 <版本-build>：在 runner 上从官方 CDN 直接下载缺失的平台包；
     - 单文件 ≥2GB 的自动 split 分卷（GitHub Release 单文件 2GiB 硬上限）；
     - 计算整包 sha256，写进该 Release 的 checksums.sha256；
     - 用 gh 建/更新对应 tag 的 Release 并上传资产。
  幂等增量：已存在的资产跳过，可反复跑 / 断点续跑。
"""
import json, os, subprocess, sys, urllib.parse, urllib.request, shutil, glob

PX_ENC = "%E5%83%8F%E7%B4%A0%E8%9B%8B%E7%B3%95"          # 像素蛋糕 (URL-encoded)
API    = "https://api.pixcakeai.com/v1/app/get_software"
CDN    = "https://download.pixcakeai.com/package"
REPO   = os.environ["GH_REPO"]
MAXV   = int(os.environ.get("MAX_VERSIONS", "100"))
SPLIT_THRESHOLD = 2_000_000_000                            # ≥ ~1.86GiB 就分卷，稳在 2GiB 限制下
PART_SIZE = "1900m"

# app_type -> (平台标签, CDN 文件名 builder, 扩展名)
PLATFORMS = {
    17: ("mac-arm64", lambda vb: f"{PX_ENC}-{vb}_arm64.dmg", "dmg"),
    15: ("mac-intel", lambda vb: f"{PX_ENC}-{vb}.dmg",       "dmg"),
    16: ("win",       lambda vb: f"{PX_ENC}_Setup_{vb}.exe", "exe"),
}

# 历史 stable 版本-build 回填清单（2026-07 实测官方 CDN 仍返回 200；CDN 保留非线性，逐个 HEAD 校验后才下）
BACKFILL = [
    "8.3.0-515", "8.4.0-499", "8.5.0-550", "8.6.0-302",
    "9.0.0-773", "9.1.0-592", "9.2.1-21",
]

def run(cmd, **kw):
    return subprocess.run(cmd, text=True, capture_output=True, **kw)

def api_latest(app_type, channel):
    url = f"{API}?app_type={app_type}&type={channel}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.load(r).get("data") or {}
            return d.get("version") or None
    except Exception as e:
        print(f"  ! API {app_type}/{channel} 失败: {e}")
        return None

def head_ok(url):
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception:
        return False

def cdn_url(vb, app_type):
    _, fn_builder, _ = PLATFORMS[app_type]
    return f"{CDN}/{vb}/{fn_builder(vb)}"

def asset_name(vb, app_type):
    label, _, ext = PLATFORMS[app_type]
    return f"PixCake-{vb}-{label}.{ext}"

def release_assets(tag):
    r = run(["gh", "release", "view", tag, "-R", REPO, "--json", "assets", "-q", ".assets[].name"])
    if r.returncode != 0:
        return None                      # release 不存在
    return set(x for x in r.stdout.split("\n") if x)

def ensure_release(tag, title, notes, prerelease, latest):
    if release_assets(tag) is not None:
        return
    cmd = ["gh", "release", "create", tag, "-R", REPO, "--title", title, "--notes", notes]
    cmd += ["--prerelease"] if prerelease else ["--latest"] if latest else ["--latest=false"]
    r = run(cmd)
    print(("  建 Release " + tag) if r.returncode == 0 else f"  ! 建 Release 失败 {tag}: {r.stderr.strip()}")

def upload(tag, files):
    r = run(["gh", "release", "upload", tag, "-R", REPO, "--clobber", *files])
    if r.returncode != 0:
        print(f"  ! 上传失败 {files}: {r.stderr.strip()}")
        return False
    return True

def sha256(path):
    return run(["sha256sum", path]).stdout.split()[0]

def load_checksums(tag, workdir):
    """取回该 Release 已有 checksums.sha256 -> {文件名: hash}"""
    dst = os.path.join(workdir, "checksums.sha256")
    r = run(["gh", "release", "download", tag, "-R", REPO, "-p", "checksums.sha256", "-D", workdir, "--clobber"])
    m = {}
    if r.returncode == 0 and os.path.exists(dst):
        for line in open(dst, encoding="utf-8"):
            parts = line.split()
            if len(parts) == 2:
                m[parts[1]] = parts[0]
    return m

def save_checksums(tag, workdir, m):
    dst = os.path.join(workdir, "checksums.sha256")
    with open(dst, "w", encoding="utf-8") as f:
        for name in sorted(m):
            f.write(f"{m[name]}  {name}\n")
    upload(tag, [dst])

def process_version(vb, prerelease, latest, seed_dir, workdir):
    # 1) 收集该版本可用平台（HEAD 校验 CDN；win 老版可能不在则跳过）
    targets = []
    for at in (17, 15, 16):
        url = cdn_url(vb, at)
        if head_ok(url):
            targets.append((at, url, asset_name(vb, at)))
    # 本地种子（CDN 已下架的老版：只有 mac dmg），补进来
    seeds = []
    if seed_dir:
        for at in (17,):  # 老版是通用包，按 mac-arm64 名归档
            for cand in glob.glob(os.path.join(seed_dir, f"*-{vb}.dmg")) + glob.glob(os.path.join(seed_dir, f"*-{vb}_arm64*.dmg")):
                seeds.append((asset_name(vb, at).replace("mac-arm64", "mac"), cand))
    if not targets and not seeds:
        return False

    existing = release_assets(vb)
    have = existing if existing is not None else set()
    # 已完整（每个目标名或其首分卷都在）→ 跳过
    def present(name):
        return name in have or f"{name}.part-aa" in have
    if targets and all(present(n) for _, _, n in targets) and all(present(n) for n, _ in seeds):
        print(f"[{vb}] 已完整，跳过")
        return False

    title = f"PixCake {vb.split('-')[0]}" + ("（Beta 测试版）" if prerelease else "（正式版）")
    ensure_release(vb, title, release_notes(vb, prerelease), prerelease, latest)

    checks = load_checksums(vb, workdir)
    changed = False

    def handle(name, local_path=None, url=None):
        nonlocal changed
        if present(name):
            print(f"  [{vb}] {name} 已存在，跳过")
            return
        path = os.path.join(workdir, name)
        if local_path:
            shutil.copy(local_path, path)
        else:
            print(f"  [{vb}] 下载 {name} <- {urllib.parse.unquote(url)}")
            r = run(["curl", "-fL", "--retry", "3", "--retry-delay", "5", "-o", path, url])
            if r.returncode != 0 or not os.path.exists(path):
                print(f"  ! 下载失败 {name}: {r.stderr.strip()[:200]}")
                return
        size = os.path.getsize(path)
        checks[name] = sha256(path)                       # 整包 hash（合并后校验用）
        changed = True
        if size >= SPLIT_THRESHOLD:
            print(f"  [{vb}] {name} = {size} bytes ≥ 阈值，分卷")
            run(["split", "-b", PART_SIZE, path, f"{path}.part-"])
            parts = sorted(glob.glob(f"{path}.part-*"))
            upload(vb, parts)
            for p in parts: os.remove(p)
        else:
            upload(vb, [path])
        os.remove(path)

    for at, url, name in targets:
        handle(name, url=url)
    for name, local in seeds:
        handle(name, local_path=local)

    if changed:
        save_checksums(vb, workdir, checks)
    return True

def release_notes(vb, prerelease):
    ver = vb.split("-")[0]
    chan = "Beta 测试版" if prerelease else "正式版"
    return f"""## PixCake / 像素蛋糕 {ver}  ·  {chan}

版本号 `{vb}`。官方原包，字节与 `download.pixcakeai.com` 一致。

### 平台资产
| 平台 | 文件 |
|------|------|
| 🍎 macOS Apple 芯片 | `PixCake-{vb}-mac-arm64.dmg` |
| 🍎 macOS Intel | `PixCake-{vb}-mac-intel.dmg` |
| 🪟 Windows x64 | `PixCake-{vb}-win.exe` |

> 部分版本仅有某些平台（老版本官方 CDN 已下架的、或本仓库回填的历史版本可能不全）。

### 分卷合并（>2GB 的文件）
GitHub Release 单文件上限 2GiB，超限文件被切成 `.part-aa` / `.part-ab` …。合并：
```bash
cat PixCake-{vb}-mac-arm64.dmg.part-* > PixCake-{vb}-mac-arm64.dmg   # macOS/Linux
copy /b PixCake-{vb}-win.exe.part-aa + PixCake-{vb}-win.exe.part-ab PixCake-{vb}-win.exe   :: Windows
```
合并后用 `checksums.sha256` 校验：`shasum -a 256 -c checksums.sha256`。
"""

def main():
    workdir = os.path.abspath("_work"); os.makedirs(workdir, exist_ok=True)
    seed_dir = os.environ.get("SEED_DIR", "")

    # 发现当前 stable / beta
    stable_vb = api_latest(17, 5)                          # arm64 stable = 主锚点
    beta_arm  = api_latest(17, 6)
    print(f"当前 stable={stable_vb}  beta={beta_arm}")

    # 组装处理顺序：stable 当前 → beta → 回填历史（新到旧）
    order = []
    def add(vb, pre, latest):
        if vb and vb not in [x[0] for x in order]:
            order.append((vb, pre, latest))
    add(stable_vb, False, True)
    if beta_arm and beta_arm != stable_vb:
        add(beta_arm, True, False)
    for vb in BACKFILL:
        add(vb, False, False)

    seeded = 0
    for vb, pre, latest in order[:MAXV]:
        try:
            # 老版(3.x/4.x)种子只对本地存在的用；其它用 CDN
            sd = seed_dir if seed_dir and glob.glob(os.path.join(seed_dir, f"*-{vb}*.dmg")) else ""
            process_version(vb, pre, latest, sd, workdir)
        except Exception as e:
            print(f"  ! 处理 {vb} 异常: {e}")
        seeded += 1
    print(f"完成，处理 {seeded} 个版本。")

if __name__ == "__main__":
    main()
