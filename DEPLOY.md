# EverMemOS — 部署与接入指南

## 架构概览

```
┌──────────────────────────────────────────────────────────┐
│  接入层                                                   │
│  Claude Code (stdio MCP) ──┐                             │
│  OpenClaw / REST API  ─────┤──► EverMemOS MCP Server     │
│  Cursor / Windsurf   ──────┘   (port 3456, HTTP MCP)     │
│                                        │                  │
│                                        ▼                  │
│                              EverMemOS App               │
│                              (port 1995, FastAPI)        │
│                                        │                  │
│  ┌─────────────┬──────────┬────────────┼──────────┐      │
│  │  MongoDB    │  Milvus  │   Elastic  │  Redis   │      │
│  │  (文档存储) │ (向量搜索)│ (全文检索) │  (缓存)  │      │
│  └─────────────┴──────────┴────────────┴──────────┘      │
└──────────────────────────────────────────────────────────┘
```

---

## 一、本地开发部署

### 1. 准备配置文件
```bash
cd /e/project/EverMemOS
cp env.template .env
# 编辑 .env，填写 LLM API Key 等必要配置
```

### 2. 启动全部基础设施（数据库）
```bash
docker compose up -d mongodb elasticsearch milvus-etcd milvus-minio milvus-standalone redis
```

### 3. 启动 EverMemOS 主应用（Python 本地运行，便于调试）
```bash
uv sync
uv run python src/run.py
# 验证：curl http://localhost:1995/health
```

### 4. 安装 MCP Server 依赖并启动
```bash
pip install -r mcp_server/requirements.txt
# 或用 uv:
uv pip install -r mcp_server/requirements.txt
```

---

## 二、全容器化部署（云服务器 / VPS）

```bash
# 一键启动所有服务（含主应用 + MCP server）
docker compose up -d

# 检查状态
docker compose ps

# 验证
curl http://localhost:1995/health     # EverMemOS API
curl http://localhost:3456/health     # MCP Server
```

> **内存建议**：云服务器至少 **4GB RAM**（Elasticsearch 占 1G，Milvus 约 1-2G）

---

## 三、Claude Code 接入（stdio MCP）

**方式 A：直接在本机运行 MCP server（推荐）**

在 Claude Code 配置文件（`~/.claude/claude_desktop_config.json` 或项目 `.mcp.json`）中添加：

```json
{
  "mcpServers": {
    "evermemos": {
      "command": "python",
      "args": ["E:/project/EverMemOS/mcp_server/server.py", "--transport", "stdio"],
      "env": {
        "EVERMEMOS_BASE_URL": "http://localhost:1995",
        "EVERMEMOS_USER_ID": "your_name",
        "EVERMEMOS_GROUP_ID": "claude_code"
      }
    }
  }
}
```

**方式 B：连接云端 MCP server（HTTP）**

```json
{
  "mcpServers": {
    "evermemos": {
      "url": "http://<your-server-ip>:3456/mcp",
      "transport": "http"
    }
  }
}
```

### 可用 MCP 工具

| 工具 | 说明 |
|------|------|
| `memorize` | 存储对话内容到长期记忆 |
| `search_memory` | 语义/混合搜索记忆（keyword/vector/hybrid/agentic） |
| `fetch_memories` | 按类型批量获取记忆 |
| `get_user_profile` | 获取用户画像（偏好、习惯、关键事实） |
| `health_check` | 检查后端是否正常 |

---

## 四、OpenClaw / OpenAI 兼容接口

EverMemOS 暴露标准 REST API，可通过 Function Calling 方式接入任何兼容 OpenAI 的客户端：

```
POST http://localhost:1995/api/v1/memories        # 存储记忆
GET  http://localhost:1995/api/v1/memories/search # 搜索记忆
GET  http://localhost:1995/api/v1/memories        # 获取记忆列表
```

详见：`docs/api_docs/memory_api.md`

---

## 五、.env 关键配置速查

```bash
# LLM（用 OpenRouter 可一个 key 调多模型）
LLM_PROVIDER=openai
LLM_MODEL=x-ai/grok-4-fast
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-xxxx

# 向量化（推荐 DeepInfra，免部署）
VECTORIZE_PROVIDER=deepinfra
VECTORIZE_API_KEY=your_deepinfra_key
VECTORIZE_BASE_URL=https://api.deepinfra.com/v1/openai
VECTORIZE_MODEL=Qwen/Qwen3-Embedding-4B

# 重排序（同上，用 DeepInfra）
RERANK_PROVIDER=deepinfra
RERANK_API_KEY=your_deepinfra_key
RERANK_BASE_URL=https://api.deepinfra.com/v1/inference
RERANK_MODEL=Qwen/Qwen3-Reranker-4B

# MCP Server 标识
EVERMEMOS_USER_ID=your_name
EVERMEMOS_GROUP_ID=default_group
```
