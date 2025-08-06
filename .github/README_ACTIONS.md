# GitHub Actions 配置说明

本文档说明如何配置 GitHub Actions 自动构建和推送 Docker 镜像到 Docker Hub。

## 前置要求

1. **Docker Hub 账户**: 需要有 Docker Hub 账户
2. **Docker Hub Access Token**: 需要创建访问令牌用于 GitHub Actions

## 配置步骤

### 1. 创建 Docker Hub Access Token

1. 登录 [Docker Hub](https://hub.docker.com/)
2. 点击右上角头像 → Account Settings
3. 选择 Security 标签页
4. 点击 "New Access Token"
5. 填写 Token 名称（如：`github-actions`）
6. 设置权限为 "Read, Write, Delete"
7. 点击 "Generate" 并复制生成的 token

### 2. 在 GitHub 仓库中配置 Secrets

1. 打开 GitHub 仓库
2. 点击 Settings 标签页
3. 在左侧菜单选择 "Secrets and variables" → "Actions"
4. 点击 "New repository secret" 添加以下 secrets：

| Secret 名称 | 值 | 描述 |
|------------|----|----|
| `DOCKERHUB_USERNAME` | 你的 Docker Hub 用户名 | 用于登录 Docker Hub |
| `DOCKERHUB_TOKEN` | 上一步创建的 Access Token | 用于认证推送镜像 |

### 3. 验证配置

配置完成后，可以通过以下方式触发构建：

1. **推送到 main 分支**: 每次推送代码到 main 分支会自动触发构建
2. **创建 tag**: 推送版本标签会触发构建并创建对应版本的镜像
3. **手动触发**: 在 Actions 标签页手动运行 workflow

## Workflow 功能

- **多架构支持**: 自动构建 `linux/amd64` 和 `linux/arm64` 架构
- **智能标签**: 根据推送类型自动生成镜像标签
- **缓存优化**: 使用 GitHub Actions 缓存加速构建
- **安全性**: 只有推送到主分支和标签时才会推送镜像

## 镜像标签规则

| 触发条件 | 生成的标签 |
|---------|----------|
| 推送到 `main` 分支 | `latest`, `main` |
| 推送 `v1.2.3` 标签 | `v1.2.3`, `latest` |
| 发布 Release | `v1.2.3`, `latest` |

## 故障排除

### 常见问题

1. **认证失败**: 检查 `DOCKERHUB_USERNAME` 和 `DOCKERHUB_TOKEN` 是否正确设置
2. **权限不足**: 确保 Docker Hub Access Token 有 "Read, Write, Delete" 权限
3. **构建失败**: 查看 Actions 日志了解具体错误信息

### 调试步骤

1. 检查 GitHub Actions 日志
2. 验证 Dockerfile 语法
3. 确认 Docker Hub 仓库权限
4. 检查网络连接问题