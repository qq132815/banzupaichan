# 设备/产线甘特图设计方案（基于真实数据）

## 一、数据分析结论

### 1.1 关键发现
- **工序数量**：114道工序
- **班组权限**：前段、焊接、扣压、装配包装
- **设备机台**：报工表中存在明确的设备字段（如：自动焊H一13、DXw1一12）
- **报工粒度**：精确到分钟级（开始时间、结束时间、时长）

### 1.2 数据关联关系
```
工单 → 工艺路线 → 工序列表
          ↓
       设备机台（通过报工数据关联）
          ↓
       班组权限（工序表中的报工权限字段）
```

---

## 二、数据库表结构设计

### 2.1 设备表（新增）
```sql
CREATE TABLE IF NOT EXISTS equipments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_code TEXT NOT NULL UNIQUE,      -- 设备编号：如 "自动焊H一13"
    equipment_name TEXT NOT NULL,              -- 设备名称
    team_id INTEGER NOT NULL,                  -- 所属班组（前段/焊接/扣压/装配包装）
    equipment_type TEXT,                       -- 设备类型：自动/手动
    status TEXT DEFAULT 'normal',              -- 状态：normal/maintenance/offline
    capacity_per_hour REAL,                    -- 标准产能（件/小时）
    location TEXT,                             -- 位置/产线
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (team_id) REFERENCES teams(id)
);
```

### 2.2 工序-设备关联表（新增）
```sql
CREATE TABLE IF NOT EXISTS process_equipment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_code TEXT NOT NULL,                -- 工序编号：如 "1A"
    equipment_id INTEGER NOT NULL,             -- 设备ID
    is_primary INTEGER DEFAULT 1,              -- 是否主设备（1=主设备，0=备用）
    setup_time INTEGER DEFAULT 0,              -- 换模/准备时间（分钟）
    FOREIGN KEY (equipment_id) REFERENCES equipments(id)
);
```

### 2.3 排程表（扩展现有schedules表）
```sql
-- 扩展现有schedules表字段
ALTER TABLE schedules ADD COLUMN equipment_id INTEGER;
ALTER TABLE schedules ADD COLUMN start_time TEXT;           -- 精确开始时间：08:30
ALTER TABLE schedules ADD COLUMN end_time TEXT;             -- 精确结束时间：12:00
ALTER TABLE schedules ADD COLUMN process_code TEXT;         -- 工序编号
ALTER TABLE schedules ADD COLUMN process_name TEXT;         -- 工序名称
ALTER TABLE schedules ADD COLUMN work_order_no TEXT;        -- 工单编号（关联工单）
ALTER TABLE schedules ADD COLUMN task_status TEXT DEFAULT 'planned'; -- planned/running/completed

-- 添加外键约束
-- FOREIGN KEY (equipment_id) REFERENCES equipments(id)
```

### 2.4 班组表（现有表扩展）
```sql
-- 现有teams表字段补充说明
-- id, name, leader, members, shift_type, shift_start, shift_end
-- 需要确保班组名称与工序表中的报工权限一致：
-- - 前段（前道）
-- - 焊接
-- - 扣压
-- - 装配包装
```

---

## 三、甘特图功能设计

### 3.1 视图维度

#### 日视图（默认）
- **时间轴**：08:00 - 20:00（12小时），按小时刻度显示
- **行维度**：设备机台（每个设备一行）
- **格子**：每设备每小时一个单元格

#### 周视图（可选）
- **时间轴**：周一至周日
- **行维度**：设备机台
- **格子**：每设备每天一个单元格

### 3.2 甘特图组件布局

```
┌─────────────────────────────────────────────────────────────────┐
│  [日期选择]  [班组筛选▼]  [设备筛选▼]  [视图切换: 日|周]  [+新建排程] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  时间轴 →  08:00    09:00    10:00    11:00    12:00    13:00...  │
│           ├────────┼────────┼────────┼────────┼────────┤        │
│  设备A    │ [工单1]│        │ [工单2]│[工单2] │        │        │
│           │  前段   │        │  焊接   │  焊接  │        │        │
│           ├────────┼────────┼────────┼────────┼────────┤        │
│  设备B    │        │ [工单3]│[工单3] │        │ [工单4]│        │
│           │        │  扣压   │  扣压  │        │  前段  │        │
│           ├────────┼────────┼────────┼────────┼────────┤        │
│  设备C    │ [工单1]│[工单1] │        │        │        │        │
│           │  装配   │  装配  │        │        │        │        │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  图例: [蓝色-前段] [橙色-焊接] [绿色-扣压] [紫色-装配包装]         │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 核心功能

#### 1. 拖拽排程
- **拖动调整**：拖动任务块改变时间
- **跨设备拖动**：将任务从一个设备拖到另一个设备（需权限验证）
- **拉伸调整**：拖动任务块边缘调整时长

#### 2. 点击操作
- **单击**：显示任务详情弹窗
- **双击**：进入编辑模式
- **右键菜单**：编辑/删除/复制/拆分任务

#### 3. 悬停提示
```
┌─────────────────────────────┐
│ 工单: WORK071590-001        │
│ 产品: F26-8108010HV         │
│ 工序: 焊接传感器座（自动）   │
│ 设备: 自动焊H一13           │
│ 时间: 08:30 - 12:00         │
│ 数量: 400件                 │
│ 人员: 卓明鸾                │
│ 进度: 100%                  │
└─────────────────────────────┘
```

#### 4. 班组权限锁定
```javascript
// 权限验证逻辑
function canSchedule(teamId, productCode, processCode) {
    // 1. 获取当前用户所属班组
    const userTeam = getCurrentUserTeam();
    
    // 2. 获取工序的报工权限
    const processPermission = getProcessPermission(processCode);
    // 如："焊接"、"前段,扣压"、"焊接,装配包装,扣压"
    
    // 3. 验证班组是否有权限
    const permissions = processPermission.split(',');
    return permissions.includes(userTeam.name);
}
```

### 3.4 冲突检测

#### 设备冲突
- 同一设备同一时间只能执行一个任务
- 冲突提示：红色边框闪烁

#### 人员冲突
- 同一人员同一时间只能在同一设备
- 冲突提示：黄色警告

#### 产能冲突
- 任务时长 × 设备产能 < 计划数量
- 冲突提示：橙色提醒

---

## 四、API接口设计

### 4.1 设备管理API
```
GET    /api/equipments                    # 获取设备列表
POST   /api/equipments                    # 创建设备
PUT    /api/equipments/<id>               # 更新设备
DELETE /api/equipments/<id>               # 删除设备
GET    /api/equipments/<id>/schedule      # 获取设备排程
```

### 4.2 甘特图数据API
```
GET /api/gantt/schedule?date=2026-05-28&team_id=1&equipment_id=2

Response:
{
    "date": "2026-05-28",
    "equipments": [
        {
            "id": 1,
            "equipment_code": "自动焊H一13",
            "equipment_name": "自动焊机13号",
            "team_id": 2,
            "team_name": "焊接",
            "tasks": [
                {
                    "id": 101,
                    "work_order_no": "WORK071590-001",
                    "product_code": "F26-8108010HV",
                    "process_code": "3W-1",
                    "process_name": "焊接传感器座（自动）",
                    "start_time": "08:30",
                    "end_time": "12:00",
                    "planned_quantity": 400,
                    "actual_quantity": 400,
                    "operator": "卓明鸾",
                    "status": "completed",
                    "color": "#ff9800"  // 焊接=橙色
                }
            ]
        }
    ]
}
```

### 4.3 拖拽更新API
```
PUT /api/gantt/schedule/<id>/move

Request:
{
    "equipment_id": 3,        // 新设备ID
    "start_time": "14:00",    // 新开始时间
    "end_time": "17:30"       // 新结束时间
}

Response:
{
    "success": true,
    "conflicts": []  // 如果有冲突，列出冲突信息
}
```

---

## 五、前端组件实现

### 5.1 技术选型
- **甘特图库**：使用原生Canvas或SVG实现（避免引入重量级库）
- **拖拽**：HTML5 Drag and Drop API
- **时间计算**：原生JavaScript Date对象

### 5.2 组件结构
```javascript
// GanttChart 主组件
class GanttChart {
    constructor(container, options) {
        this.date = options.date;
        this.teamId = options.teamId;
        this.equipments = [];      // 设备列表
        this.tasks = [];           // 任务列表
        this.hourStart = 8;        // 开始时间：8点
        this.hourEnd = 20;         // 结束时间：20点
        this.hourWidth = 100;      // 每小时像素宽度
        this.rowHeight = 60;       // 每行高度
    }
    
    render() {
        // 渲染时间轴
        this.renderTimeHeader();
        // 渲染设备行
        this.renderEquipmentRows();
        // 渲染任务块
        this.renderTasks();
        // 绑定事件
        this.bindEvents();
    }
    
    // 拖拽相关方法
    onTaskDragStart(e, task) {}
    onTaskDrag(e) {}
    onTaskDrop(e, targetEquipment, targetHour) {}
    
    // 冲突检测
    checkConflicts(task, equipmentId, startTime, endTime) {}
}
```

### 5.3 颜色方案（按班组）
```css
/* 班组颜色映射 */
.team-qianduan { background: #2196F3; }    /* 前段 - 蓝色 */
.team-hanjie   { background: #FF9800; }    /* 焊接 - 橙色 */
.team-kouya    { background: #4CAF50; }    /* 扣压 - 绿色 */
.team-zhuangpei{ background: #9C27B0; }    /* 装配包装 - 紫色 */

/* 任务状态 */
.status-planned   { opacity: 0.7; }
.status-running   { border: 2px solid #fff; box-shadow: 0 0 10px rgba(0,0,0,0.3); }
.status-completed { opacity: 0.5; background-image: linear-gradient(45deg, rgba(255,255,255,0.2) 25%, transparent 25%); }
```

---

## 六、数据初始化建议

### 6.1 从报工数据提取设备
```sql
-- 从报工表提取唯一的设备列表
INSERT INTO equipments (equipment_code, equipment_name, team_id)
SELECT DISTINCT 
    设备机台 as equipment_code,
    设备机台 as equipment_name,
    (SELECT id FROM teams WHERE name = '焊接') as team_id
FROM 报工表
WHERE 设备机台 IS NOT NULL;
```

### 6.2 从工序表提取工序-权限映射
```sql
-- 将工序的报工权限映射到班组
-- 工序.报工权限 = "焊接,装配包装,扣压" → 需要拆分到多个班组
```

---

## 七、实施步骤

### 阶段1：数据库准备（1天）
1. 创建设备表
2. 创建工序-设备关联表
3. 扩展现有排程表
4. 导入设备数据（从报工表提取）

### 阶段2：后端API开发（2天）
1. 设备管理CRUD API
2. 甘特图数据查询API
3. 拖拽更新API
4. 冲突检测逻辑

### 阶段3：前端甘特图组件（3天）
1. 基础甘特图渲染
2. 时间轴和设备行
3. 任务块渲染
4. 拖拽功能
5. 悬停提示

### 阶段4：集成与测试（2天）
1. 集成到排班页面
2. 班组权限验证
3. 数据联调
4. 性能优化

---

## 八、与现有系统的关联

### 8.1 数据流
```
MES报工数据 → 提取设备/工序 → 设备表/工序表
                      ↓
用户排程 → 甘特图可视化 → 排程表
                      ↓
实际报工 → 更新任务状态 → 进度追踪
```

### 8.2 权限控制
- 班组只能看到自己权限内的工序
- 班组只能调度自己管辖的设备
- 管理人员可以看到全部

---

## 九、详细模块设计

### 9.1 权限控制逻辑

#### 权限数据结构
从工序表提取的权限映射：
```
工序编号 → 报工权限（逗号分隔）
例如：
  "1A" → "前段"
  "3W-1" → "焊接"
  "5K-1" → "扣压"
  "装配多人装配" → "装配包装"
  "某工序" → "前段,扣压"  （多班组共享）
```

#### 权限验证函数
```python
def check_schedule_permission(user_team, process_code, equipment_id):
    """
    验证用户是否有权限在指定设备上调度指定工序
    
    返回:
        {
            "allowed": True/False,
            "reason": "原因说明",
            "suggestions": ["建议的替代方案"]
        }
    """
    # Step 1: 获取工序的报工权限
    process = get_process(process_code)
    permissions = process.报工权限.split(',')
    
    # Step 2: 验证班组权限
    if user_team not in permissions:
        return {
            "allowed": False,
            "reason": f"班组'{user_team}'无权操作工序'{process.工序名称}'",
            "suggestions": [f"该工序仅限：{', '.join(permissions)}"]
        }
    
    # Step 3: 验证设备归属
    equipment = get_equipment(equipment_id)
    if equipment.team_id != get_team_id(user_team):
        return {
            "allowed": False,
            "reason": f"设备'{equipment.equipment_code}'不属于班组'{user_team}'",
            "suggestions": [f"该设备属于：{equipment.team_name}"]
        }
    
    return {"allowed": True, "reason": "权限验证通过", "suggestions": []}
```

#### 权限矩阵表
| 班组 | 可操作工序类型 | 可调度设备 |
|------|----------------|------------|
| **前段** | 下料、外角、内角、镦头等 | DXw、DT、DJ系列设备 |
| **焊接** | 焊接类工序 | 自动焊H系列设备 |
| **扣压** | 扣压类工序 | 扣压机系列设备 |
| **装配包装** | 装配、包装、入库 | 装配线、包装线 |

---

### 9.2 冲突检测算法

#### 设备时间冲突检测
```python
def detect_equipment_conflict(equipment_id, date, start_time, end_time, exclude_task_id=None):
    """检测设备在指定时间段是否有冲突"""
    tasks = get_equipment_tasks(equipment_id, date)
    conflicts = []
    new_start = parse_time(start_time)
    new_end = parse_time(end_time)
    
    for task in tasks:
        if task.id == exclude_task_id:
            continue
        task_start = parse_time(task.start_time)
        task_end = parse_time(task.end_time)
        # 时间区间重叠检测
        if not (new_end <= task_start or new_start >= task_end):
            conflicts.append({
                "task_id": task.id,
                "work_order_no": task.work_order_no,
                "overlap_minutes": calculate_overlap(new_start, new_end, task_start, task_end)
            })
    
    return {"has_conflict": len(conflicts) > 0, "conflict_tasks": conflicts}
```

#### 人员冲突检测
```python
def detect_operator_conflict(operator_name, date, start_time, end_time, equipment_id, exclude_task_id=None):
    """检测操作员在指定时间段是否有冲突（同一人员同一时间只能在一个设备上工作）"""
    tasks = get_operator_tasks(operator_name, date)
    conflicts = []
    
    for task in tasks:
        if task.id == exclude_task_id or task.equipment_id == equipment_id:
            continue
        # 时间重叠检测...
    
    return {"has_conflict": len(conflicts) > 0, "conflict_tasks": conflicts}
```

#### 产能可行性检测
```python
def detect_capacity_issue(equipment_id, planned_quantity, start_time, end_time):
    """检测计划数量是否在设备产能范围内"""
    equipment = get_equipment(equipment_id)
    duration_hours = calculate_duration_hours(start_time, end_time)
    max_capacity = duration_hours * equipment.capacity_per_hour
    
    if planned_quantity > max_capacity:
        return {
            "has_issue": True,
            "issue_type": "产能不足",
            "shortage": planned_quantity - max_capacity,
            "suggestion": f"建议时长：{planned_quantity / equipment.capacity_per_hour:.1f}小时"
        }
    return {"has_issue": False}
```

#### 综合验证函数
```python
def validate_schedule(task_data):
    """综合验证排程数据"""
    results = {"valid": True, "errors": [], "warnings": []}
    
    # 1. 权限验证 → errors
    # 2. 设备冲突 → errors
    # 3. 人员冲突 → warnings
    # 4. 产能检测 → warnings
    
    return results
```

---

### 9.3 拖拽交互逻辑

#### 拖拽状态机
```
[空闲] ──mousedown──→ [选中]
                       │
                       ├── dragstart ──→ [拖拽中] ──drop──→ [验证] → [完成/回滚]
                       │                              │
                       │                              └── esc → [取消]
                       │
                       └── resize ──→ [调整大小] ──release──→ [验证]
```

#### 拖拽约束规则
| 操作 | 约束条件 | 违反处理 |
|------|----------|----------|
| **时间拖动** | 不能拖到已有任务的时间段 | 红色高亮，禁止放置 |
| **跨设备拖动** | 目标设备必须属于同一班组 | 灰色禁用目标设备行 |
| **拉伸调整** | 最小30分钟，最大12小时 | 边界吸附 |
| **已完成任务** | 不允许拖动 | 锁定状态 |

#### 前端拖拽处理
```javascript
class GanttDragHandler {
    onDragStart(e, task) {
        // 记录原始位置，显示拖拽提示，高亮可放置区域
    }
    
    onDrag(e) {
        // 计算新位置，实时预览，实时冲突检测
    }
    
    async onDrop(e) {
        // 验证 → 执行移动 或 显示错误并回滚
    }
}
```

---

### 9.4 数据同步机制

#### 同步流程
```
MES报工数据
    │
    ▼
[数据清洗] ── 统一设备名称、工序编码
    │
    ▼
[增量识别] ── 比对最后同步时间，识别新增报工
    │
    ├──→ 新设备 ──→ 插入设备表
    ├──→ 新工序 ──→ 插入工序表
    └──→ 新报工 ──→ 更新排程状态
                        │
                        ├── 排程任务状态 → running/completed
                        ├── 实际数量累加
                        └── 进度百分比更新
```

#### 设备名称清洗规则
```python
EQUIPMENT_NAME_MAPPING = {
    "自动焊H一13": "自动焊H-13",
    "DXw1一12": "DXW1-12",
    "DT4--9": "DT4-9",
    # ...
}

def normalize_equipment_name(raw_name):
    """标准化设备名称"""
    if raw_name in EQUIPMENT_NAME_MAPPING:
        return EQUIPMENT_NAME_MAPPING[raw_name]
    return raw_name.replace(" ", "").replace("一", "-").replace("--", "-")
```

#### 同步API
```python
@app.route('/api/sync/mes', methods=['POST'])
def sync_mes_data():
    """从MES同步报工数据（定时/手动/Webhook触发）"""
    last_sync = get_last_sync_time()
    new_reports = fetch_mes_reports(since=last_sync)
    
    for report in new_reports:
        equipment = sync_equipment(report.设备机台)
        process = sync_process(report.工序名称)
        task = find_matching_task(report.工单编号, report.工序名称)
        if task:
            update_task_progress(task, report.报工良品数, report.生产人员)
    
    return jsonify(sync_result)
```

---

## 十、注意事项

1. **设备命名**：报工表中的设备机台名称可能不统一，需要清洗数据
2. **时间精度**：报工数据精确到分钟，甘特图需要支持分钟级显示
3. **跨天任务**：支持跨天排程（如夜班）
4. **并发控制**：多人同时排程时的数据一致性
5. **权限隔离**：班组只能看到和操作自己权限内的工序和设备
6. **冲突优先级**：设备冲突 > 人员冲突 > 产能警告
