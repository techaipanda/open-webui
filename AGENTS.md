# AGENTS.md

此文件为 Codex (Codex.ai/code) 在本代码库中工作时提供指导。

## 回答原则

**每当你回答问题时，除了给出解决方案，还必须提供证据和来源：**

- 引用的官方文档链接（如 https://docs.openwebui.com）
- 代码中的具体位置（文件路径:行号）
- 知识库或笔记中的原文摘录
- 第三方资源的链接

**目的**：让你不仅知道"怎么做"，更理解"为什么这么做"。

---

## 项目概述

Open WebUI 是一个自托管 AI 平台（类似于 ChatGPT），支持 Ollama、OpenAI 兼容 API、RAG、语音/视频通话，以及通过插件扩展功能。项目为 monorepo 结构，包含 Python/FastAPI 后端和 SvelteKit/Svelte 5 前端。

## 架构

```
├── backend/open_webui/     # Python FastAPI 应用
│   ├── routers/             # API 端点模块（auths, chats, models 等）
│   ├── models/              # SQLAlchemy ORM 模型
│   ├── storage/             # 文件/存储后端
│   ├── retrieval/          # RAG 文档加载器
│   ├── tools/              # Python 函数调用工具
│   ├── socket/             # WebSocket 处理
│   ├── tasks/             # 后台任务处理
│   ├── internal/          # 内部迁移和工具
│   ├── migrations/         # Alembic 数据库迁移
│   └── main.py             # FastAPI 应用入口（约 116KB）
├── src/                    # SvelteKit 前端（TypeScript/Svelte 5）
│   ├── lib/
│   │   ├── apis/           # API 客户端模块（index.ts + 子目录）
│   │   ├── components/     # Svelte 组件（admin, chat, common 等）
│   │   ├── stores/         # Svelte 状态管理
│   │   └── utils/          # 工具函数
│   └── app.html            # HTML 入口
├── test/                   # Playwright E2E 测试
├── cypress/                # Cypress 集成测试
├── package.json            # 前端 npm 脚本和依赖
├── pyproject.toml         # Python 项目配置（hatch, ruff, pytest）
└── docker-compose.yaml     # Docker 部署配置
```

### 后端结构

- **`main.py`**：FastAPI 应用，包含中间件配置、CORS、会话、WebSocket 路由和所有 API 路由注册（约 116KB）
- **`routers/`**：按域组织的 API 端点（auths、chats、models、users、files、retrieval 等）
- **`models/`**：所有实体的 SQLAlchemy ORM 模型（users、chats、messages、files、knowledge 等）
- **`config.py`**：中央配置（约 144KB），处理所有环境变量和应用设置
- **`internal/migrations/`**：初始化架构的引导迁移

### 前端结构

- SvelteKit + Svelte 5 + TypeScript + Tailwind CSS 4
- Svelte stores 用于客户端状态管理
- `src/lib/apis/` 下的 API 客户端与后端路由结构对应
- 组件按域（admin、chat、common）和 admin 设置页面组织

## 常用命令

### 前端开发
```bash
npm run dev              # 启动开发服务器（http://localhost:5173）
npm run dev:5050        # 在 5050 端口启动开发服务器
npm run build            # 生产环境构建
npm run check            # Svelte 类型检查（tsconfig）
npm run check:watch      # 监听模式类型检查
npm run lint:frontend    # ESLint（带 --fix）
npm run lint:types       # svelte-check TypeScript 检查
npm run test:frontend    # Vitest 单元测试（--passWithNoTests）
npm run format           # Prettier 格式化所有文件
```

### 后端开发
```bash
ruff format .            # 格式化 Python 代码
ruff check .             # Lint Python 代码
pylint backend/          # 额外 lint 检查
pytest                   # 运行后端测试
pytest -x                # 首次失败时停止
pytest -k "test_name"    # 运行特定测试
```

### 官方推荐开发方式（双终端分离运行）

这是官方文档推荐的开发方式，前后端分离，各司其职：

**终端 1 - 前端开发服务器**
```bash
cp -RPp .env.example .env  # 首次只需执行一次
npm install
npm run dev                # http://localhost:5173（带热更新）
```

**终端 2 - 后端开发服务器**
```bash
cd backend
python -m venv venv
venv\Scripts\activate     # Windows
pip install -r requirements.txt -U
./dev.sh                  # 或 uvicorn open_webui.main:app --port 8080 --reload
```

> **来源**：[Open WebUI 官方开发文档](https://docs.openwebui.com/getting-started/advanced-topics/development)

### Docker
```bash
docker compose up -d             # 启动所有服务
docker compose up -d --build      # 重新构建并启动
docker compose stop               # 停止服务
```

### i18n
```bash
npm run i18n:parse    # 提取 i18n 字符串并重新生成语言文件
```

## 关键配置

- **环境变量**：参见 `backend/open_webui/env.py`（约 42KB）了解所有配置项，`backend/open_webui/config.py`（约 144KB）了解运行时行为
- **数据库**：默认 SQLite，支持通过环境变量配置 PostgreSQL
- **会话存储**：使用 starsessions 的 Redis 后端会话
- **向量数据库**：支持 ChromaDB、PGVector、Qdrant、Milvus、Elasticsearch、OpenSearch、Pinecone、S3Vector、Oracle 23ai

## 后端入口

FastAPI 应用在 `backend/open_webui/__init__.py` 中导出 `app`。`pyproject.toml` 中的入口点是 `open-webui = "open_webui:app"`。实际应用创建在 `main.py` 中，通过 `create_app()` 函数和 `app = FastAPI()` 实现，包含大量中间件配置：CORS、会话（Redis）、压缩、审计日志和 WebSocket 支持。

## 前端构建

基于 Vite，使用 SvelteKit adapter-auto。`open_webui/frontend` 目录通过 hatch 构建配置打包到 wheel 中。构建前需运行 `npm run pyodide:fetch` 准备 Pyodide（WebAssembly Python）运行时。

## 测试

- **前端单元测试**：Vitest
- **集成测试**：pytest（后端），支持异步
- **E2E 测试**：Playwright（docker-compose.playwright.yaml）