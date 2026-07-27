@echo off
cd /d f:\Codex项目文件\班组排产系统

echo === Removing tracked files that should be ignored ===
git rm -r --cached scripts/screenshots/ 2>nul
git rm -r --cached scripts/downloads/ 2>nul
git rm -r --cached downloads/ 2>nul
git rm --cached screenshot.png 2>nul
git rm --cached debug_workshop.png 2>nul

echo === Committing changes ===
git add -A
git commit -m "chore: update .gitignore to exclude screenshots and downloads

- 忽略 scripts/screenshots/ 和 scripts/downloads/ 调试截图
- 忽略 downloads/ 目录所有文件
- 从 git 跟踪中移除已忽略的文件"

echo === Pushing to Gitea ===
git push

echo === Done ===
pause
