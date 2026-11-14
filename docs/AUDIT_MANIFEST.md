# AUDIT_MANIFEST

Every file in this archive, why it exists, and which upstream commit
it applies to. SHA256 lets a reviewer confirm nothing was altered in
transit; `ZIP_MANIFEST.tsv` carries the same list in machine form.

Archive: `PixelOS_equuleus_AUDIT_PACKAGE.zip`  
Generated: 2026-11-12T21:51:38Z  
Files: 107  

## 1. Project-authored files

| Path | SHA256 | Purpose | Upstream base |
| --- | --- | --- | --- |
| `blob_sources.json` | `f947c19e1011fdcec3e297643965939cb621b9cf38dbe79e8bc4a6ef190e9292` | machine-readable blob source record | authored (this project) |
| `evidence/blob-archive/MANIFEST.sha256` | `62a0e0dd20c7b047bf55f40f092dd63295eeb119d57f539b8fbbc604d6db838d` | per-file SHA256 of all 872 blobs | authored (this project) |
| `evidence/blob-archive/VOLUMES.sha256` | `1d37065451ff7bb19d13ac6a34f13453449dc135ff89c433e7ba5e69c4f08ddc` | archive volume checksum | authored (this project) |
| `evidence/round15/round15-p0-fixes.log` | `1f9b9844a9f711f7deb1c1fabef3f194f793a4f146765c5efab8a534a7cd6f0f` | before/after of the BUILD READY bypass + 7/7 fault injection | authored (this project) |
| `evidence/round15/mutations.log` | `10bfd1904665b0e6d42af330cd66355cd221263db3340b1038a55253f323684e` | 64/64 mutation results | authored (this project) |
| `README.md` | `79b96958b6fdf159a303c1d6471e017786dafb28c7b436d0a447f0cbd710639c` | entry point: what this package is and is not | authored (this project) |
| `UPSTREAM_LOCK.md` | `605c9110e5f978864748e74460f5e1d158cf72b86d082b071c2ccf1ba0fd771a` | P0 dependency lock: every pinned commit + real-clone proof | authored (this project) |
| `KNOWN_BLOCKERS.md` | `1cc0f31398dab8bc56d4800a0376fe0a77f565b036a787a0191c59f99f5010a9` | 14 tracked blockers with severity, evidence, status | authored (this project) |
| `TEST_REPORT.md` | `b376e4e6607bbc28559e1baaef187e0d7fec5bb8aead111dcfc56af534759683` | three-bucket verification matrix (executed/failed/not executed) | authored (this project) |
| `CLOUD_READINESS.md` | `afd020df590faeaa5024e70f0a6b276d6f6c946343c31892d53fa250706a5878` | paid-ECS gate analysis and two-stage preflight rationale | authored (this project) |
| `DEVICE_AUDIT.md` | `d56cc88daa52263808bb4fdbdeb048f68f273dba20d40de8b181c5d8d2a6202c` | FOD / camera / NFC static audit with verification status | authored (this project) |
| `VENDOR_TRANSFER.md` | `54662eb998eef2639df7af469a15aef855c68a92b4eefd63ef7589a4d16ad826` | how to ship and verify the blob archive | authored (this project) |
| `FIRST_BUILD_RUNBOOK.md` | `9f6deb0b2b303863c582a2769fb6a1d3cfdd0ea648456253fdc34a1a62851c95` | the cloud build sequence, NOT YET EXECUTED | authored (this project) |
| `MIUI_IR_BLOB_INVENTORY.md` | `b1a86dd4d5b1b29dd9823fbaf13667a4b0d6c8a1d260f19e86872988428096a8` | what the factory MIUI firmware contains | authored (this project) |
| `MIUI_VS_LINEAGE_IR_DIFF.md` | `b485d0f5d6668fb8c724ae5475eb0d3d672b2a421e50fc34c3dfb79820903330` | byte-level MIUI vs LineageOS IR comparison | authored (this project) |
| `IR_FACE_UNLOCK_DEPENDENCIES.md` | `79ea0aadcc6b62fa8dc93a1d6beb6dc5173f054d8ae3a50b924d560381ed455d` | IR unlock dependency chain + device test plan | authored (this project) |
| `logs/miui-ir-extraction.log` | `c624068cd945d4b36d0c39a65ec17380e6198fd0a69b90f3eb26d15885e4e8e8` | actual MIUI extraction and comparison log | authored (this project) |
| `logs/miui-ir-compare.json` | `f58ad9322d03ba7481e542ff1b55f6d74b114ec8b3d08837df95c274c4082bca` | machine-readable 18-path comparison | authored (this project) |
| `B01_EXTRACTION_REPORT.json` | `54a05b19de466480f27977be26988cea37c70072ecbe01370eb80daa93fa5c3c` | proven extraction record: partitions, 862-entry resolution, verification | authored (this project) |
| `BLOB_SOURCES.md` | `a90b3c4f7c121fab7e52e91c0476383615fb5c974561bdce2930b4d516759745` | OTA source record: URL, SHA256, verified format, execution status | authored (this project) |
| `BLOB_EXTRACTION.md` | `5a9f62f1c0eb9f840fe118fc3d5141b5157100b8e92c922f08fdd39d9a8bd1dd` | firmware matrix, extract-utils grammar, post-processing | authored (this project) |
| `patches/0001-equuleus-product-setup.patch` | `e1ba845c0b1065824bc4b1157de2995f4e39b2a5da3e881b85ed71a6e9cc8dc5` | equuleus: add PixelOS product definition (aosp_equuleus + lunch choices) | device/xiaomi/equuleus @ db40750f… |
| `patches/0002-equuleus-drop-lineage-sdk-overlay.patch` | `4dd335564bf6e8dba42772c1e35cf2ede5a7eacf9a4f4c1521b9ebd3550bd5d1` | equuleus: drop overlay subtree with no PixelOS target (lineage-sdk) | device/xiaomi/equuleus @ db40750f… |
| `patches/0003-sdm845-common-use-vendor-aosp.patch` | `e4b27ae6421b800cd9205854e9e629365797f0daf73f503e2ae0d3a854bc4d33` | sdm845-common: switch build policy to vendor/aosp equivalents | device/xiaomi/sdm845-common @ 35cf356b… |
| `patches/0004-sdm845-common-drop-lineage-overlays.patch` | `611989a5fe07526b9e8349da6cae319f2992e8bf24171d1bc248733c348ad53d` | sdm845-common: drop overlays with no PixelOS target | device/xiaomi/sdm845-common @ 35cf356b… |
| `patches/0005-manifest-gms-repo.patch` | `6b4ca979a4174666d1aeab219c56c01350adcfd43a87da15267046a6f173860c` | manifest: repoint vendor/gms to the fifteen-compatible repository | PixelOS-AOSP/manifest @ 0334d5e4… (branch fifteen) — edits snippets/custom.xml |
| `patches/0006-equuleus-fix-pn553-fw-path.patch` | `5d8897e301e03f1bf7d1c099438ef244541998ed6f0f985ecc6cc61e629393a7` | patch | device/xiaomi/equuleus @ db40750f… |
| `patches/0007-equuleus-ir-face-unlock-camera-id.patch` | `30a214905faa9a2d6f1d0b162c91c3601478e308fa932124b9b51bc5b9738f78` | patch | device/xiaomi/equuleus @ db40750f… |
| `patches/0008-sdm845-common-ir-face-unlock-aux-camera.patch` | `55f2a1caca8a6f080ff02dc2f3b718a3adbb051a04b394191a41f7ab5df54e94` | patch | device/xiaomi/sdm845-common @ 35cf356b… |
| `.repo/local_manifests/equuleus.xml` | `d6fc652c7f75308f3bd796d19d0bb17cb994f5aade49b28af02c5cc3d88c929f` | repo local manifest: 5 pinned projects, vendor/gms repoint, remotes | authored (this project) |
| `scripts/host-preflight.sh` | `d45ca20245e3f001cb6b8623bc4605b83fb19a2e3e6765f999b296d432b4d0ea` | project script (see file header) | authored (this project) |
| `scripts/build-preflight.sh` | `ccd3b3b19300cd7000cd0bec472126669282b2f55caa1e11ba2384e4ed81a1f7` | project script (see file header) | authored (this project) |
| `scripts/preflight.sh` | `6c8b6e92a24629772007e4c67faf0ee3339885eec5de99ffbda32fe67f4049e6` | project script (see file header) | authored (this project) |
| `scripts/sync.sh` | `67edd68c69db78398c875f87522480a1fc6a6a6b8f6bda279287ea56a156672c` | project script (see file header) | authored (this project) |
| `scripts/build.sh` | `da383626cbf433ca74bf6b3599a16a672249c938eae3c45cd36f2ee736e871a1` | project script (see file header) | authored (this project) |
| `scripts/verify_deliverables.py` | `d61e3d56c374a403997d77ef895e876cc059e6f3df32df2949375318353ea9cc` | project script (see file header) | authored (this project) |
| `scripts/verify_mutations.py` | `860c213eb885d39a0baa4eda15825d6165800c3e8d05439eea4e48381b8a2fc7` | project script (see file header) | authored (this project) |
| `scripts/verify_blobs.py` | `d34840855a93c37707057d2bfafe799ceb730138efa53fd448991d6834904e68` | project script (see file header) | authored (this project) |
| `scripts/verify_patch_coverage.py` | `187e89a037640e1efdeb35c832ba6e469c4be9dccad5e76044422317a242aeb5` | project script (see file header) | authored (this project) |
| `scripts/verify_manifest_parse.py` | `6cdf886c1eae02f30baa8a33e0fbaaeab1d37a3f92a06be6d6a33a718b4fe82d` | project script (see file header) | authored (this project) |
| `scripts/test_verify_blobs.py` | `89bf983e7f512402dc150e2f5192bc0ed7f8f73196749bccf9574a565eb5ae1f` | project script (see file header) | authored (this project) |
| `scripts/test_build_artifacts.py` | `67e323da7d1f5f8a1a60bfc942ba77a76e60a8cfb43d7b75c94843e6f95b417e` | project script (see file header) | authored (this project) |
| `scripts/pack_vendor.sh` | `4574f70080874f0e583277baaa35364b2fd66c0d35095e85f6680b2052c5cc62` | project script (see file header) | authored (this project) |
| `scripts/test_first_build_flow.py` | `e11810c1737908e0a525886098069917bd2a1e5686693e8f0435775fbc52fd8d` | project script (see file header) | authored (this project) |
| `scripts/cloud_vendor_transfer.sh` | `a55f501653944138478199ded7e6c3c4fa5aa6e79fd3f11d04dd07ff860e8c66` | project script (see file header) | authored (this project) |
| `scripts/verify_ubuntu_portability.py` | `ef9fabbe41cd672a89e45f9d3ac319a7869f06253620c5bcbcd62932aa0a31da` | project script (see file header) | authored (this project) |
| `scripts/compare_ir_blobs.py` | `ca12f4b39bdd6fc6175b7726f8acb152b4372b4404e297e52e25f141d9317cf7` | project script (see file header) | authored (this project) |
| `scripts/simg2img.py` | `9d7854446d11cf190e9049e363dce3caf6e11f2b5a0571bad47eb0568eb00e92` | project script (see file header) | authored (this project) |
| `scripts/verify_miui_ir_analysis.py` | `9ce501fffca6731caee7577670bba2eed42c39d9d6368402eef343dd1bfbad80` | project script (see file header) | authored (this project) |
| `scripts/verify_ir_face_unlock.py` | `8b0a471236e77fbbc1b33b9cf1da9c40cde5378e2e3943c60ac41de05bdbe9e3` | project script (see file header) | authored (this project) |
| `scripts/export_ir_patches.py` | `0f97a28b4e376dc77f3b1295d5b01cf3bda759f9a3b9b7273035d3905923cef1` | project script (see file header) | authored (this project) |
| `scripts/apply_ir_face_unlock.py` | `1e6b62faa28337eb334bbd7ea568b6cc920c8b18cefeb1d05d5ceb7666098eae` | project script (see file header) | authored (this project) |
| `scripts/ota_extract.py` | `6ae62c34481df0365a82e13c76fcbf35ee84d1d36664e65754a1cb4a8a7258d7` | project script (see file header) | authored (this project) |
| `scripts/img_extract.sh` | `1a76d43d95b3413cf6f4c3e708d2447e4ec367b36dd37970024baba3f0cb0d6e` | project script (see file header) | authored (this project) |
| `scripts/blob_audit.py` | `c7870549e18ac461e1f27ad754c3e67ace836ee3095453a1a8b66d26136298fc` | project script (see file header) | authored (this project) |
| `scripts/make_vendor_trees.py` | `20a5100ffab576ccacd1f9a81a9ab53209964ee27768e60d535ff9f17ae072a4` | project script (see file header) | authored (this project) |
| `scripts/extract_vendor_full.sh` | `b9b727308ce445ad737ade3cd7f10d53b825bcb50deb9dc1c9a16611d9483c38` | project script (see file header) | authored (this project) |
| `scripts/fetch_lineage_ota.sh` | `a08bcb8d7f333fe459ad87787dfd0c34ac0b040c05b265cf0cb7ae66bc57b684` | project script (see file header) | authored (this project) |
| `scripts/extract_blobs_from_ota.sh` | `1cb6c62fa594022ed4c690bb5be0fa71b9fddeb7a84696349c842e38b32206fc` | project script (see file header) | authored (this project) |
| `scripts/fetch_clones.sh` | `071b1a5f0ecba2a5f420d559020300d9296c02b0a4a35fbaa1bcf1b41c3a8100` | project script (see file header) | authored (this project) |
| `scripts/export_patches.py` | `0479c493e20cf67fb46acdd309f4024efe9bb46c286968940c1891c316aaedca` | project script (see file header) | authored (this project) |
| `scripts/extract_package.py` | `dca6174305e69d709bcde608b23fbd0008332eb4d86763328d5007f3ebff45fa` | project script (see file header) | authored (this project) |
| `scripts/extract_audit_package.py` | `aa06646e72c23ed2dc859476060b5383147f9f5dab3600ec80fe648507a4b683` | project script (see file header) | authored (this project) |
| `scripts/make_package.py` | `063b2639521b594632ee4f9fb3cf8700d3e2424abad4e54f906f731b0da9d221` | project script (see file header) | authored (this project) |
| `scripts/make_audit_package.py` | `66fcac5c445962d5d0801d1dabde6ef537cbe9afd37ba58d52431fc8687c6983` | project script (see file header) | authored (this project) |
| `evidence/fixtures/minimal.so` | `eb638718394701d651dee5b2fe617ab76817abd0b6939172beae35222c44a1d3` | 435-byte hand-built ELF64 test vector for the DT_SONAME reader in verify_blobs.py (synthetic, not a vendor blob) | synthetic test vector |
| `evidence/VERIFICATION_TRANSCRIPT.txt` | `32032f444c38e5c526431b57beb79c5e35c748732911cd0923e1fd58edb1f22b` | condensed logs: full commands, exit codes, FAIL/WARN context | generated from logs/ |
| `evidence/logs/deliverables-20261112T061522Z.log` | `2446579d3fdba2ef33d688c4dda07c946d09b747053c2cc01e08edfbd057c8d3` | raw log retained verbatim (4515 B) | generated from logs/ |
| `evidence/logs/fetch-ota-20261112T065855Z.log` | `f3a1495496b7a42725c008cfc470db0a5b9fbc7fed4fab085809c2e0418eadf7` | raw log retained verbatim (656 B) | generated from logs/ |
| `evidence/logs/final-state.sha256` | `c34b4a273970dcef84ce393f0ce7f040a08fda6596c68ec993cb03c9670652a4` | raw log retained verbatim (2326 B) | generated from logs/ |
| `evidence/logs/host-preflight-20261111T193211Z.log` | `a2f82d33be5057ddde59a8f72a5e60043a4246a2ef8d5ab50eb8587e0fe962a8` | raw log retained verbatim (2716 B) | generated from logs/ |
| `evidence/logs/host-preflight-20261111T193414Z.log` | `afc4bf2891adfcf910e8387d1fa8db59aab9016183646698ff0c76d91e72cc10` | raw log retained verbatim (2695 B) | generated from logs/ |
| `evidence/logs/host-preflight-20261111T202229Z.log` | `f957c568241a286f8ca83d1bbc8b66dd4949f915cdfb4b092330c95f278f04d8` | raw log retained verbatim (2624 B) | generated from logs/ |
| `evidence/logs/host-preflight-20261112T042933Z.log` | `8493d6c38b9747a01bf63c4bf765a699b6bd27f0b4356a2a31851c14499240da` | raw log retained verbatim (2116 B) | generated from logs/ |
| `evidence/logs/host-preflight-20261112T043135Z.log` | `2b5257d50c64b8a15f7c68e12b8b28e9a5a2563084b50c2ef02c0fdb61ea00ac` | raw log retained verbatim (3442 B) | generated from logs/ |
| `evidence/logs/host-preflight-20261112T045819Z.log` | `56790082fd544f51a4dc5e8c90410089dc3e5ecd221b9e702dff38072a46e321` | raw log retained verbatim (2071 B) | generated from logs/ |
| `evidence/logs/ldfm.xml` | `7cfb5692b2a4ee9451d9233d8aaac278eabb6aff656ce8cd076fa718a703a756` | raw log retained verbatim (7152 B) | generated from logs/ |
| `evidence/logs/manifest-parse-20261111T214848Z.log` | `0bf6afcb6e13ac1599138da2690e7a10709250ed09b2cc2c566c680e67ef1175` | raw log retained verbatim (1165 B) | generated from logs/ |
| `evidence/logs/missing_paths.json` | `207584f75d26820014779602026cdc202e5974a78d3054ab88c63e7340af7402` | raw log retained verbatim (1506 B) | generated from logs/ |
| `evidence/logs/miui-ir-compare.json` | `f58ad9322d03ba7481e542ff1b55f6d74b114ec8b3d08837df95c274c4082bca` | raw log retained verbatim (15143 B) | generated from logs/ |
| `evidence/logs/miui-ir-extraction.log` | `c624068cd945d4b36d0c39a65ec17380e6198fd0a69b90f3eb26d15885e4e8e8` | raw log retained verbatim (5354 B) | generated from logs/ |
| `evidence/logs/mutations-20261112T061522Z.log` | `f3fe411c35264bd9037e423ba96d03814f529bc5b4509b8fee0f1dffa56f318d` | raw log retained verbatim (4681 B) | generated from logs/ |
| `evidence/logs/mutations-final.log` | `10bfd1904665b0e6d42af330cd66355cd221263db3340b1038a55253f323684e` | raw log retained verbatim (6847 B) | generated from logs/ |
| `evidence/logs/mutations-r12.log` | `d6b6b6f9ae2878c9281a52e5a57e62283e74952dc905b246415d599bb6afb236` | raw log retained verbatim (5899 B) | generated from logs/ |
| `evidence/logs/mutations-r13.log` | `d6b6b6f9ae2878c9281a52e5a57e62283e74952dc905b246415d599bb6afb236` | raw log retained verbatim (5899 B) | generated from logs/ |
| `evidence/logs/mutations-r13b.log` | `a5f9db34909f9b45bd68f96cd593336967e974dee31dfc004228675669898f69` | raw log retained verbatim (6149 B) | generated from logs/ |
| `evidence/logs/mutations-r14.log` | `a5f9db34909f9b45bd68f96cd593336967e974dee31dfc004228675669898f69` | raw log retained verbatim (6149 B) | generated from logs/ |
| `evidence/logs/mutations-r15.log` | `10bfd1904665b0e6d42af330cd66355cd221263db3340b1038a55253f323684e` | raw log retained verbatim (6847 B) | generated from logs/ |
| `evidence/logs/pack-vendor-20261112T135917Z.log` | `e7903ebca58c747e9dbdd5efebfddc0baa6fc4a55aa2bb82d8e7207c1c22dca0` | raw log retained verbatim (1907 B) | generated from logs/ |
| `evidence/logs/preflight-20261111T172531Z.log` | `e76825a2afcf2fe61509045109362efd3715b81c915ff9a4e1a16baa9fd51543` | raw log retained verbatim (3733 B) | generated from logs/ |
| `evidence/logs/preflight-20261111T172702Z.log` | `21f69dc935a2e74585ffca0b0659bddd631220ed037c927e9d4cadc5e29c1e97` | raw log retained verbatim (3776 B) | generated from logs/ |
| `evidence/logs/preflight-20261111T174507Z.log` | `9c564530ef537a20f1370a9b28de074e1e6c059120cb8839952be17479321467` | raw log retained verbatim (3827 B) | generated from logs/ |
| `evidence/logs/round15-p0-fixes.log` | `1f9b9844a9f711f7deb1c1fabef3f194f793a4f146765c5efab8a534a7cd6f0f` | raw log retained verbatim (1547 B) | generated from logs/ |
| `evidence/logs/test_build_artifacts-20261112T061522Z.log` | `3bd99cf821d2feadf5a514f5bb40092a70f2fdf7df9fd44bc3e8a5e7622a5d15` | raw log retained verbatim (1000 B) | generated from logs/ |
| `evidence/logs/test_build_artifacts-20261112T075157Z.log` | `adc830452c60b232a9b1dd28ed62d074eec764ce16c132eb744fed86204ea9e6` | raw log retained verbatim (1535 B) | generated from logs/ |
| `evidence/logs/test_build_artifacts-20261112T102209Z.log` | `adc830452c60b232a9b1dd28ed62d074eec764ce16c132eb744fed86204ea9e6` | raw log retained verbatim (1535 B) | generated from logs/ |
| `evidence/logs/test_build_artifacts-20261112T121304Z.log` | `adc830452c60b232a9b1dd28ed62d074eec764ce16c132eb744fed86204ea9e6` | raw log retained verbatim (1535 B) | generated from logs/ |
| `evidence/logs/test_verify_blobs-20261112T061522Z.log` | `0375bcd3f98b3a46a38b28928dc199939f0f69297ed32a7850ede277f715a756` | raw log retained verbatim (1202 B) | generated from logs/ |
| `evidence/logs/test_verify_blobs-20261112T075157Z.log` | `0375bcd3f98b3a46a38b28928dc199939f0f69297ed32a7850ede277f715a756` | raw log retained verbatim (1202 B) | generated from logs/ |
| `evidence/logs/test_verify_blobs-20261112T102209Z.log` | `4da45ce931f705363f791fdc69b40440f8c1a728048e0ca68a0fc276c7ba00d2` | raw log retained verbatim (1186 B) | generated from logs/ |
| `evidence/logs/test_verify_blobs-20261112T121304Z.log` | `4da45ce931f705363f791fdc69b40440f8c1a728048e0ca68a0fc276c7ba00d2` | raw log retained verbatim (1186 B) | generated from logs/ |
| `evidence/logs/verify_deliverables-20261112T075157Z.log` | `3ffbc2e291f5914d57b70fcea7087d2beabf13fbfc2c8fac9900956b2e864b6a` | raw log retained verbatim (5015 B) | generated from logs/ |
| `evidence/logs/verify_deliverables-20261112T102209Z.log` | `762adc6a390bceda190ce50834db168d1cd52eaac1e196e1e6d44bec5bbb7dd9` | raw log retained verbatim (5015 B) | generated from logs/ |
| `evidence/logs/verify_deliverables-20261112T121304Z.log` | `fe3120ec603cc6f2366ccf8a77b245f8a89e340d20f386ea6b1bf3bf7e919676` | raw log retained verbatim (5139 B) | generated from logs/ |
| `evidence/logs/verify_ir_face_unlock-20261112T121304Z.log` | `416c651d10d31a829ca477c46497164b3b5cc5be1f66d36a6011868f9049d193` | raw log retained verbatim (1386 B) | generated from logs/ |
| `evidence/logs/verify_mutations-20261112T075157Z.log` | `c37de3a2b6e25b46749f208b23f1ec73c1526f1bb6bc446e69ed5345ee5600aa` | raw log retained verbatim (5157 B) | generated from logs/ |
| `evidence/logs/vl.json` | `e3893d9402f7fbc8366b2ad2f1a5e7d9d982c649270d7ed3bfcdbc55ecbf8839` | raw log retained verbatim (2774 B) | generated from logs/ |

## 2. Upstream commits this package pins

| Path in tree | Repository | Branch | Commit |
| --- | --- | --- | --- |
| `device/xiaomi/equuleus` | `LineageOS/android_device_xiaomi_equuleus` | `lineage-22.2` | `db40750f063e86110e20db1455729c0f6621f7da` |
| `device/xiaomi/sdm845-common` | `LineageOS/android_device_xiaomi_sdm845-common` | `lineage-22.2` | `35cf356b095e033e71261b16c7fa319faac12cb3` |
| `kernel/xiaomi/sdm845` | `LineageOS/android_kernel_xiaomi_sdm845` | `lineage-22.2` | `aa8adfe9bf212c6e93238a86980b4024da4f819a` |
| `hardware/xiaomi` | `PixelOS-AOSP/hardware_xiaomi` | `fifteen` | `281f97dbac46b75eb7b6a680624e62e807ec0689` |
| `hardware/lineage/interfaces` | `LineageOS/android_hardware_lineage_interfaces` | `lineage-22.2` | `3466aa530ace6de0760c12a68cf81b31e8d3807b` |
| `vendor/aosp` | `PixelOS-AOSP/vendor_aosp` | `fifteen` | `2887d1b7729f38560b1cb4b27317c2bf29f2325b` |
| `vendor/gms` | `PixelOS-AOSP/vendor_gms-15 (GitLab)` | `fifteen` | `ffe5c52d947eec784a07124dfb72e95840e8f3c7` |
| `manifest` | `PixelOS-AOSP/manifest` | `fifteen` | `0334d5e468a86ab0aefa6d3a40bc2abd11bf4035` |

## 3. Deliberately excluded, and why

| Excluded | Reason |
| --- | --- |
| `src/` (upstream snapshots, ~166 MiB) | Verbatim upstream source we did not author. Byte-identical to the tarballs at the pinned commits; regenerable via `fetch_clones.sh`. Reviewing it adds size, not signal. |
| `clones/` (real git clones, ~800 MiB) | Needed only to prove pins are real commit objects. Recreated with `scripts/fetch_clones.sh`, which fails if any HEAD differs from its pin. |
| `work/` (review commits, ~2.5 MiB) | The patches are byte-identical to these commits (verified by `verify_patch_coverage.py`); inside the full tree only. |
| Kernel tree (~174 MiB tarball) | No patch in this package touches the kernel. Its two defconfig files are quoted by path and line in `KNOWN_BLOCKERS.md` B-04. |
| `.git/`, `out/`, `ccache/` | Build and VCS metadata; no review value and large. |
| Firmware images, `vendor/xiaomi/**`, proprietary `.so` | Not redistributable, and none was ever obtained. See `BLOB_EXTRACTION.md`. |
| `logs/*.json` scraped trees (2.1 MiB `hwif.json`, etc.) | Bulk scrape data. The conclusions drawn from it are written into the docs with file/line citations, so the raw dumps are not needed. |
| Credentials, tokens, keys | None were ever present. The acceptance suite asserts this and the mutation suite proves the assertion can fail. |

## 4. How to verify this archive

```bash
# Run from the directory that CONTAINS the zip; -m zipfile handles
# any long AIDL paths without needing the bundled extractor.
python -m zipfile -e PixelOS_equuleus_AUDIT_PACKAGE.zip /tmp/audit
cd /tmp/audit/PixelOS_equuleus_AUDIT_PACKAGE
chmod +x scripts/*.sh   # a ZIP built on Windows loses the +x bit
python scripts/verify_deliverables.py      # static acceptance
python scripts/verify_mutations.py         # proves the suite can fail
python scripts/verify_patch_coverage.py    # every authored change exported
```

`verify_deliverables.py` will report which checks need files that are
*intentionally* absent here (the upstream source tree and real git
clones). That is expected: see `REPRODUCE.md` for the checks that do
run standalone, and for how to materialise the full evidence base.
