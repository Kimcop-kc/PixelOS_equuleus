# Vendor Blobs — 提取说明

本目录**不包含**任何 vendor 二进制 blob（法律与合规原因，也避免仓库过大）。
只保留提取清单和校验方法，任何人都能从官方 MIUI 包自行生成 vendor 树。

## 需要的 MIUI 包

- 版本：`V12.5.2.0.QECCNXM`（Android 10，国行/国际版均可）
- 国内线刷包：`equuleus_images_V12.5.2.0.QECCNXM_20211118.0000.00_10.0_cn_*.tgz`
- 卡刷包：`xiaomi.eu_multi_MI8Pro_V12.5.2.0.QECCNXM_v12-10.zip`（含 firmware-update）

## 提取步骤

### 从线刷包（tgz）

```bash
# 解压后得到 images/ 目录
tar -xzf equuleus_images_V12.5.2.0.QECCNXM_*.tgz

# 用设备树自带提取脚本
cd device/xiaomi/equuleus
./extract-files.py /path/to/images/
```

### 从卡刷包（zip）

```bash
# 用审计包里的完整提取脚本
scripts/extract_vendor_full.sh <rom.zip>
```

详细步骤见 `docs/BLOB_EXTRACTION.md` 和 `docs/BLOB_SOURCES.md`。

## 清单

- `equuleus-proprietary-files.txt` — 设备专属 blob 清单
- `sdm845-common-proprietary-files.txt` — 通用 sdm845 blob 清单

## 校验

提取完成后运行：

```bash
scripts/verify_blobs.py
scripts/blob_audit.py
```

这两个脚本会校验 blob 的 SHA256、检查缺失项，并生成审计报告。

## 重要说明

- **不要**从第三方 ROM 提取 blob（来源不可信，可能混入恶意代码）
- **不要**从他人上传的 vendor 树复制 blob（无法验证完整性）
- 优先从官方 MIUI 包提取，`blob_sources.json` 记录了每个 blob 的来源与哈希
