import json
import os
import subprocess
import time
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
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
            }
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

load_config()

# 初始化备份管理器
backup_manager = BackupManager(config)

# 初始化Docker客户端
try:
    if os.name == 'nt':  # Windows
        docker_client = docker.from_env()
    else:  # Linux
        docker_client = docker.DockerClient(base_url='unix://' + config['docker']['socket_path'])
except DockerException as e:
    print(f"警告: 无法连接到Docker: {e}")
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
        container = get_container()
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
        
        # 尝试多种方式执行命令
        output = ""
        success = False
        
        # 方式1: 尝试使用rcon-cli
        try:
            exec_result = container.exec_run(
                f"rcon-cli {cmd}",
                user="root"
            )
            output = exec_result.output.decode('utf-8', errors='ignore') if exec_result.output else ""
            success = exec_result.exit_code == 0
        except:
            pass
        
        # 方式2: 如果rcon-cli失败，尝试直接写入到服务器控制台
        if not success:
            try:
                # 通过docker exec直接执行命令（适用于某些镜像）
                exec_result = container.exec_run(
                    f"mc-send-to-console {cmd}",
                    user="root"
                )
                output = exec_result.output.decode('utf-8', errors='ignore') if exec_result.output else ""
                success = exec_result.exit_code == 0
            except:
                pass
        
        # 方式3: 如果都失败，尝试使用mcrcon（如果可用）
        if not success:
            try:
                import mcrcon
                rcon = mcrcon.MCRcon(
                    config['minecraft']['rcon_host'],
                    config['minecraft']['rcon_password'],
                    port=config['minecraft']['rcon_port']
                )
                rcon.connect()
                output = rcon.command(cmd)
                rcon.disconnect()
                success = True
            except ImportError:
                output = "执行失败: 请确保容器支持rcon-cli/mc-send-to-console，或安装mcrcon库"
                success = False
            except Exception as e:
                output = f"执行失败: {str(e)}。请确保已配置RCON或容器支持rcon-cli/mc-send-to-console"
                success = False
        
        return {
            "success": success,
            "output": output,
            "exit_code": 0 if success else 1
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/minecraft/players")
async def get_players():
    """获取在线玩家列表"""
    try:
        container = get_container()
        if container.status != "running":
            return {"players": [], "count": 0, "max": 0}
        
        output = ""
        
        # 尝试多种方式获取玩家列表
        # 方式1: 使用rcon-cli
        try:
            exec_result = container.exec_run(
                "rcon-cli list",
                user="root"
            )
            output = exec_result.output.decode('utf-8', errors='ignore') if exec_result.output else ""
        except:
            pass
        
        # 方式2: 使用mcrcon
        if not output:
            try:
                import mcrcon
                rcon = mcrcon.MCRcon(
                    config['minecraft']['rcon_host'],
                    config['minecraft']['rcon_password'],
                    port=config['minecraft']['rcon_port']
                )
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
async def start_backup(background_tasks: BackgroundTasks):
    """启动备份任务"""
    try:
        # 在后台执行备份（不等待完成）
        async def run_backup():
            await backup_manager.execute_backup()
        
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config['server']['host'], port=config['server']['port'])
