# Minecraft 服务器管理面板

一个基于 FastAPI 和 HTML 的 Minecraft Docker 服务器管理面板，提供容器管理、命令执行、资源监控和玩家管理等功能。

## 功能特性

- 🎮 **容器管理**: 启动、停止、重启 Minecraft 服务器容器
- 💻 **命令执行**: 支持两种方式执行 Minecraft 服务器命令（Docker Attach 和 RCON）
- 📊 **资源监控**: 实时显示 CPU 和内存使用情况
- 👥 **玩家管理**: 显示在线玩家列表和人数统计
- ⚙️ **配置管理**: 统一管理容器名称、命令执行方式、RCON 配置等信息
- 💾 **备份管理**: 支持自动备份和云存储同步

## 系统要求

- Python 3.8+
- Docker 已安装并运行
- 已运行的 Minecraft 服务器容器

## 安装步骤

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置设置

编辑 `config.json` 文件，设置以下配置：

```json
{
  "docker": {
    "container_name": "minecraft-server",  // 你的Minecraft容器名称
    "socket_path": "/var/run/docker.sock"  // Linux系统，Windows会自动检测
  },
  "minecraft": {
    "command_method": "docker_attach",     // 命令执行方式: "docker_attach" 或 "rcon"
    "rcon_host": "localhost",              // RCON主机地址（仅RCON模式需要）
    "rcon_port": 25575,                    // RCON端口（仅RCON模式需要）
    "rcon_password": "your_password"       // RCON密码（仅RCON模式需要）
  },
  "server": {
    "host": "0.0.0.0",                     // Web服务监听地址
    "port": 8000,                          // Web服务端口
    "refresh_interval": 5                  // 数据刷新间隔（秒）
  }
}
```

### 3. 配置命令执行方式

本管理面板支持两种命令执行方式：

#### Docker Attach 方式（推荐新手）
- **优点**: 无需额外配置，直接向容器发送命令
- **缺点**: 无法获取命令执行结果，玩家列表功能有限
- **配置**: 在 `config.json` 中设置 `"command_method": "docker_attach"`

#### RCON 方式（推荐高级用户）
- **优点**: 完整的命令执行和结果获取，支持完整的玩家列表功能
- **缺点**: 需要配置 RCON
- **配置**: 在 `config.json` 中设置 `"command_method": "rcon"`

### 4. 启用 RCON（仅 RCON 模式需要）

确保你的 Minecraft 服务器已启用 RCON。在 `server.properties` 文件中设置：

```properties
enable-rcon=true
rcon.port=25575
rcon.password=your_password
```

### 5. 运行服务

```bash
python app.py
```

或者使用 uvicorn：

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

### 6. 访问管理面板

打开浏览器访问：`http://localhost:8000`

## 使用说明

### 容器控制

- **启动**: 启动 Minecraft 服务器容器
- **停止**: 停止运行中的容器
- **重启**: 重启容器（会短暂中断服务）

### 执行命令

在命令输入框中输入 Minecraft 命令，例如：
- `say Hello World` - 向所有玩家发送消息
- `list` - 列出在线玩家
- `time set day` - 设置时间为白天
- `give @a diamond 64` - 给所有玩家64个钻石

### 监控信息

管理面板会自动刷新显示：
- 容器运行状态
- CPU 使用率
- 内存使用情况（包括使用量和百分比）
- 在线玩家数量和列表

### 配置管理

在配置管理区域可以：
- 查看当前配置
- 选择命令执行方式（Docker Attach 或 RCON）
- 修改容器名称
- 更新 RCON 设置（仅 RCON 模式需要）
- 保存配置（需要重启服务生效）

## Docker 使用说明

### Windows

在 Windows 上，Docker 客户端会自动使用 Docker Desktop 的配置，无需额外设置。

### Linux

确保 Docker socket 路径正确。默认路径为 `/var/run/docker.sock`。如果使用 rootless Docker 或其他配置，请修改 `config.json` 中的 `socket_path`。

## 常见问题

### 1. 无法连接到 Docker

- 确保 Docker 服务正在运行
- 在 Linux 上，确保当前用户有权限访问 Docker socket（可能需要将用户添加到 docker 组）
- 检查 `config.json` 中的 socket 路径是否正确

### 2. 找不到容器

- 检查容器名称是否正确（使用 `docker ps -a` 查看）
- 确保容器存在（即使已停止）

### 3. 命令执行失败

#### Docker Attach 模式
- 确保容器正在运行
- 检查 Minecraft 服务器是否在 screen 或 tmux 会话中运行
- 查看服务器日志确认命令是否被执行
- 如果问题持续，建议切换到 RCON 模式

#### RCON 模式
- 确保容器正在运行
- 检查 RCON 是否已启用并配置正确
- 确保安装了 `mcrcon` 库：`pip install mcrcon`
- 验证 RCON 端口是否正确暴露

### 4. 无法获取玩家信息

#### Docker Attach 模式
- 此模式下玩家列表功能有限，建议切换到 RCON 模式获取完整功能

#### RCON 模式
- 确保 RCON 配置正确
- 检查服务器是否支持 `list` 命令
- 查看浏览器控制台是否有错误信息

## 技术栈

- **后端**: FastAPI
- **前端**: HTML + CSS + JavaScript
- **Docker**: docker-py
- **RCON**: mcrcon (可选)

## 安全注意事项

⚠️ **重要**: 此管理面板提供了对 Minecraft 服务器的完全控制，请确保：

1. 不要将服务暴露到公网，或使用防火墙限制访问
2. 使用强密码保护 RCON
3. 在生产环境中考虑添加身份验证
4. 定期备份服务器数据

## 命令执行方式详细说明

详细的命令执行方式说明请参考：[COMMAND_METHODS.md](COMMAND_METHODS.md)

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
