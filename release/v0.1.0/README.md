# PDM 0.1.0 离线安装包（分卷）/ Offline installer (split volumes)

| 文件 File | 大小 Size |
|---|---|
| [pdm-0.1.0-offline-win64.zip.001](pdm-0.1.0-offline-win64.zip.001) | 100 MB |
| [pdm-0.1.0-offline-win64.zip.002](pdm-0.1.0-offline-win64.zip.002) | 38 MB |
| [join.cmd](join.cmd) | 合并脚本 / join script |
| [SHA256SUMS.txt](SHA256SUMS.txt) | 校验值 / checksums |
| [部署说明 / DEPLOY_GUIDE.md](../../deploy/offline/DEPLOY_GUIDE.md) | 中英文 / zh-en |

## 合并

把两个分卷和 `join.cmd` 放在同一个文件夹，双击 `join.cmd`。它会合并出 `pdm-0.1.0-offline-win64.zip` 并校验 SHA-256。也可以手动执行：

```
copy /b pdm-0.1.0-offline-win64.zip.001+pdm-0.1.0-offline-win64.zip.002 pdm-0.1.0-offline-win64.zip
```

7-Zip 也可以直接打开 `.001`。然后解压，双击 `install.cmd`，按部署说明操作。

## Join

Put both volumes and `join.cmd` in one folder and double-click `join.cmd`. It rebuilds `pdm-0.1.0-offline-win64.zip` and checks its SHA-256 (or run the `copy /b` line above; 7-Zip can also open `.001` directly). Then unzip and double-click `install.cmd`.

This build includes the httpx runtime dependency and the Windows PowerShell 5.1 installer fix.
