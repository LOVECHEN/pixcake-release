#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PixCake 官方全平台镜像同步器（跑在 GitHub Actions runner，纯从官网拉）。

- 调 get_software API 拿 stable(type=5)+beta(type=6) 三平台当前版本；
- 叠加历史 stable 回填清单（官方 CDN 仍可下的老版本）；
- 每个 <版本-build> 下缺失平台包 -> ≥2GB 自动分卷 -> 建/传 Release。
幂等增量，可反复/断点续跑。
"""
import json, os, subprocess, urllib.parse, urllib.request, glob

PX  = "%E5%83%8F%E7%B4%A0%E8%9B%8B%E7%B3%95"      # 像素蛋糕
API = "https://api.pixcakeai.com/v1/app/get_software"
CDN = "https://download.pixcakeai.com/package"
REPO = os.environ["GH_REPO"]
MAXV = int(os.environ.get("MAX_VERSIONS", "100"))
SPLIT_THRESHOLD = 2_000_000_000
PART_SIZE = "1900m"

# app_type -> (标签, CDN 文件名, 扩展名)
PLATFORMS = {
    17: ("mac-arm64", lambda vb: f"{PX}-{vb}_arm64.dmg", "dmg"),
    15: ("mac-intel", lambda vb: f"{PX}-{vb}.dmg",       "dmg"),
    16: ("win",       lambda vb: f"{PX}_Setup_{vb}.exe", "exe"),
}
BACKFILL = ["8.3.0-515", "8.4.0-499", "8.5.0-550", "8.6.0-302",
            "9.0.0-773", "9.1.0-592", "9.2.1-21"]

def run(cmd): return subprocess.run(cmd, text=True, capture_output=True)

def api_latest(at, ch):
    try:
        with urllib.request.urlopen(f"{API}?app_type={at}&type={ch}", timeout=30) as r:
            return (json.load(r).get("data") or {}).get("version") or None
    except Exception as e:
        print(f"  ! API {at}/{ch}: {e}"); return None

def head_ok(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as r:
            return r.status == 200
    except Exception:
        return False

def assets_of(tag):
    r = run(["gh", "release", "view", tag, "-R", REPO, "--json", "assets", "-q", ".assets[].name"])
    return None if r.returncode else set(x for x in r.stdout.split("\n") if x)

def notes(vb, pre):
    return (f"PixCake `{vb}`{'（Beta）' if pre else ''} 官方原包。\n\n"
            f"文件 >2GB 会切成 `.part-*`，合并：`cat 文件.part-* > 文件`，再用 `checksums.sha256` 校验。")

def sha256(p): return run(["sha256sum", p]).stdout.split()[0]

def sync_version(vb, pre, latest, wd):
    targets = [(at, cdn, f"PixCake-{vb}-{PLATFORMS[at][0]}.{PLATFORMS[at][2]}")
               for at in (17, 15, 16)
               for cdn in [f"{CDN}/{vb}/{PLATFORMS[at][1](vb)}"] if head_ok(cdn)]
    if not targets:
        return
    have = assets_of(vb) or set()
    present = lambda n: n in have or f"{n}.part-aa" in have
    if assets_of(vb) is not None and all(present(n) for *_, n in targets):
        print(f"[{vb}] 已完整，跳过"); return

    if assets_of(vb) is None:
        c = ["gh", "release", "create", vb, "-R", REPO, "--title", f"PixCake {vb}", "--notes", notes(vb, pre)]
        c += ["--prerelease"] if pre else ["--latest"] if latest else ["--latest=false"]
        run(c); print(f"  建 Release {vb}")

    # 取回已有 checksums
    run(["gh", "release", "download", vb, "-R", REPO, "-p", "checksums.sha256", "-D", wd, "--clobber"])
    cf = os.path.join(wd, "checksums.sha256"); checks = {}
    if os.path.exists(cf):
        for ln in open(cf, encoding="utf-8"):
            a = ln.split()
            if len(a) == 2: checks[a[1]] = a[0]

    changed = False
    for at, url, name in targets:
        if present(name):
            continue
        path = os.path.join(wd, name)
        print(f"  [{vb}] 拉 {name}")
        if run(["curl", "-fL", "--retry", "3", "--retry-delay", "5", "-o", path, url]).returncode or not os.path.exists(path):
            print(f"  ! 下载失败 {name}"); continue
        checks[name] = sha256(path); changed = True
        if os.path.getsize(path) >= SPLIT_THRESHOLD:
            run(["split", "-b", PART_SIZE, path, f"{path}.part-"])
            parts = sorted(glob.glob(f"{path}.part-*"))
            run(["gh", "release", "upload", vb, "-R", REPO, "--clobber", *parts])
            for p in parts: os.remove(p)
        else:
            run(["gh", "release", "upload", vb, "-R", REPO, "--clobber", path])
        os.remove(path)
    if changed:
        with open(cf, "w", encoding="utf-8") as f:
            for n in sorted(checks): f.write(f"{checks[n]}  {n}\n")
        run(["gh", "release", "upload", vb, "-R", REPO, "--clobber", cf])

def main():
    wd = os.path.abspath("_work"); os.makedirs(wd, exist_ok=True)
    stable = api_latest(17, 5); beta = api_latest(17, 6)
    print(f"stable={stable} beta={beta}")
    order, seen = [], set()
    def add(vb, pre, latest):
        if vb and vb not in seen: seen.add(vb); order.append((vb, pre, latest))
    add(stable, False, True)
    if beta and beta != stable: add(beta, True, False)
    for vb in BACKFILL: add(vb, False, False)
    for vb, pre, latest in order[:MAXV]:
        try: sync_version(vb, pre, latest, wd)
        except Exception as e: print(f"  ! {vb}: {e}")
    print("done")

if __name__ == "__main__":
    main()
