# 3D 车间监控工作台实施计划 (Implementation Plan)

## 1. 数据库层 (Database Layer) - [Sync Checklist]
我们需要在 `equipments` 表中增加 3D 坐标和模型信息。
- **字段变更**:
  - `pos_x`, `pos_y`, `pos_z`: FLOAT (3D 空间坐标)
  - `rotation_z`: FLOAT (设备朝向角度)
  - `model_type`: TEXT (模型类型，如 'cnc', 'press', 'robot')
- **操作**: 
  - 更新 `utils/db.py` 中的建表语句。
  - 执行 `ALTER TABLE` 兼容旧数据。

## 2. 后端层 (Backend Layer) - [Sync Checklist]
新增 API 接口用于 3D 渲染和实时数据获取。
- **接口**: `GET /api/workshop/3d-status`
- **返回数据**:
  - 设备基础信息 (Code, Name)
  - 实时状态 (Running/Idle/Down) - 模拟或关联报工数据
  - 关联工单信息 (Product Name, Progress)
- **权限**: 使用 `@login_required`。

## 3. 前端层 (Frontend Layer) - [Sync Checklist]
替换 `index.html` (工作台) 为 3D 场景。
- **技术**: Three.js (引入 CDN)。
- **场景**:
  - 地板网格 (Grid)
  - 设备模型 (使用几何体组合，根据 `model_type` 渲染不同形状)
  - 状态灯光 (Green/Yellow/Red)
- **交互**:
  - 鼠标悬停: 显示 CSS2DRenderer 标签 (Tooltip)。
  - 点击: 弹出详情弹窗。
- **动画**: 
  - 运行中的设备添加“呼吸灯”或“旋转”动画。

## 4. 实施步骤 (Steps)
1. **Step 1**: 修改数据库，增加 3D 坐标字段。
2. **Step 2**: 编写后端 API 获取 3D 数据。
3. **Step 3**: 搭建 Three.js 基础场景。
4. **Step 4**: 实现设备渲染与状态映射。
5. **Step 5**: 实现交互（悬停提示、点击详情）。
