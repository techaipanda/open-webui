# Open WebUI 👋

![GitHub stars](https://img.shields.io/github/stars/open-webui/open-webui?style=social)
![GitHub forks](https://img.shields.io/github/forks/open-webui/open-webui?style=social)
![GitHub watchers](https://img.shields.io/github/watchers/open-webui/open-webui?style=social)
![GitHub repo size](https://img.shields.io/github/repo-size/open-webui/open-webui)
![GitHub language count](https://img.shields.io/github/languages/count/open-webui/open-webui)
![GitHub top language](https://img.shields.io/github/languages/top/open-webui/open-webui)
![GitHub last commit](https://img.shields.io/github/last-commit/open-webui/open-webui?color=red)
[![Discord](https://img.shields.io/badge/Discord-Open_WebUI-blue?logo=discord&logoColor=white)](https://discord.gg/5rJgQTnV4s)
[![](https://img.shields.io/static/v1?label=Sponsor&message=%E2%9D%A4&logo=GitHub&color=%23fe8e86)](https://github.com/sponsors/tjbck)

![Open WebUI Banner](./banner.png)

**Open WebUI 是一个功能丰富、便于扩展、用户友好的自托管 AI 平台，设计为完全离线运行。** 它支持多种 LLM 运行时，如 **Ollama** 和 **OpenAI 兼容 API**，并内置 **RAG 推理引擎**，是一个 **强大的 AI 部署解决方案**。

热衷于开源 AI？[加入我们的团队 →](https://careers.openwebui.com/)

![Open WebUI Demo](./demo.png)

> [!TIP]
> **想要了解 [企业版](https://docs.openwebui.com/enterprise)？** – **[立即联系我们的销售团队！](https://docs.openwebui.com/enterprise)**
>
> 获得 **增强功能**，包括 **自定义主题和品牌**、**服务级别协议（SLA）支持**、**长期支持（LTS）版本** 以及 **更多**！

欲了解更多详情，请查看我们的 [Open WebUI 文档](https://docs.openwebui.com/)。

## Open WebUI 主要功能 ⭐

- 🚀 **轻松设置**：通过 Docker 或 Kubernetes（kubectl、kustomize 或 helm）无缝安装，支持 `:ollama` 和 `:cuda` 标签镜像，让安装无忧。

- 🤝 **Ollama/OpenAI API 集成**：轻松集成 OpenAI 兼容 API，与 Ollama 并行使用。通过自定义 OpenAI API URL 链接 **LMStudio、GroqCloud、Mistral、OpenRouter** 等。

- 🛡️ **精细权限和用户组**：管理员可创建详细的用户角色和权限，确保安全的环境。这种粒度不仅增强安全性，还允许定制用户体验，培养用户的所有权和责任感。

- 📱 **响应式设计**：在桌面 PC、笔记本电脑和移动设备上享受无缝体验。

- 📱 **移动端渐进式 Web 应用（PWA）**：通过我们的 PWA 在移动设备上获得原生应用体验，在 localhost 上提供离线访问和流畅的用户界面。

- ✒️🔢 **完整 Markdown 和 LaTeX 支持**：通过全面的 Markdown 和 LaTeX 功能提升您的 LLM 体验，实现丰富的交互。

- 🎤📹 **免提语音/视频通话**：通过多个语音转文字提供商（本地 Whisper、OpenAI、Deepgram、Azure）和文字转语音引擎（Azure、ElevenLabs、OpenAI、Transformers、WebAPI）实现无缝免提语音和视频通话功能，打造动态和交互式聊天环境。

- 🛠️ **模型构建器**：通过 Web UI 轻松创建 Ollama 模型。创建和添加自定义角色/代理，定制聊天元素，并通过 [Open WebUI 社区](https://openwebui.com/) 集成轻松导入模型。

- 🐍 **原生 Python 函数调用工具**：通过工具工作区中内置的代码编辑器支持增强您的 LLM。只需添加纯 Python 函数即可自带函数（BYOF），实现与 LLM 的无缝集成。

- 💾 **持久化工件存储**：内置键值存储 API 用于工件，支持日志、追踪器、排行榜和协作工具，跨会话具有个人和共享数据范围。

- 📚 **本地 RAG 集成**：通过使用 9 个向量数据库和多个内容提取引擎（Tika、Docling、Document Intelligence、Mistral OCR、PaddleOCR-vl、外部加载器）的开创性检索增强生成（RAG）支持，进入聊天交互的未来。将文档直接加载到聊天中或添加到文档库，使用 `#` 命令后跟查询即可轻松访问。

- 🔍 **RAG 网络搜索**：使用 15+ 个提供商执行网络搜索，包括 `SearXNG`、`Google PSE`、`Brave Search`、`Kagi`、`Mojeek`、`Tavily`、`Perplexity`、`serpstack`、`serper`、`Serply`、`DuckDuckGo`、`SearchApi`、`SerpApi`、`Bing`、`Jina`、`Exa`、`Sougou`、`Azure AI Search` 和 `Ollama Cloud`，直接将结果注入您的聊天体验。

- 🌐 **网页浏览功能**：使用 `#` 命令后跟 URL 将网站无缝整合到您的聊天体验中。此功能允许您直接将网页内容合并到对话中，增强交互的丰富性和深度。

- 🎨 **图像生成与编辑集成**：使用多个引擎创建和编辑图像，包括 OpenAI 的 DALL-E、Gemini、ComfyUI（本地）和 AUTOMATIC1111（本地），支持生成和基于提示的编辑工作流。

- ⚙️ **多模型对话**：轻松同时与多个模型交互，利用它们各自的优势获得最佳响应。通过在并行中利用多样化的模型集来增强您的体验。

- 🔐 **基于角色的访问控制（RBAC）**：通过限制性权限确保安全访问；只有授权人员可以访问您的 Ollama，管理员保留专属的模型创建/拉取权限。

- 🗄️ **灵活的数据库和存储选项**：从 SQLite（可选加密）、PostgreSQL 中选择，或配置云存储后端（S3、Google Cloud Storage、Azure Blob Storage）以实现可扩展部署。

- 🔍 **高级向量数据库支持**：从 9 个向量数据库选项中选择，包括 ChromaDB、PGVector、Qdrant、Milvus、Elasticsearch、OpenSearch、Pinecone、S3Vector 和 Oracle 23ai，以实现最佳的 RAG 性能。

- 🔐 **企业级认证**：完整支持 LDAP/Active Directory 集成、SCIM 2.0 自动配置，以及通过可信头的 SSO 以及 OAuth 提供商。通过 SCIM 2.0 协议实现企业级用户和组配置，与 Okta、Azure AD 和 Google Workspace 等身份提供商无缝集成，实现自动用户生命周期管理。

- ☁️ **云原生集成**：原生支持 Google Drive 和 OneDrive/SharePoint 文件选择，实现从企业云存储无缝导入文档。

- 📊 **生产可观测性**：内置 OpenTelemetry 支持跟踪、指标和日志，通过您现有的可观测性堆栈实现全面监控。

- ⚖️ **水平扩展性**：基于 Redis 的会话管理和 WebSocket 支持，适用于负载均衡器后面的多工作进程和多节点部署。

- 🌐🌍 **多语言支持**：通过我们的国际化（i18n）支持以您首选的语言体验 Open WebUI。加入我们扩展支持语言！ 我们正在积极寻求贡献者！

- 🧩 **Pipelines、Open WebUI 插件支持**：使用 [Pipelines 插件框架](https://github.com/open-webui/pipelines) 将自定义逻辑和 Python 库无缝集成到 Open WebUI。启动您的 Pipelines 实例，将 OpenAI URL 设置为 Pipelines URL，并探索无限可能。[示例](https://github.com/open-webui/pipelines/tree/main/examples)包括 **函数调用**、用户 **速率限制** 以控制访问、**使用 Langfuse 等工具进行使用监控**、**使用 LibreTranslate 进行实时翻译** 以支持多语言、**有毒消息过滤** 等等。

- 🌟 **持续更新**：我们致力于通过定期更新、修复和新功能来改进 Open WebUI。

想要了解更多关于 Open WebUI 功能的信息？查看我们的 [Open WebUI 文档](https://docs.openwebui.com/features) 获取全面概述！

---

我们对赞助商的慷慨支持深表感谢。他们的贡献帮助我们维护和改进项目，确保我们能够继续为社区提供优质工作。谢谢你们！

## 如何安装 🚀

### 通过 Python pip 安装 🐍

Open WebUI 可以使用 pip（Python 包安装器）安装。在继续之前，请确保您使用的是 **Python 3.11** 以避免兼容性问题。

1. **安装 Open WebUI**：
   打开终端并运行以下命令安装 Open WebUI：

   ```bash
   uv pip install open-webui
   ```

2. **运行 Open WebUI**：
   安装后，您可以通过执行以下命令来启动 Open WebUI：

   ```bash
   open-webui serve
   ```

这将启动 Open WebUI 服务器，您可以通过 [http://localhost:8080](http://localhost:8080) 访问它。

### 使用 Docker 快速开始 🐳

> [!NOTE]
> 请注意，对于某些 Docker 环境，可能需要额外的配置。如果您遇到任何连接问题，我们详细的 [Open WebUI 文档](https://docs.openwebui.com/) 可以提供帮助。

> [!WARNING]
> 使用 Docker 安装 Open WebUI 时，请确保在 Docker 命令中包含 `-v open-webui:/app/backend/data`。此步骤至关重要，因为您的数据库需要正确挂载以防止任何数据丢失。

> [!TIP]
> 如果您希望使用包含的 Ollama 或 CUDA 加速来运行 Open WebUI，我们建议使用带有 `:cuda` 或 `:ollama` 标签的官方镜像。要启用 CUDA，您必须在 Linux/WSL 系统上安装 [Nvidia CUDA 容器工具包](https://docs.nvidia.com/dgx/nvidia-container-runtime-upgrade/)。

### 默认配置安装

- **如果 Ollama 在您的计算机上**，请使用此命令：

  ```bash
  docker run -d -p 3000:8080 --add-host=host.docker.internal:host-gateway -v open-webui:/app/backend/data --name open-webui --restart always ghcr.io/open-webui/open-webui:main
  ```

- **如果 Ollama 在不同的服务器上**，请使用此命令：

  要连接到另一个服务器上的 Ollama，请将 `OLLAMA_BASE_URL` 更改为服务器的 URL：

  ```bash
  docker run -d -p 3000:8080 -e OLLAMA_BASE_URL=https://example.com -v open-webui:/app/backend/data --name open-webui --restart always ghcr.io/open-webui/open-webui:main
  ```

- **使用 Nvidia GPU 支持运行 Open WebUI**，请使用此命令：

  ```bash
  docker run -d -p 3000:8080 --gpus all --add-host=host.docker.internal:host-gateway -v open-webui:/app/backend/data --name open-webui --restart always ghcr.io/open-webui/open-webui:cuda
  ```

### 仅使用 OpenAI API 的安装

- **如果您仅使用 OpenAI API**，请使用此命令：

  ```bash
  docker run -d -p 3000:8080 -e OPENAI_API_KEY=your_secret_key -v open-webui:/app/backend/data --name open-webui --restart always ghcr.io/open-webui/open-webui:main
  ```

### 安装包含捆绑 Ollama 的 Open WebUI

此安装方法使用将 Open WebUI 与 Ollama 捆绑在一起的单个容器镜像，允许通过单个命令简化设置。根据您的硬件配置选择适当的命令：

- **GPU 支持**：
  通过运行以下命令利用 GPU 资源：

  ```bash
  docker run -d -p 3000:8080 --gpus=all -v ollama:/root/.ollama -v open-webui:/app/backend/data --name open-webui --restart always ghcr.io/open-webui/open-webui:ollama
  ```

- **仅 CPU**：
  如果您不使用 GPU，请改用此命令：

  ```bash
  docker run -d -p 3000:8080 -v ollama:/root/.ollama -v open-webui:/app/backend/data --name open-webui --restart always ghcr.io/open-webui/open-webui:ollama
  ```

这两个命令都可以方便地安装 Open WebUI 和 Ollama，确保您可以快速启动和运行。😄

安装后，您可以通过 [http://localhost:3000](http://localhost:3000) 访问 Open WebUI。

### 其他安装方法

我们提供多种安装替代方案，包括非 Docker 本地安装方法、Docker Compose、Kustomize 和 Helm。访问我们的 [Open WebUI 文档](https://docs.openwebui.com/getting-started/) 或加入我们的 [Discord 社区](https://discord.gg/5rJgQTnV4s) 获取全面指导。

### 故障排除

遇到连接问题？我们的 [Open WebUI 文档](https://docs.openwebui.com/troubleshooting/) 已为您准备好帮助。如需进一步帮助并加入我们充满活力的社区，请访问 [Open WebUI Discord](https://discord.gg/5rJgQTnV4s)。

#### Open WebUI：服务器连接错误

如果您遇到连接问题，通常是因为 WebUI docker 容器无法在容器内的 127.0.0.1:11434（host.docker.internal:11434）访问 Ollama 服务器。使用 docker 命令中的 `--network=host` 标志来解决此问题。请注意，端口从 3000 更改为 8080，结果链接为：`http://localhost:8080`。

**示例 Docker 命令**：

```bash
docker run -d --network=host -v open-webui:/app/backend/data -e OLLAMA_BASE_URL=http://127.0.0.1:11434 --name open-webui --restart always ghcr.io/open-webui/open-webui:main
```

### 保持 Docker 安装最新

访问我们的 [Open WebUI 文档](https://docs.openwebui.com/getting-started/updating) 查看我们的更新指南。

### 使用 Dev 分支 🌙

> [!WARNING]
> `:dev` 分支包含最新的不稳定功能更改。使用它需要您自担风险，因为它可能存在错误或不完整的功能。

如果您想尝试最新的前沿功能并且可以接受偶尔的不稳定性，您可以使用 `:dev` 标签，如下所示：

```bash
docker run -d -p 3000:8080 -v open-webui:/app/backend/data --name open-webui --add-host=host.docker.internal:host-gateway --restart always ghcr.io/open-webui/open-webui:dev
```

### 离线模式

如果您在离线环境中运行 Open WebUI，您可以设置 `HF_HUB_OFFLINE` 环境变量为 `1` 以防止尝试从互联网下载模型。

```bash
export HF_HUB_OFFLINE=1
```

## 下一步是什么？ 🌟

在我们的 [Open WebUI 文档](https://docs.openwebui.com/roadmap/) 中发现即将推出的功能。

## 许可证 📜

本项目包含多种许可证的代码。当前代码库包括在 Open WebUI 许可证下获得许可的组件，并附加了保留"Open WebUI"品牌的额外要求，以及先前贡献者根据其各自原始许可证的贡献。有关许可证变更的详细记录以及代码每个部分适用的条款，请参阅 [LICENSE_HISTORY](./LICENSE_HISTORY)。有关完整和更新的许可详情，请参阅 [LICENSE](./LICENSE) 和 [LICENSE_HISTORY](./LICENSE_HISTORY) 文件。

## 支持 💬

如果您有任何问题、建议或需要帮助，请提交 issue 或加入我们的 [Open WebUI Discord 社区](https://discord.gg/5rJgQTnV4s) 与我们联系！🤝

## Star History

<a href="https://star-history.com/#open-webui/open-webui&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=open-webui/open-webui&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=open-webui/open-webui&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=open-webui/open-webui&type=Date" />
  </picture>
</a>

---

由 [Timothy Jaeryang Baek](https://github.com/tjbck) 创建 - 让我们一起让 Open WebUI 变得更加出色！💪