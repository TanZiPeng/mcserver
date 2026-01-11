# Minecraft 服务器管理面板

一个基于 FastAPI 和 HTML 的 Minecraft Docker 服务器管理面板，提供容器管理、命令执行、资源监控和玩家管理等功能。

## 功能特性

- 🎮 **容器管理**: 启动、停止、重启 Minecraft 服务器容器
- 💻 **命令执行**: 通过 Web 界面执行 Minecraft 服务器命令
- 📊 **资源监控**: 实时显示 CPU 和内存使用情况
- 👥 **玩家管理**: 显示在线玩家列表和人数统计
- ⚙️ **配置管理**: 统一管理容器名称、RCON 配置等信息

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
    "rcon_host": "localhost",              // RCON主机地址
    "rcon_port": 25575,                    // RCON端口
    "rcon_password": "your_password"       // RCON密码
  },
  "server": {
    "host": "0.0.0.0",                     // Web服务监听地址
    "port": 8000,                          // Web服务端口
    "refresh_interval": 5                  // 数据刷新间隔（秒）
  }
}
```

### 3. 启用 RCON（如果尚未启用）

确保你的 Minecraft 服务器已启用 RCON。在 `server.properties` 文件中设置：

```properties
enable-rcon=true
rcon.port=25575
rcon.password=your_password
```

### 4. 运行服务

```bash
python app.py
```

或者使用 uvicorn：

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

### 5. 访问管理面板

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
- 修改容器名称
- 更新 RCON 设置
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

- 确保容器正在运行
- 检查 RCON 是否已启用并配置正确
- 某些 Minecraft 镜像可能使用不同的命令执行方式，请参考镜像文档

### 4. 无法获取玩家信息

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

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
