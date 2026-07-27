@echo off
cd /d f:\Codex项目文件\班组排产系统
git add -A
git commit -m "feat: 新增装框量字段及CI/CD配置

- work_reports 表新增 frame_qty 字段
- MES同步映射新增'每（筐/车）容量'列
- 标准工时页面显示装框量(平均值)
- 报工明细弹窗显示装框量列
- 新增 Gitea Actions CI/CD 工作流
- 更新 .gitignore"
git push
pause
