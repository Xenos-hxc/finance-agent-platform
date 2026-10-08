# EchoMind

面向客服场景的多 Agent 系统，提供意图识别、知识库检索、工具调用、分层记忆与评测监控。仓库包含 Python 和 Java 两套后端实现，共用 Vue 前端，可切换后端查看对话、检索和评测结果。

## 功能与结构

| 目录 | 内容 |
| --- | --- |
| `EchoMind/` | FastAPI、Anthropic SDK、Redis、ChromaDB，多 Agent 编排与工具调用 |
| `EchoMindJava/` | Java 21、Spring Boot、Spring AI，BM25 + 本地向量融合检索 |
| `EchoMindFrontend/` | Vue 3、Vite，对话、知识库、记忆、监控和评测页面 |

请求经过记忆读取、意图识别、Agent 路由、知识检索与工具调用，生成回复后写回记忆。Skills 文件维护客服规则；评测与监控用于检查路由效果、回答质量和运行状态。Java 版长期记忆与知识库使用 JSON 持久化，Python 版使用 ChromaDB。

## Docker 启动

需要 Docker 和 Docker Compose。复制根目录 `.env.example` 为 `.env`，填写自己的模型 API Key，设置 Redis 密码。

```bash
cp .env.example .env
docker compose --env-file .env -f EchoMindFrontend/docker-compose.yml up -d --build
```

Windows 可用 `Copy-Item .env.example .env`。前端入口：`http://localhost:5174`；统一网关：`http://localhost`；Python API：`http://localhost:8000/docs`；Java API：`http://localhost:8080/docs`。

首次构建 Python 镜像会下载依赖与 embedding 模型，需要网络连接。填写有效 Key 后才能验证真实模型回复；Java 在未配置 Key 时支持本地降级回复。演示数据、用户画像、会话记录和导入的知识库由运行时生成，不随源码提供。

## 本地开发

Python 需要 Python 3.11 或 3.12、Redis；从 `EchoMind/` 运行：

```bash
python -m venv .venv
# 激活虚拟环境后执行
pip install -r requirements-dev.txt
cp .env.example .env
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Java 需要 JDK 21、Maven 3.8.6+、Redis。设置 `REDIS_HOST`、`REDIS_PORT`、`REDIS_PASSWORD`、模型 API Key 等环境变量后，从 `EchoMindJava/` 运行 `mvn spring-boot:run`。Java 本地运行不自动读取 `.env`；Docker Compose 会传入配置。

前端需要 Node.js 22.12+；从 `EchoMindFrontend/` 运行 `npm ci` 与 `npm run dev`，访问 `http://localhost:5173`。默认代理转发到 Python 的 8000 端口和 Java 的 8080 端口。

## 验证

- Python：在 `EchoMind/` 运行 `python -m pytest tests`。
- Java：在 `EchoMindJava/` 运行 `mvn test` 或 `mvn package`。
- 前端：在 `EchoMindFrontend/` 运行 `npm run build`。

Redis 集成测试仅在设置 `ECHOMIND_TEST_REDIS=true` 时运行，应使用隔离的测试服务。模型评测需要自行配置模型服务与测试知识库。

## 配置与部署

本仓库只提供源码、依赖清单、示例配置与部署文件。`.env`、密钥、运行数据和构建产物均被 Git 忽略。示例密码仅用于本地演示。客服 API 的公网部署需要另外配置身份认证、访问控制和 HTTPS。
