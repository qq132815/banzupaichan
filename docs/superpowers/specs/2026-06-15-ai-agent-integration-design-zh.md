# AI 智能体集成设计

日期：2026-06-15
项目：班组排产系统
状态：待用户评审

## 1. 目标

在现有 MES 班组排产系统中接入一个 AI 智能助手。该助手需要能够读取本地系统数据回答生产相关问题，并支持后续接入飞书、微信等机器人。

已确认采用双模型方案：

- Qwen3.5 对话模型：负责理解问题、推理、选择工具、生成最终中文回答。
- Embedding 向量模型：负责本地文档、规则、术语的语义检索。
- SQLite `data/production.db`：仍然是生产事实数据的唯一可信来源。

第一版只做只读能力。AI 不能修改排班、审批计划、删除数据、触发 MES 同步，也不能执行任意 SQL。

## 2. 范围

### MVP 包含内容

- 在系统内新增 AI 助手页面。
- 新增统一的后端 AI 对话 API。
- 接入 OpenAI 兼容的 Qwen3.5 chat completions API。
- 接入 OpenAI 兼容的 embeddings API。
- 基于本地项目文档和业务规则建立知识库索引。
- 增加一组只读生产数据查询工具。
- 每个数据工具都强制执行现有角色权限和班组权限。
- 记录 AI 对话日志，方便追溯。
- 系统内 AI 助手稳定后，再增加飞书和微信机器人 webhook 入口。
- 模型、机器人、功能开关等配置存入 `system_settings`。

### MVP 不包含内容

- 自动修改排班。
- 自动审批或驳回计划。
- 自动触发 MES 同步。
- 让模型生成并执行任意 SQL。
- 部署大型外部向量数据库。
- 多步骤自主任务编排。
- 模型微调。

## 3. 推荐架构

AI 功能应与当前较大的 `app.py` 保持隔离。建议新增独立工具模块，`app.py` 只负责暴露路由并转发到 AI 模块。

```text
系统内 AI 助手 / 飞书 / 微信
        ↓
Flask 路由层
        ↓
权限上下文构建
        ↓
AI Agent 服务
        ↓
Embedding 知识检索
        ↓
只读生产数据工具
        ↓
SQLite production.db
        ↓
Qwen3.5 生成最终回答
```

## 4. 建议新增文件

### 后端模块

- `utils/ai_client.py`
  OpenAI 兼容客户端，负责调用 `/v1/chat/completions` 和 `/v1/embeddings`。

- `utils/ai_agent.py`
  AI 编排核心，负责接收问题、检索知识、选择工具、调用 Qwen3.5、整理答案。

- `utils/ai_tools.py`
  只读业务工具层。所有数据库访问都必须参数化，并且执行权限过滤。

- `utils/ai_knowledge.py`
  负责文档发现、切片、embedding 生成、相似度搜索、知识库重建。

- `utils/ai_bots.py`
  负责飞书/微信签名校验、消息标准化、机器人回复格式化。

### 前端模板

- `templates/ai_assistant.html`
  系统内 AI 助手页面。

### 后续需要改动的现有文件

- `app.py`
  只新增路由，不放 AI 复杂逻辑。

- `templates/base.html`
  新增带 `data-perm="ai_assistant"` 的导航菜单。

- `utils/db.py`
  新增 AI 相关表的初始化逻辑。

- `data/production.db`
  通过迁移或初始化增加 AI 表和 `system_settings` 配置项。

## 5. 数据流

### 系统内网页对话

```text
登录用户提交问题
  ↓
POST /api/ai/chat
  ↓
从 session 构建权限上下文：user_id、role、team_id
  ↓
通过 embedding 相似度检索本地知识片段
  ↓
让 Qwen3.5 判断需要调用哪些允许的工具，或直接基于上下文回答
  ↓
执行被选择的只读工具，并强制应用权限过滤
  ↓
让 Qwen3.5 基于数据库结果和知识片段生成总结
  ↓
保存 AI 对话日志
  ↓
返回答案和可选来源引用
```

### 机器人对话

```text
飞书/微信 webhook 收到消息
  ↓
校验机器人签名或 token
  ↓
查找绑定的系统用户，或使用受限机器人角色
  ↓
调用同一个 AI Agent 服务
  ↓
返回文本回复给飞书/微信
```

## 6. 模型配置

配置建议存储在 `system_settings`，方便管理员在不同部署环境中调整，不需要改代码。

推荐配置项：

```text
ai_enabled
ai_base_url
ai_api_key
ai_chat_model
ai_embedding_model
ai_vector_store
ai_chroma_mode
ai_chroma_persist_dir
ai_chroma_host
ai_chroma_port
ai_chroma_collection
ai_request_timeout_seconds
ai_max_context_chunks
ai_max_tool_rows
ai_log_retention_days
ai_bot_feishu_enabled
ai_bot_feishu_secret
ai_bot_wechat_enabled
ai_bot_wechat_secret
```

预期模型接口：

```text
POST {ai_base_url}/chat/completions
POST {ai_base_url}/embeddings
```

当前假设 chat 模型和 embedding 模型都通过同一个 OpenAI 兼容服务访问。如果后续两类模型使用不同服务地址，可新增：

```text
ai_chat_base_url
ai_embedding_base_url
```

MVP 阶段向量数据库明确使用 Chroma。建议配置 `ai_vector_store=chroma`。默认推荐使用 Chroma Server 模式：`ai_chroma_mode=http`、`ai_chroma_host`、`ai_chroma_port`，因为 Windows/Python 3.12 可以直接使用轻量的 `chromadb-client` 包，不需要编译原生 HNSW 扩展。如果使用本地持久化 Chroma，则配置 `ai_chroma_mode=local` 和 `ai_chroma_persist_dir`，但需要安装完整 `chromadb` 包并具备本机 C++ 编译环境。知识片段建议存入独立 collection，例如 `production_ai_knowledge`。

## 7. 知识检索设计

Embedding 模型用于本地文档和规则检索，不用于回答生产数量、交期、完成率等事实数据。生产事实必须来自 SQLite 查询结果。

### 初始知识来源

- `AGENTS.md`
- `documentation.md`
- `GANTT_CHART_DESIGN.md`
- MES 同步相关说明
- 产品定义相关说明
- 图片导入/下载相关说明
- 排班规则、权限规则、工时规则、故障排查规则

### 文档切片策略

- Markdown 和文本文件优先按标题切分。
- 每个片段约 500 到 1000 个中文字符。
- 存储来源文件路径、标题、片段文本、内容哈希、更新时间。
- 只对发生变化的片段重新生成 embedding。

### 相似度搜索

Chroma 是第一版的主向量数据库。检索流程为：

```text
用户问题
  ↓
Embedding 模型生成查询向量
  ↓
Chroma 在 `production_ai_knowledge` collection 中做相似度查询
  ↓
返回最相关的文档片段和来源 metadata
  ↓
Qwen3.5 把这些片段作为上下文生成回答
```

SQLite 只保留文档和片段的元数据，方便追溯；Chroma 负责保存向量、可检索片段内容和来源 metadata。如果 Chroma 暂时不可用，AI 助手仍可继续回答数据库事实类问题，但需要明确提示“文档检索暂不可用”。

降级或未来替代方案：

- SQLite `embedding_json` 加 Python cosine similarity 只作为应急降级方案。
- FAISS：轻量本地向量索引。
- Milvus 或 pgvector：更大规模部署。

## 8. 只读工具设计

模型不能执行自由 SQL，只能请求调用预定义工具。每个工具负责校验参数、使用参数化 SQL、应用角色/班组过滤，并限制返回行数。

第一版工具建议：

- `get_work_order_status(order_no=None, product_code=None, date_from=None, date_to=None)`
- `get_schedule_summary(date=None, team_id=None, equipment_id=None)`
- `get_equipment_load(date=None, team_id=None, equipment_code=None)`
- `get_active_alerts(level=None, team_id=None)`
- `get_material_alerts(status=None, team_id=None)`
- `get_work_report_summary(date_from=None, date_to=None, team_id=None)`
- `get_shipping_plan(date_from=None, date_to=None, product_code=None)`
- `get_production_requirements(date_from=None, date_to=None, team_id=None)`
- `get_team_stats(period="daily", date=None, team_id=None)`

工具结果行数由 `ai_max_tool_rows` 限制，默认 50 行。

## 9. 权限规则

权限必须在工具层强制执行，不能只依赖提示词约束。

### 系统内用户权限

- `admin`：可查询全部生产数据和 AI 日志。
- `planner`：可查询计划相关的全局生产数据。
- `team`：只能查询 `session.team_id` 对应班组的数据。

### 机器人权限

- 未绑定机器人用户只允许访问受限的公共汇总信息。
- 已绑定机器人用户继承对应系统账号的角色和班组。
- 机器人接口必须先完成平台签名校验，再处理消息。

### 敏感数据限制

AI 助手不得暴露：

- 密码哈希或登录凭据。
- API Key 和机器人密钥。
- `system_settings` 中的密钥类原始值。
- 未经过滤的用户账号数据。
- 任意数据库结构转储。

## 10. 数据库新增内容

推荐新增表：

```sql
CREATE TABLE IF NOT EXISTS ai_chat_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    role TEXT,
    team_id INTEGER,
    channel TEXT,
    question TEXT,
    answer TEXT,
    tools_used TEXT,
    knowledge_sources TEXT,
    model TEXT,
    success INTEGER DEFAULT 1,
    error TEXT,
    latency_ms INTEGER,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS ai_knowledge_docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL UNIQUE,
    title TEXT,
    content_hash TEXT,
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS ai_knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    chroma_collection TEXT,
    chroma_id TEXT,
    content_hash TEXT,
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (doc_id) REFERENCES ai_knowledge_docs(id)
);

CREATE TABLE IF NOT EXISTS ai_bot_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    system_user_id INTEGER NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(platform, external_user_id)
);
```

建议索引：

```sql
CREATE INDEX IF NOT EXISTS idx_ai_logs_created ON ai_chat_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_ai_logs_user ON ai_chat_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_chunks_doc ON ai_knowledge_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_ai_bot_bindings_platform_user ON ai_bot_bindings(platform, external_user_id);
```

## 11. 路由设计

推荐新增路由：

```text
GET  /ai-assistant
POST /api/ai/chat
GET  /api/ai/logs
POST /api/ai/knowledge/rebuild
GET  /api/ai/settings
POST /api/ai/settings
POST /api/bot/feishu
POST /api/bot/wechat
```

路由权限：

- `/ai-assistant`：`@login_required`
- `/api/ai/chat`：`@login_required`
- `/api/ai/logs`：`@login_required`，并按 admin/planner 权限过滤
- `/api/ai/knowledge/rebuild`：`@login_required` + `@admin_required`
- `/api/ai/settings`：读取需登录，写入需 `@admin_required`
- 机器人 webhook：不使用 session 登录，但必须做平台签名校验和用户绑定查询

## 12. 导航与权限同步

在 `templates/base.html` 新增导航菜单：

```html
<li data-perm="ai_assistant"><a href="/ai-assistant" class="nav-link"><span class="icon">AI</span><span>AI助手</span></a></li>
```

同时在 `system_settings` 中新增 `perm_ai_assistant`，用于控制不同角色是否可见。推荐默认：

```text
admin: 可见
planner: 可见
team: 可见
```

这必须遵守项目现有规则：新增导航菜单项时，必须同步更新 `templates/base.html` 和 `system_settings` 权限配置。

## 13. 错误处理

AI 助手需要给出可理解的错误提示，同时不能暴露内部敏感信息。

需要处理的情况：

- AI 功能未启用。
- 模型配置缺失。
- Qwen3.5 请求超时。
- Embedding 请求超时。
- 知识库索引为空或未构建。
- 工具参数校验失败。
- 数据库被锁定。
- 机器人签名校验失败。
- 机器人用户未绑定系统账号。

降级策略：

- 如果 embedding 检索失败，仍可继续使用数据库工具回答，并提示“文档检索暂不可用”。
- 如果 Qwen3.5 调用失败，返回友好的失败提示并记录日志。
- 如果某个工具失败，不执行危险重试；由于所有工具都是只读，可以记录错误并在其他工具可用时继续回答。

## 14. 测试计划

### 单元测试或脚本检查

- 从 `system_settings` 读取 AI 配置。
- Chat 和 embedding 客户端请求格式。
- 文档切片和变更检测。
- Cosine similarity 排序。
- 每个只读工具在 planner/admin/team 权限上下文下的结果。
- 机器人签名校验。

### 手工验证

- 班组用户只能查询自己班组的数据。
- 计划员和管理员可以查询全局数据。
- 模型不能获取密码、API Key、系统密钥。
- 模型不能执行任意 SQL。
- 常见问题返回的是数据库事实，而不是模型猜测。
- 同一绑定用户在机器人和系统页面中获得一致的回答。

### 验收问题示例

- `今天有哪些生产预警？`
- `WG7-1 今天排了哪些任务？`
- `订单 X 的完成进度怎么样？`
- `本周哪个班组压力最大？`
- `加班工时怎么算？`
- `MES同步失败 Failed to fetch 怎么处理？`

## 15. 实施阶段

### 第一阶段：系统内 AI 助手

- 新增数据库表和配置项。
- 新增模型客户端。
- 新增知识库索引与检索。
- 新增只读数据工具。
- 新增 `/api/ai/chat`。
- 新增 `ai_assistant.html` 页面和菜单权限。

### 第二阶段：机器人入口

- 新增飞书 webhook。
- 新增微信 webhook。
- 新增机器人用户绑定表和绑定管理流程。
- 复用同一个 AI Agent 服务。

### 第三阶段：主动推送

- 每日风险汇总推送。
- 备料提醒推送。
- 设备负荷预警推送。
- 计划完成率汇总推送。

### 第四阶段：排产建议

- AI 只提供建议。
- 用户确认后，手动跳转到排班页面调整。
- 在单独设计获得批准前，不允许 AI 自动写入排班。

## 16. 部署前需要确认的问题

实施前需要确认以下值：

- Qwen3.5 的 `ai_base_url`。
- Qwen3.5 的 chat model 名称。
- Embedding model 名称。
- Chat 和 embedding 是否共用同一个 OpenAI 兼容 base URL。
- 飞书机器人类型和签名密钥。
- 微信机器人类型：企业微信应用机器人、群机器人 webhook，或其他接入方式。

## 17. 评审门槛

这份设计文档已准备好进行用户评审。在用户确认 spec 可接受，或提出需要修改的内容之前，不应开始实现。
