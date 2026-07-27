@echo off
cd /d f:\Codex项目文件\班组排产系统

echo === Adding files modified after 2025-07-21 ===
powershell -Command "Get-ChildItem -Recurse -File -Exclude '*.pyc' | Where-Object { $_.LastWriteTime -gt (Get-Date '2025-07-21') -and $_.FullName -notmatch '\\\.git\\' -and $_.FullName -notmatch '\\__pycache__\\' -and $_.FullName -notmatch '\\downloads\\' -and $_.FullName -notmatch '\\screenshots\\' } | ForEach-Object { $rel = $_.FullName.Substring((Get-Location).Path.Length+1); Write-Host $rel; git add $rel }"

echo === Committing ===
git commit -m "feat: 新增装框量字段及CI/CD配置

- work_reports 表新增 frame_qty 字段
- MES同步映射新增'每（筐/车）容量'列
- 标准工时页面显示装框量(平均值)
- 报工明细弹窗显示装框量列
- 新增 Gitea Actions CI/CD 工作流
- 更新 .gitignore"

echo === Pushing to Gitea ===
git push

echo === Done ===
pause
