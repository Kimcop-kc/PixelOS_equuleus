# PixelOS 15 — Xiaomi Mi 8 Pro (equuleus) Port

PixelOS Android 15（`fifteen`，对齐 LineageOS 22.2）移植到小米 8 屏幕指纹版
（代号 `equuleus`，即 Mi 8 Pro / Mi 8 UD）的完整设备树、补丁与构建脚本。

## 状态

| 项 | 状态 |
|---|---|
| ROM 编译 | ✅ 成功（真实执行） |
| 设备启动 | ✅ 已进入系统（`sys.boot_completed=1`） |
| 启动循环 | ✅ 已修复（vendor 缺 Adreno EGL/Keymaster/Gatekeeper + system_server 空指针） |
| 触摸点击 | ✅ 已修复（fts.idc 标定） |
| 默认相机 | ✅ GCam（Aperture 已移除） |
| IR 人脸解锁 | ⚠️ 未上机验证 |
| Root（Magisk） | ⚠️ 待用可靠方式安装 |

## 目录结构

```
PixelOS_equuleus/
├── manifest/                     # repo local manifest（pin 所有上游 SHA）
│   └── equuleus.xml
├── device/xiaomi/
│   ├── equuleus/                 # 设备树（含改动）
│   └── sdm845-common/            # 通用设备树（含改动，gcam 只留模块定义）
├── patches/                      # 8 个构建补丁
├── scripts/                      # 构建/提取/审计脚本
├── docs/                         # 全部文档与审计报告
└── vendor-blobs/                 # blob 提取清单（不含 blob 本体）
```

## 构建

```bash
# 1. 初始化 PixelOS fifteen
repo init -u https://github.com/PixelOS-AOSP/manifest -b fifteen

# 2. 放入 local manifest
cp manifest/equuleus.xml .repo/local_manifests/

# 3. 同步（vendor blob 需另行提取，见 vendor-blobs/）
repo sync

# 4. 提取 vendor blob（从 MIUI V12.5.2.0.QECCNXM）
#    见 vendor-blobs/ 说明

# 5. 应用补丁
for p in patches/*.patch; do git apply $p; done

# 6. 编译
source build/envsetup.sh
lunch aosp_equuleus-bp1a-userdebug
mka bacon
```

详细步骤见 `docs/FIRST_BUILD_RUNBOOK.md` 和 `docs/REPRODUCE.md`。

## 关键修复记录（本轮）

1. **启动循环**：vendor 缺 Adreno EGL / Keymaster / Gatekeeper（`make_vendor_trees.py` 跳过 `/bin/` 安装 + 共享库未进包），修复 system_server 空指针 + SELinux 拒绝 `IFastCharge`
2. **触摸点击失灵**：fts 触摸驱动把压力值当面积上报，`touch.size.calibration=GEOMETRIC` 误判，新增 `fts.idc` 修正
3. **LiveDisplay 崩溃循环**：设备树 AIDL 迁移与 PixelOS framework（HIDL 2.0）版本错配，回退 HAL 到 HIDL
4. **默认相机**：集成 GCam、移除 Aperture

详见 `docs/` 下各文档。
