# Minecraft 服务器命令执行方式说明

本管理面板支持两种方式向 Minecraft 服务器发送命令：

## 1. Docker Attach 方式 (`docker_attach`)

### 特点
- **直接性**: 直接向容器内的 Minecraft 进程发送命令
- **无需配置**: 不需要配置 RCON 端口和密码
- **兼容性**: 适用于大多数 Docker 化的 Minecraft 服务器

### 工作原理
系统会尝试以下几种方法向服务器发送命令：
1. 通过 `screen` 会话发送命令（如果服务器在 screen 中运行）
2. 通过 `tmux` 会话发送命令（如果服务器在 tmux 中运行）
3. 直接向 Minecraft 进程的标准输入写入命令
4. 使用临时文件传递命令

### 适用场景
- 使用 Docker 容器运行的 Minecraft 服务器
- 服务器在 screen 或 tmux 会话中运行
- 不想配置 RCON 的情况

### 限制
- 无法直接获取命令执行结果
- 获取玩家列表功能有限
- 依赖于容器的具体配置

## 2. RCON 方式 (`rcon`)

### 特点
- **标准协议**: 使用 Minecraft 官方的 RCON 协议
- **完整功能**: 支持命令执行和结果获取
- **可靠性**: 稳定的双向通信

### 工作原理
通过 TCP 连接到 Minecraft 服务器的 RCON 端口，发送命令并接收响应。

### 配置要求
在 Minecraft 服务器的 `server.properties` 文件中需要启用 RCON：
```properties
enable-rcon=true
rcon.port=25575
rcon.password=your_password_here
```

### 适用场景
- 需要获取命令执行结果的情况
- 需要完整的玩家列表功能
- 服务器已经配置了 RCON

### 限制
- 需要额外配置 RCON
- 需要暴露 RCON 端口（如果从容器外部连接）
- 需要安装 `mcrcon` Python 库

## 配置示例

### Docker Attach 模式
```json
{
  "minecraft": {
    "command_method": "docker_attach"
  }
}
```

### RCON 模式
```json
{
  "minecraft": {
    "command_method": "rcon",
    "rcon_host": "localhost",
    "rcon_port": 25575,
    "rcon_password": "your_rcon_password"
  }
}
```

## 推荐使用

- **新手用户**: 推荐使用 `docker_attach` 方式，配置简单
- **高级用户**: 推荐使用 `rcon` 方式，功能完整
- **生产环境**: 推荐使用 `rcon` 方式，更加可靠

## 故障排除

### Docker Attach 方式问题
1. 确保 Minecraft 服务器在 screen 或 tmux 会话中运行
2. 检查容器是否有足够的权限
3. 查看服务器日志确认命令是否被执行

### RCON 方式问题
1. 确保 `server.properties` 中启用了 RCON
2. 检查 RCON 端口是否正确暴露
3. 验证 RCON 密码是否正确
4. 确保安装了 `mcrcon` 库：`pip install mcrcon`