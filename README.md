<div align="center">

# 🎂 像素蛋糕 PixCake 全平台镜像

**PixCake / 像素蛋糕 各版本官方安装包 —— 每日自动跟随官方 stable + beta，直发 GitHub Release**

[![Latest](https://img.shields.io/github/v/release/LOVECHEN/pixcake-release?label=最新&color=ff5c8a&logo=apple&logoColor=white)](https://github.com/LOVECHEN/pixcake-release/releases/latest)
[![最近更新](https://img.shields.io/github/release-date/LOVECHEN/pixcake-release?label=最近更新&color=ff8fab)](https://github.com/LOVECHEN/pixcake-release/releases)
[![自动同步](https://github.com/LOVECHEN/pixcake-release/actions/workflows/sync.yml/badge.svg)](https://github.com/LOVECHEN/pixcake-release/actions/workflows/sync.yml)

[**⬇️ 下载最新版**](https://github.com/LOVECHEN/pixcake-release/releases/latest) · [📦 全部版本](https://github.com/LOVECHEN/pixcake-release/releases) · [🔀 分卷合并](#分卷合并) · [❓ 版本说明](#版本说明)

</div>

---

## ⬇️ 下载

每个版本一个 [Release](https://github.com/LOVECHEN/pixcake-release/releases)，tag = 完整版本号 `<版本>-<build>`（如 `9.2.1-21`）。每个 Release 里三平台资产命名固定：

| 平台 | 文件名 |
|------|--------|
| 🍎 **macOS · Apple 芯片** | `PixCake-<版本>-mac-arm64.dmg` |
| 🍎 **macOS · Intel** | `PixCake-<版本>-mac-intel.dmg` |
| 🪟 **Windows · x64** | `PixCake-<版本>-win.exe` |

- **最新正式版**：点 [Releases → Latest](https://github.com/LOVECHEN/pixcake-release/releases/latest)。
- **测试版（Beta）**：标 `Pre-release`，如当前 `9.3.0-249`。
- 每个 Release 附 `checksums.sha256`，下载后可校验完整性。
- 都是**官方原包**，字节与 `download.pixcakeai.com` 官方 CDN 完全一致（未改包、未重签）。

<a id="分卷合并"></a>

## 🔀 分卷合并（大于 2GB 的文件）

GitHub Release **单文件上限 2 GiB**，超过的包被切成 `.part-aa` / `.part-ab` …。下齐同名所有 `.part-*` 后合并：

```bash
# macOS / Linux
cat PixCake-9.2.1-21-mac-arm64.dmg.part-* > PixCake-9.2.1-21-mac-arm64.dmg
shasum -a 256 -c checksums.sha256      # 校验合并结果
```
```bat
:: Windows（按 part-aa、part-ab… 顺序）
copy /b PixCake-9.3.0-249-win.exe.part-aa + PixCake-9.3.0-249-win.exe.part-ab PixCake-9.3.0-249-win.exe
```

> `checksums.sha256` 里存的是**合并后整包**的哈希；小于 2GB、没被切分的文件直接下、直接校验。

<a id="版本说明"></a>

## ❓ 版本说明

- **只收官方原包**：数据源 = 官方 `api.pixcakeai.com` 的 `get_software` 接口（stable=`type=5` / beta=`type=6`）解析出的真包地址 + 官方 CDN `download.pixcakeai.com`。
- **为什么历史版本不一定全**：官方 API 只返回**当前最新**版本；官方 CDN 只**滚动保留最近约一年**的版本，更老的会被清（404）。本仓库把「当下还能从官方 CDN 下到的历史版本」一次性归档进 Release，**下架了也留得住**——这正是镜像的意义。
- **平台缺失**：老版本官方 CDN 已下架的、或早期只发过某平台的，可能只有部分平台文件。
- **自动同步**：每天 04:00 UTC，[workflow](.github/workflows/sync.yml) 在 GitHub runner 上从官方 CDN 拉新版 + 回填历史，发现新 build 自动建 Release。增量幂等，已有的不重复下。

## 📁 版本谱系（节选）

| 版本 | 时间 | 架构壳 | 备注 |
|------|------|--------|------|
| 3.2.6 / 3.4.2 | 2022 | **Electron** | 最早期桌面版（Electron Framework + Squirrel 多进程）|
| 4.0.9 起 | 2022 中 | **Qt5** | 切换到 Qt5 原生壳（QtWebEngine 内嵌 Chromium 加载本地 web 前端）|
| 8.3.0 – 9.2.1 | 2026 | Qt5 | 官方 CDN 现役、可直下 |
| 9.3.0 | 2026 | Qt5 | 当前 Beta |

> PixCake 桌面端 **2022 年中从 Electron 迁到 Qt5**（3.4.2=Electron，4.0.9=Qt5），此后一路 Qt5 至今。

---

<div align="center">
<sub>仅做官方安装包版本归档镜像 · 数据源：<a href="https://www.pixcakeai.com">pixcakeai.com</a></sub>
</div>
