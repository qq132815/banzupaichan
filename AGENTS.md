# AGENTS.md - 班组排产系统

## 项目概述
这是一个制造企业MES班组排产系统，用于管理生产计划、设备排班和进度跟踪。

## 技术栈
- **后端**: Python Flask
- **数据库**: SQLite (production.db)
- **前端**: 原生HTML/CSS/JavaScript
- **Excel处理**: openpyxl

## 项目结构
```
班组排产系统/
├── app.py                 # Flask主应用，所有API路由
├── requirements.txt       # Python依赖
├── data/
│   └── production.db     # SQLite数据库
├── imports/              # 上传的Excel文件存储
├── scripts/
│   └── rebuild_all.py    # 数据库重建脚本
├── static/
│   ├── css/style.css     # 全局样式
│   └── js/app.js         # 通用JS函数
├── templates/
│   ├── base.html         # 基础模板(侧边栏)
│   ├── login.html        # 登录页面
│   ├── index.html        # 工作台首页
│   ├── schedule.html     # 排班&甘特图(主页面)
│   ├── alerts.html       # 预警中心
│   ├── orders.html       # 订单管理
│   ├── product_routes.html   # 工艺路线
│   ├── product_cycles.html   # 生产周期
│   ├── product_bom.html      # 物料清单
│   ├── admin_users.html      # 用户管理
│   └── planner_plans.html    # 计划审批
└── utils/
    ├── db.py             # 数据库操作
    ├── excel.py          # Excel导入功能
    └── calc.py           # 计算逻辑(预警/倒推)
```

## 编码规范
- Python: 使用UTF-8编码，处理中文时注意编码问题
- JavaScript: 使用ES5语法，避免使用let/const/箭头函数
- SQL: 使用参数化查询防止注入
- 文件编码: 所有文件统一使用UTF-8

﻿## 开发约束与注意事项 (Development Constraints & Checklist)

**重要：每次修改代码前，必须对照以下清单进行检查，防止“改一处，坏一处”。**

### 1. 前后端同步清单 (Sync Checklist)
如果你修改了数据库字段或业务逻辑，必须同时检查以下内容：
- **数据库层**: `utils/db.py` (CREATE TABLE) 和 `data/production.db` (ALTER TABLE)
- **后端层**: `app.py` 中的 INSERT/UPDATE/SELECT SQL 语句
- **前端层**:
  - HTML表单的 `name` 属性是否匹配？
  - API调用的 JSON key 是否匹配？
  - 表格列头（headers）和渲染逻辑是否更新？

### 2. 权限控制清单 (Permission Checklist)
新增或修改功能时，必须通过以下三层验证：
1. **后端路由 (Route)**: 是否使用了正确的装饰器？
   - 管理员: `@admin_required`
   - 计划员/管理员: `@planner_required`
   - 登录用户: `@login_required`
2. **侧边栏菜单 (Menu)**: 是否在 `templates/base.html` 中设置了 `data-perm` 属性？
3. **页面元素 (Elements)**:
   - 按钮/输入框是否对“班组”角色禁用了 `disabled` 或 `readonly`？
   - JS 中是否处理了角色判断？(参考 `window.USER_ROLE`)

### 3. 常见雷区 (Common Pitfalls)
- **工时计算**: 
  - 早班: 08:00-17:00 (8h)，扣除 11:45-12:45 午休。
  - 加班: 17:30-20:00 (2.5h)，扣除 17:00-17:30 晚餐，不扣其他休息。
  - *注意：前端显示的工时和后端计算逻辑必须一致。*
- **设备排序**: 设备代码（如 WG7-1）必须进行自然排序，避免出现 WG7-10 排在 WG7-2 前面的情况。
- **班组过滤**: 排班页面的甘特图和设备下拉框，必须根据当前登录用户的 `team_id` 进行过滤。


## 数据库表结构
- teams: 班组信息
- equipments: 设备信息
- work_orders: 工单(含process_progress工序进度)
- process_routes: 工艺路线
- processes: 工序定义
- schedules: 排班记录
- daily_plans: 日计划(含状态workflow)
- shipping_plan: 发货计划
- production_cycles: 生产周期
- bom: 物料清单

## 用户角色
- planner(计划员): 可查看所有班组，审批计划
- team(班组): 只能操作自己班组的排班

## 工作时间
- 正常班: 08:00-17:00
- 休息: 10:00-10:10, 11:45-12:45, 15:00-15:10
- 加班: 17:30-20:00(仅当日可加班)

## 分页规范
- 所有数据列表页面必须使用分页，禁止一次性加载全部数据
- 后端API统一支持 `page`（从1开始）和 `page_size`（默认50，最大200）参数
- 返回格式：`{"data": [...], "total": N, "page": P, "page_size": S, "total_pages": T}`
- 前端使用通用分页组件 `renderPagination(containerId, page, totalPages, callback)`
- 搜索/筛选时重置到第1页
- 分页组件包含：上一页、页码、下一页、每页条数选择

## 重要注意事项
1. PowerShell中写Python脚本时，使用@' ... '@语法并保存到文件执行
2. 中文字符在PowerShell控制台可能显示乱码，但文件内容是正确的
3. 数据库路径是data/production.db，不是data/mes.db
4. rebuild_all.py会重建整个数据库，包括自动创建缺失的工序
