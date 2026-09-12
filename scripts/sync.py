#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PixCake 官方全平台镜像同步器（GitHub Actions，纯从官网拉）。

两段式并行：
  discover 模式  -> 输出待处理【大版本列表】JSON（供 workflow 动态 matrix）
  sync 模式      -> 只处理 env TARGET_VERSION 指定的那一个大版本（一个 matrix job 一版，避免单 job 逼近 6h 上限）

要点：
- 用 get_software API **每平台各自**的真实包地址（win/mac build 号可能不同，如 10.0.0: mac=713/win=709）；
- 按**大版本号**分组成一个 Release，各平台资产名带各自真实 <版本-build>；
- stable(type=5) 当前版标 latest；仅 beta(type=6) 出现的新版标 prerelease；叠加历史 stable 回填；
- 单文件 ≥2GB 自动 split 分卷 + 整包 sha256；幂等增量，可反复/断点续跑。
"""
import json, os, subprocess, sys, urllib.parse, urllib.request, glob

sys.stdout.reconfigure(line_buffering=True)
PXR  = "像素蛋糕"
API  = "https://api.pixcakeai.com/v1/app/get_software"
CDN  = "https://download.pixcakeai.com/package"
REPO = os.environ["GH_REPO"]
SPLIT_THRESHOLD = 2_000_000_000
PART_SIZE = "1900m"

PLATFORMS = {
    17: ("mac-arm64", "dmg", lambda vb: f"{PXR}-{vb}_arm64.dmg"),
    15: ("mac-intel", "dmg", lambda vb: f"{PXR}-{vb}.dmg"),
    16: ("win",       "exe", lambda vb: f"{PXR}_Setup_{vb}.exe"),
}
BACKFILL = ["8.3.0-515", "8.4.0-499", "8.5.0-550", "8.6.0-302",
            "9.0.0-773", "9.1.0-592", "9.2.1-21"]
BF_MK = {vb.split("-")[0] for vb in BACKFILL}

def run(c): return subprocess.run(c, text=True, capture_output=True)

def enc(u):
    p = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path), p.query, p.fragment))

def api_get(at, ch):
    try:
        with urllib.request.urlopen(f"{API}?app_type={at}&type={ch}", timeout=30) as r:
            d = json.load(r).get("data") or {}
            return d.get("version"), d.get("package_download_url")
    except Exception as e:
        print(f"  ! API {at}/{ch}: {e}"); return None, None

def head_ok(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(enc(u), method="HEAD"), timeout=30) as r:
            return r.status == 200
    except Exception:
        return False

def assets_of(tag):
    r = run(["gh", "release", "view", tag, "-R", REPO, "--json", "assets", "-q", ".assets[].name"])
    return None if r.returncode else set(x for x in r.stdout.split("\n") if x)

def sha256(p): return run(["sha256sum", p]).stdout.split()[0]

def build_targets():
    """-> ({mk: {'plats':{label:(vb,url,ext)}, 'pre':bool, 'latest':bool}}, ordered_mk_list)"""
    T = {}
    def add(vb, url, at, ch):
        if not vb or not url: return
        mk = vb.split("-")[0]
        label, ext, _ = PLATFORMS[at]
        t = T.setdefault(mk, {"stable": False, "beta": False, "plats": {}})
        if ch == 5: t["stable"] = True
        if ch == 6: t["beta"] = True
        t["plats"].setdefault(label, (vb, url, ext))

    stable_mk = None
    for at in (17, 15, 16):
        vb, url = api_get(at, 5); add(vb, url, at, 5)
        if at == 17 and vb: stable_mk = vb.split("-")[0]
    for at in (17, 15, 16):
        vb, url = api_get(at, 6); add(vb, url, at, 6)
    for vb in BACKFILL:
        for at in (17, 15, 16):
            u = f"{CDN}/{vb}/{PLATFORMS[at][2](vb)}"
            if head_ok(u): add(vb, u, at, 0)

    res = {}
    for mk, t in T.items():
        res[mk] = {
            "plats": t["plats"],
            "latest": (mk == stable_mk),
            "pre": t["beta"] and not t["stable"] and mk not in BF_MK and mk != stable_mk,
        }
    order = sorted(res, key=lambda mk: tuple(int(x) for x in mk.split(".")), reverse=True)
    return res, order

def sync_release(mk, plats, pre, latest, wd):
    have = assets_of(mk)
    expect = {label: f"PixCake-{vb}-{label}.{ext}" for label, (vb, url, ext) in plats.items()}
    present = lambda n: have is not None and (n in have or f"{n}.part-aa" in have)
    if have is not None and all(present(n) for n in expect.values()):
        print(f"[{mk}] 已完整，跳过"); return

    if have is None:
        c = ["gh", "release", "create", mk, "-R", REPO, "--title", f"PixCake {mk}",
             "--notes", f"PixCake `{mk}`{'（Beta）' if pre else ''} 官方原包（各平台 build 号可能不同）。\n\n"
                        f"文件 >2GB 会切成 `.part-*`，合并：`cat 文件.part-* > 文件`，再用 `checksums.sha256` 校验。"]
        c += ["--prerelease"] if pre else ["--latest"] if latest else ["--latest=false"]
        run(c); print(f"  建 Release {mk}" + ("（Beta）" if pre else ""))

    run(["gh", "release", "download", mk, "-R", REPO, "-p", "checksums.sha256", "-D", wd, "--clobber"])
    cf = os.path.join(wd, "checksums.sha256"); checks = {}
    if os.path.exists(cf):
        for ln in open(cf, encoding="utf-8"):
            a = ln.split()
            if len(a) == 2: checks[a[1]] = a[0]

    changed = False
    for label, (vb, url, ext) in plats.items():
        name = expect[label]
        if present(name):
            continue
        path = os.path.join(wd, name)
        print(f"  [{mk}] 拉 {name}")
        if run(["curl", "-fL", "--retry", "3", "--retry-delay", "5", "-o", path, enc(url)]).returncode or not os.path.exists(path):
            print(f"  ! 下载失败 {name}"); continue
        checks[name] = sha256(path); changed = True
        if os.path.getsize(path) >= SPLIT_THRESHOLD:
            run(["split", "-b", PART_SIZE, path, f"{path}.part-"])
            parts = sorted(glob.glob(f"{path}.part-*"))
            run(["gh", "release", "upload", mk, "-R", REPO, "--clobber", *parts])
            for p in parts: os.remove(p)
        else:
            run(["gh", "release", "upload", mk, "-R", REPO, "--clobber", path])
        os.remove(path)
        print(f"  [{mk}] ✓ {name}")
    if changed:
        with open(cf, "w", encoding="utf-8") as f:
            for n in sorted(checks): f.write(f"{checks[n]}  {n}\n")
        run(["gh", "release", "upload", mk, "-R", REPO, "--clobber", cf])

def cmd_discover():
    res, order = build_targets()
    payload = json.dumps(order, separators=(",", ":"))
    print(f"versions={payload}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f: f.write(f"versions={payload}\n")

def cmd_sync(mk):
    wd = os.path.abspath("_work"); os.makedirs(wd, exist_ok=True)
    res, _ = build_targets()
    if mk not in res:
        print(f"[{mk}] 当前无可下目标（可能官方已下架）"); return
    t = res[mk]
    sync_release(mk, t["plats"], t["pre"], t["latest"], wd)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "discover":
        cmd_discover()
    elif mode == "sync":
        cmd_sync(os.environ["TARGET_VERSION"])
    else:  # 本地/兜底：串行全跑
        res, order = build_targets()
        print(f"versions={order}")
        for mk in order:
            try: cmd_sync(mk)
            except Exception as e: print(f"  ! {mk}: {e}")
    print("done")

if __name__ == "__main__":
    main()
