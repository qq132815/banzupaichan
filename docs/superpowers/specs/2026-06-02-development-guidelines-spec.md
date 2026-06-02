# 2026-06-02 班组排产系统 - 开发规范与约束 (Development Guidelines & Constraints)

## 1. 核心痛点 (Core Pain Points)
- **前后端逻辑不同步**: 数据库字段变更导致前端报错。
- **权限控制遗漏**: 新功能未适配不同角色的访问权限。

## 2. 开发检查清单 (Checklists)

### 2.1 前后端同步清单 (Sync Checklist)
修改数据库字段或业务逻辑时，必须按顺序检查：
1.  **数据库层**: 
    - utils/db.py: 修改 CREATE TABLE 语句。
    - data/production.db: 如果是现有表，需通过 ALTER TABLE 兼容旧数据。
2.  **后端层 (pp.py)**: 
    - 检查所有相关的 INSERT/UPDATE/SELECT 语句。
    - 确保 API 返回的 JSON key 与前端一致。
3.  **前端层**:
    - **表单**: 检查 <input name=...> 是否匹配。
    - **表格**: 检查列头 (headers) 和 JS 渲染逻辑。
    - **调用**: 检查 etch 或 XMLHttpRequest 发送的数据 key。

### 2.2 权限控制清单 (Permission Checklist)
新增功能必须通过三层验证：
1.  **后端路由 (Route)**:
    - 管理员专用: @admin_required
    - 计划员/管理员: @planner_required
    - 登录用户: @login_required
2.  **侧边栏菜单 (Menu)**:
    - 必须在 	emplates/base.html 中为菜单项添加 data-perm 属性。
3.  **页面元素 (Elements)**:
    - **可见性**: 班组角色只能看到/操作与其相关的数据。
    - **只读性**: 非管理员/计划员在特定页面应设置 disabled 或 
eadonly。
    - **JS 判定**: 使用 window.USER_ROLE 进行前端逻辑分支。

## 3. 业务逻辑约束 (Business Logic Constraints)

### 3.1 工时计算 (Working Hours Calculation)
- **早班**: 08:00 - 17:00 (8小时)，**扣除 11:45 - 12:45 午休**。
- **加班**: 17:30 - 20:00 (2.5小时)，**扣除 17:00 - 17:30 晚餐休息**，不扣其他休息。
- *一致性要求*: 前端显示的工时必须与后端计算结果完全一致。

### 3.2 设备排序 (Equipment Sorting)
- **规则**: 使用自然排序 (Natural Sort)。
- **示例**: WG7-1, WG7-2, ... WG7-10 (而非 WG7-10 排在 WG7-2 前)。

### 3.3 班组过滤 (Team Filtering)
- **场景**: 排班页面甘特图、设备下拉列表、报工记录。
- **规则**: 必须根据 session[team_id] 或 window.TEAM_ID 过滤数据，班组只能看到自己的数据。

## 4. 变更记录 (Change Log)
- **2026-06-02**: 初始化开发规范，确立检查清单。
