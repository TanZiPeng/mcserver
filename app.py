import json
import os
import subprocess
import time
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
import docker
from docker.errors import DockerException, NotFound, APIError
import aiofiles
from backup import BackupManager

app = FastAPI(title="Minecraft Server Manager")

# 加载配置
CONFIG_FILE = "config.json"
config = {}

def load_config():
    global config
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        # 确保所有必需的配置项都存在
        if 'docker' not in config:
            config['docker'] = {}
        if 'socket_path' not in config['docker']:
            config['docker']['socket_path'] = '/var/run/docker.sock'
        if 'container_name' not in config['docker']:
            config['docker']['container_name'] = 'minecraft-server'
        
        # 确保其他配置项也存在
        if 'minecraft' not in config:
            config['minecraft'] = {}
        if 'command_method' not in config['minecraft']:
            config['minecraft']['command_method'] = 'docker_attach'  # 默认使用docker attach
        if 'server' not in config:
            config['server'] = {}
        if 'backup' not in config:
            config['backup'] = {}
    except FileNotFoundError:
        # 创建默认配置
        config = {
            "docker": {
                "container_name": "minecraft-server",
                "socket_path": "/var/run/docker.sock"
            },
            "minecraft": {
                "rcon_host": "localhost",
                "rcon_port": 25575,
                "rcon_password": "your_rcon_password_here"
            },
            "server": {
                "host": "0.0.0.0",
                "port": 8000,
                "refresh_interval": 5
            },
            "backup": {
                "mc_server_path": "/home/webdev/mcserver",
                "rclone_remote": "cloudflare_r2",
                "bucket_path": "normal",
                "webhook_url": ""
            }
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except json.JSONDecodeError as e:
        print(f"警告: 配置文件格式错误: {e}")
        print("使用默认配置...")
        config = {
            "docker": {
                "container_name": "minecraft-server",
                "socket_path": "/var/run/docker.sock"
            },
            "minecraft": {
                "rcon_host": "localhost",
                "rcon_port": 25575,
                "rcon_password": "your_rcon_password_here"
            },
            "server": {
                "host": "0.0.0.0",
                "port": 8000,
                "refresh_interval": 5
            },
            "backup": {
                "mc_server_path": "/home/webdev/mcserver",
                "rclone_remote": "cloudflare_r2",
                "bucket_path": "normal",
                "webhook_url": ""
            }
        }

load_config()

# 初始化备份管理器
backup_manager = BackupManager(config)

# 初始化Docker客户端
try:
    if os.name == 'nt':  # Windows
        docker_client = docker.from_env()
    else:  # Linux
        # 安全获取 socket_path，如果不存在则使用默认值
        socket_path = config.get('docker', {}).get('socket_path', '/var/run/docker.sock')
        docker_client = docker.DockerClient(base_url='unix://' + socket_path)
except DockerException as e:
    print(f"警告: 无法连接到Docker: {e}")
    docker_client = None
except KeyError as e:
    print(f"警告: 配置文件中缺少必要的配置项: {e}")
    print("尝试使用默认配置...")
    try:
        socket_path = '/var/run/docker.sock'
        docker_client = docker.DockerClient(base_url='unix://' + socket_path)
    except Exception as e2:
        print(f"警告: 无法连接到Docker: {e2}")
        docker_client = None

def get_container():
    """获取Minecraft容器"""
    if not docker_client:
        raise HTTPException(status_code=503, detail="Docker客户端未初始化")
    try:
        return docker_client.containers.get(config['docker']['container_name'])
    except NotFound:
        raise HTTPException(status_code=404, detail=f"容器 '{config['docker']['container_name']}' 未找到")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """返回主页面"""
    try:
        async with aiofiles.open("templates/home.html", 'r', encoding='utf-8') as f:
            content = await f.read()
        return content
    except FileNotFoundError:
        return HTMLResponse(content="<h1>错误: 找不到home.html文件</h1>", status_code=404)

@app.get("/console", response_class=HTMLResponse)
async def console_page():
    """返回控制台/管理面板页面"""
    try:
        async with aiofiles.open("templates/console.html", 'r', encoding='utf-8') as f:
            content = await f.read()
        return content
    except FileNotFoundError:
        return HTMLResponse(content="<h1>错误: 找不到console.html文件</h1>", status_code=404)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    """返回监控面板页面（暂时指向控制台）"""
    return await console_page()

@app.get("/config", response_class=HTMLResponse)
async def config_page():
    """返回配置管理页面（暂时指向控制台）"""
    return await console_page()

@app.get("/api/status")
async def get_status():
    """获取服务器状态"""
    try:
        # 检查 Docker 客户端是否初始化
        if not docker_client:
            return {
                "status": "error",
                "error": "Docker客户端未初始化，请检查Docker是否运行以及权限设置",
                "running": False
            }
        
        container = get_container()
        
        # 如果容器未运行，返回状态但不报错
        if container.status != "running":
            return {
                "status": container.status,
                "cpu_percent": 0,
                "memory_usage_mb": 0,
                "memory_limit_mb": 0,
                "memory_percent": 0,
                "running": False
            }
        
        stats = container.stats(stream=False)
        
        # 计算CPU和内存使用率
        cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
        system_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
        cpu_percent = (cpu_delta / system_delta) * len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100 if system_delta > 0 else 0
        
        memory_usage = stats['memory_stats'].get('usage', 0)
        memory_limit = stats['memory_stats'].get('limit', 0)
        memory_percent = (memory_usage / memory_limit * 100) if memory_limit > 0 else 0
        
        return {
            "status": container.status,
            "cpu_percent": round(cpu_percent, 2),
            "memory_usage_mb": round(memory_usage / 1024 / 1024, 2),
            "memory_limit_mb": round(memory_limit / 1024 / 1024, 2),
            "memory_percent": round(memory_percent, 2),
            "running": container.status == "running"
        }
    except NotFound as e:
        return {
            "status": "error",
            "error": f"容器 '{config.get('docker', {}).get('container_name', 'unknown')}' 未找到",
            "running": False
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "running": False
        }

@app.post("/api/container/start")
async def start_container():
    """启动容器"""
    try:
        container = get_container()
        if container.status == "running":
            return {"success": True, "message": "容器已在运行中"}
        container.start()
        return {"success": True, "message": "容器已启动"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/container/stop")
async def stop_container():
    """停止容器"""
    try:
        container = get_container()
        if container.status != "running":
            return {"success": True, "message": "容器已停止"}
        container.stop()
        return {"success": True, "message": "容器已停止"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/container/restart")
async def restart_container():
    """重启容器"""
    try:
        container = get_container()
        container.restart(timeout=30)
        return {"success": True, "message": "容器已重启"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/minecraft/command")
async def execute_command(command: dict):
    """执行Minecraft命令"""
    try:
        container = get_container()
        if container.status != "running":
            raise HTTPException(status_code=400, detail="容器未运行")
        
        cmd = command.get("command", "")
        if not cmd:
            raise HTTPException(status_code=400, detail="命令不能为空")
        
        # 获取命令执行方式配置
        command_method = config.get('minecraft', {}).get('command_method', 'docker_attach')
        # 可选值: 'docker_attach' (Docker attach方式) 或 'rcon' (RCON连接)
        
        output = ""
        success = False
        
        if command_method == 'docker_attach':
            # 方案1: 使用 docker attach 方式直接向容器输入命令
            try:
                # 方法1: 尝试使用 docker exec 执行命令到 Minecraft 控制台
                # 对于大多数 Minecraft 服务器容器，可以通过以下方式发送命令：
                
                # 首先尝试通过 screen 会话发送命令（如果服务器在 screen 中运行）
                exec_result = container.exec_run(
                    f"screen -S minecraft -p 0 -X stuff '{cmd}^M'",
                    user="root"
                )
                
                if exec_result.exit_code == 0:
                    output = f"命令 '{cmd}' 已通过 screen 发送到服务器"
                    success = True
                else:
                    # 方法2: 尝试通过 tmux 会话发送命令
                    exec_result = container.exec_run(
                        f"tmux send-keys -t minecraft '{cmd}' Enter",
                        user="root"
                    )
                    
                    if exec_result.exit_code == 0:
                        output = f"命令 '{cmd}' 已通过 tmux 发送到服务器"
                        success = True
                    else:
                        # 方法3: 尝试直接写入到 Minecraft 进程的标准输入
                        # 查找 Minecraft 进程的 PID
                        exec_result = container.exec_run(
                            "pgrep -f 'java.*minecraft'",
                            user="root"
                        )
                        
                        if exec_result.exit_code == 0 and exec_result.output:
                            pid = exec_result.output.decode('utf-8').strip().split('\n')[0]
                            # 尝试向进程的标准输入写入命令
                            exec_result = container.exec_run(
                                f"echo '{cmd}' > /proc/{pid}/fd/0",
                                user="root"
                            )
                            
                            if exec_result.exit_code == 0:
                                output = f"命令 '{cmd}' 已发送到 Minecraft 进程 (PID: {pid})"
                                success = True
                            else:
                                # 方法4: 尝试使用 fifo 管道
                                exec_result = container.exec_run(
                                    f"echo '{cmd}' | tee /tmp/minecraft_input",
                                    user="root"
                                )
                                output = f"命令 '{cmd}' 已写入临时文件，请检查服务器日志"
                                success = True
                        else:
                            output = "未找到 Minecraft 进程，请确保服务器正在运行"
                            success = False
                    
                if not success:
                    output = f"Docker attach 方式执行失败。建议：\n1. 确保 Minecraft 服务器在 screen 或 tmux 会话中运行\n2. 或者切换到 RCON 模式\n3. 检查容器是否正确配置"
                    
            except Exception as e:
                output = f"Docker attach 执行失败: {str(e)}。建议切换到 RCON 模式。"
                success = False
        else:
            # 方案2: 使用 RCON 连接
            try:
                import mcrcon
                rcon_host = config.get('minecraft', {}).get('rcon_host', 'localhost')
                rcon_port = config.get('minecraft', {}).get('rcon_port', 25575)
                rcon_password = config.get('minecraft', {}).get('rcon_password', '')
                
                # 先测试端口是否可达（从容器内部或外部）
                # 如果 rcon_host 是 localhost，尝试从容器内部连接
                if rcon_host == 'localhost' or rcon_host == '127.0.0.1':
                    # 从容器内部连接 localhost:25575
                    try:
                        rcon = mcrcon.MCRcon('127.0.0.1', rcon_password, port=rcon_port)
                        rcon.connect()
                        output = rcon.command(cmd)
                        rcon.disconnect()
                        success = True
                    except Exception as e:
                        # 如果从容器内部连接失败，尝试从外部连接（需要暴露端口）
                        try:
                            # 获取容器的 IP 地址或使用主机网络
                            container_ip = container.attrs['NetworkSettings']['IPAddress']
                            if container_ip:
                                rcon = mcrcon.MCRcon(container_ip, rcon_password, port=rcon_port)
                                rcon.connect()
                                output = rcon.command(cmd)
                                rcon.disconnect()
                                success = True
                        except:
                            pass
                else:
                    # 从外部连接指定的主机
                    rcon = mcrcon.MCRcon(rcon_host, rcon_password, port=rcon_port)
                    rcon.connect()
                    output = rcon.command(cmd)
                    rcon.disconnect()
                    success = True
            except ImportError:
                output = "执行失败: 未安装 mcrcon 库。请运行: pip install mcrcon"
                success = False
            except Exception as e:
                output = f"RCON 执行失败: {str(e)}。请确保：1) RCON已启用 2) 端口25575已暴露 3) 密码正确"
                success = False
        
        return {
            "success": success,
            "output": output,
            "exit_code": 0 if success else 1
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/minecraft/logs")
async def get_server_logs(lines: int = 200):
    """获取服务器日志"""
    try:
        container = get_container()
        if container.status != "running":
            return {"success": False, "logs": [], "error": "容器未运行"}
        
        # 尝试多种方式获取日志
        logs = []
        
        # 方法1: 尝试读取常见的日志文件
        log_paths = [
            "/opt/minecraft/logs/latest.log",
            "/data/logs/latest.log", 
            "/server/logs/latest.log",
            "/minecraft/logs/latest.log",
            "/home/minecraft/logs/latest.log"
        ]
        
        for log_path in log_paths:
            try:
                exec_result = container.exec_run(
                    f"test -f {log_path} && tail -{lines} {log_path}",
                    user="root"
                )
                if exec_result.exit_code == 0 and exec_result.output:
                    log_content = exec_result.output.decode('utf-8', errors='ignore')
                    logs = log_content.strip().split('\n')
                    break
            except:
                continue
        
        # 方法2: 如果找不到日志文件，尝试使用 docker logs
        if not logs:
            try:
                container_logs = container.logs(tail=lines, timestamps=True).decode('utf-8', errors='ignore')
                logs = container_logs.strip().split('\n') if container_logs.strip() else []
            except:
                logs = []
        
        # 过滤和格式化日志
        formatted_logs = []
        for log_line in logs:
            if log_line.strip():
                # 简单的日志格式化
                formatted_logs.append({
                    "timestamp": "",
                    "level": "INFO",
                    "message": log_line.strip()
                })
        
        return {
            "success": True,
            "logs": formatted_logs[-lines:] if formatted_logs else [],
            "total": len(formatted_logs)
        }
        
    except Exception as e:
        return {
            "success": False,
            "logs": [],
            "error": str(e)
        }

@app.get("/api/minecraft/players")
async def get_players():
    """获取在线玩家列表"""
    try:
        container = get_container()
        if container.status != "running":
            return {"players": [], "count": 0, "max": 0}
        
        output = ""
        command_method = config.get('minecraft', {}).get('command_method', 'docker_attach')
        
        # 尝试多种方式获取玩家列表
        if command_method == 'docker_attach':
            # 使用 docker attach 方式
            try:
                # 由于 docker attach 方式无法直接获取命令输出，
                # 我们需要通过其他方式获取玩家信息
                # 方法1: 尝试读取服务器日志文件
                exec_result = container.exec_run(
                    "find /opt/minecraft /data /server -name 'latest.log' -o -name 'server.log' 2>/dev/null | head -1",
                    user="root"
                )
                
                if exec_result.exit_code == 0 and exec_result.output:
                    log_path = exec_result.output.decode('utf-8').strip()
                    if log_path:
                        # 读取最近的日志来获取玩家信息
                        exec_result = container.exec_run(
                            f"tail -100 {log_path} | grep -E '(joined the game|left the game)' | tail -10",
                            user="root"
                        )
                        if exec_result.exit_code == 0:
                            log_output = exec_result.output.decode('utf-8', errors='ignore')
                            # 这里可以解析日志来获取玩家信息，但比较复杂
                            # 暂时返回提示信息
                            output = "Docker attach 模式下无法直接获取玩家列表，请查看服务器日志或切换到 RCON 模式"
                
                if not output:
                    output = "无法获取玩家列表，建议切换到 RCON 模式"
            except:
                output = "获取玩家列表失败"
        else:
            # 使用 RCON 方式
            try:
                import mcrcon
                rcon_host = config.get('minecraft', {}).get('rcon_host', 'localhost')
                rcon_port = config.get('minecraft', {}).get('rcon_port', 25575)
                rcon_password = config.get('minecraft', {}).get('rcon_password', '')
                
                if rcon_host == 'localhost' or rcon_host == '127.0.0.1':
                    try:
                        rcon = mcrcon.MCRcon('127.0.0.1', rcon_password, port=rcon_port)
                        rcon.connect()
                        output = rcon.command("list")
                        rcon.disconnect()
                    except Exception as e:
                        try:
                            container_ip = container.attrs['NetworkSettings']['IPAddress']
                            if container_ip:
                                rcon = mcrcon.MCRcon(container_ip, rcon_password, port=rcon_port)
                                rcon.connect()
                                output = rcon.command("list")
                                rcon.disconnect()
                        except:
                            pass
                else:
                    rcon = mcrcon.MCRcon(rcon_host, rcon_password, port=rcon_port)
                    rcon.connect()
                    output = rcon.command("list")
                    rcon.disconnect()
            except (ImportError, Exception):
                pass
        
        # 解析输出: "There are X of a max of Y players online: player1, player2"
        players = []
        count = 0
        max_players = 0
        
        if output and "online" in output.lower():
            # 解析玩家数量
            import re
            # 匹配 "There are X of a max of Y players online"
            match = re.search(r'There are (\d+) of a max of (\d+) players online', output)
            if match:
                count = int(match.group(1))
                max_players = int(match.group(2))
            
            # 解析玩家列表
            if "online:" in output:
                parts = output.split("online:")
                if len(parts) == 2:
                    players_str = parts[1].strip()
                    if players_str and players_str.lower() != "there are no players online":
                        players = [p.strip() for p in players_str.split(",") if p.strip()]
        
        return {
            "players": players,
            "count": count,
            "max": max_players
        }
    except Exception as e:
        return {
            "players": [],
            "count": 0,
            "max": 0,
            "error": str(e)
        }

@app.get("/api/config")
async def get_config():
    """获取配置"""
    return config

@app.post("/api/config")
async def update_config(new_config: dict):
    """更新配置"""
    global config, backup_manager
    try:
        # 合并配置
        config.update(new_config)
        
        # 保存到文件
        async with aiofiles.open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(config, indent=2, ensure_ascii=False))
        
        # 重新加载备份管理器
        backup_manager = BackupManager(config)
        
        # 重新加载Docker客户端（如果socket路径改变）
        global docker_client
        if 'docker' in new_config and 'socket_path' in new_config['docker']:
            try:
                if os.name != 'nt':
                    docker_client = docker.DockerClient(base_url='unix://' + config['docker']['socket_path'])
            except:
                pass
        
        return {"success": True, "message": "配置已更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 备份相关路由
@app.get("/backup", response_class=HTMLResponse)
async def backup_page():
    """返回备份管理页面"""
    try:
        async with aiofiles.open("templates/backup.html", 'r', encoding='utf-8') as f:
            content = await f.read()
        return content
    except FileNotFoundError:
        return HTMLResponse(content="<h1>错误: 找不到backup.html文件</h1>", status_code=404)

@app.post("/api/backup/start")
async def start_backup(background_tasks: BackgroundTasks, request: Request):
    """启动备份任务"""
    try:
        # 获取要备份的路径列表
        body = await request.json()
        selected_paths = body.get("selected_paths", []) if isinstance(body, dict) else []
        
        # 在后台执行备份（不等待完成）
        async def run_backup():
            await backup_manager.execute_backup(selected_paths=selected_paths)
        
        background_tasks.add_task(run_backup)
        return {"success": True, "message": "备份任务已启动，正在后台执行"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/backup/history")
async def get_backup_history(limit: int = 20):
    """获取备份历史记录"""
    try:
        history = backup_manager.get_history(limit)
        return {"success": True, "history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/backup/{backup_id}")
async def get_backup_detail(backup_id: str):
    """获取备份详情"""
    try:
        backup = backup_manager.get_backup_by_id(backup_id)
        if not backup:
            raise HTTPException(status_code=404, detail="备份记录未找到")
        return {"success": True, "backup": backup}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/backup/scan")
async def scan_backup_directory():
    """扫描备份目录，返回最外层的文件和文件夹列表"""
    try:
        backup_config = config.get('backup', {})
        mc_server_path = backup_config.get('mc_server_path', '/home/webdev/mcserver')
        
        if not os.path.exists(mc_server_path):
            return {"success": False, "error": f"目录不存在: {mc_server_path}"}
        
        items = []
        try:
            # 只扫描最外层
            for item in os.listdir(mc_server_path):
                item_path = os.path.join(mc_server_path, item)
                # 跳过隐藏文件
                if item.startswith('.'):
                    continue
                
                is_dir = os.path.isdir(item_path)
                size = 0
                if not is_dir:
                    try:
                        size = os.path.getsize(item_path)
                    except:
                        pass
                else:
                    # 如果是目录，尝试计算总大小（可选，可能较慢）
                    try:
                        for root, dirs, files in os.walk(item_path):
                            for file in files:
                                try:
                                    size += os.path.getsize(os.path.join(root, file))
                                except:
                                    pass
                    except:
                        pass
                
                items.append({
                    "name": item,
                    "type": "directory" if is_dir else "file",
                    "size": size,
                    "size_formatted": _format_bytes(size)
                })
            
            # 按类型和名称排序：目录在前，然后按名称排序
            items.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
            
        except PermissionError:
            return {"success": False, "error": f"没有权限访问目录: {mc_server_path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        
        return {"success": True, "path": mc_server_path, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _format_bytes(bytes: int) -> str:
    """格式化字节数为可读格式"""
    if bytes == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.2f} PB"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config['server']['host'], port=config['server']['port'])
