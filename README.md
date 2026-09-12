<div align="center">

# 🎂 像素蛋糕 PixCake 镜像

**PixCake 各平台安装包镜像 —— 每日自动跟随官方，直发 GitHub Release**

[![Latest](https://img.shields.io/github/v/release/LOVECHEN/pixcake-release?label=最新&color=ff5c8a)](https://github.com/LOVECHEN/pixcake-release/releases/latest)
[![更新](https://img.shields.io/github/release-date/LOVECHEN/pixcake-release?label=更新&color=ff8fab)](https://github.com/LOVECHEN/pixcake-release/releases)
[![同步](https://github.com/LOVECHEN/pixcake-release/actions/workflows/sync.yml/badge.svg)](https://github.com/LOVECHEN/pixcake-release/actions/workflows/sync.yml)

[**⬇️ 最新版**](https://github.com/LOVECHEN/pixcake-release/releases/latest) · [📦 全部版本](https://github.com/LOVECHEN/pixcake-release/releases)

</div>

---

每个大版本一个 [Release](https://github.com/LOVECHEN/pixcake-release/releases)，tag = 版本号（如 `10.0.0`、`9.3.1`）。文件名带各平台真实 build（同一版本 mac 与 win 的 build 号可能不同）：

| 平台 | 文件 |
|------|------|
| 🍎 macOS Apple 芯片 | `PixCake-<版本-build>-mac-arm64.dmg` |
| 🍎 macOS Intel | `PixCake-<版本-build>-mac-intel.dmg` |
| 🪟 Windows | `PixCake-<版本-build>-win.exe` |

- Beta 版标 `Pre-release`；每个 Release 附 `checksums.sha256`。
- **大于 2GB 的文件被切成 `.part-*`**（GitHub 单文件上限 2GiB），合并：

```bash
cat PixCake-9.2.1-21-mac-arm64.dmg.part-* > PixCake-9.2.1-21-mac-arm64.dmg
shasum -a 256 -c checksums.sha256
```

<div align="center"><sub>官方安装包归档 · 数据源 <a href="https://www.pixcakeai.com">pixcakeai.com</a></sub></div>
