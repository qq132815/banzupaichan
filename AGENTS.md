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

## 重要注意事项
1. PowerShell中写Python脚本时，使用@' ... '@语法并保存到文件执行
2. 中文字符在PowerShell控制台可能显示乱码，但文件内容是正确的
3. 数据库路径是data/production.db，不是data/mes.db
4. rebuild_all.py会重建整个数据库，包括自动创建缺失的工序
