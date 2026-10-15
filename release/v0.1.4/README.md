# PDM 0.1.4 升级包 / Upgrade package

只含程序代码（约 5 MB），用于已安装 0.1.0–0.1.3 离线安装包的服务器；不改动数据库内容、账号、`pdm\backend\.env`（含涛思账号）、内置 Python。
Code only (about 5 MB) for servers installed from an offline package 0.1.0–0.1.3. Database contents, accounts, `pdm\backend\.env` (including TDengine accounts) and the bundled Python are not touched.

| 文件 File | 说明 Note |
|---|---|
| pdm-0.1.4-upgrade-win64.zip | 升级包 / the upgrade package |
| SHA256SUMS.txt | 校验值 / checksum (`certutil -hashfile pdm-0.1.4-upgrade-win64.zip SHA256`) |
| RELEASE_NOTES.md | 更新内容 / changes |

## 步骤 / Steps

1. 下载 zip，解压到任意文件夹（例如桌面），**不要**解压进安装目录。 Download and unzip into any folder, **not** into the install folder.
2. 双击 `pdm-upgrade\upgrade.cmd`，在 UAC 提示中选“是”。 Double-click `upgrade.cmd` and accept the UAC prompt.
3. 脚本会备份旧程序（和数据库，若找到 `pg_dump`）到 `C:\ProgramData\PDM\backup\`，替换程序文件，迁移结构，重启服务。 It backs up the old program (and the database when `pg_dump` is found), replaces program files, migrates and restarts the service.

详见 `pdm-upgrade\DEPLOY_GUIDE.md` 末尾“升级包”一节。未在真实 Windows 上运行过，首次升级前请自行备份数据库。
See the "Upgrade package" section at the end of `DEPLOY_GUIDE.md`. Not yet run on real Windows; back up your database yourself before the first upgrade.
