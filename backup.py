import json
import os
import subprocess
import time
import asyncio
from datetime import datetime
from typing import Dict, Optional
import aiohttp
import aiofiles

class BackupManager:
    def __init__(self, config: Dict):
        self.config = config
        self.backup_config = config.get('backup', {})
        self.mc_server_path = self.backup_config.get('mc_server_path', '/home/webdev/mcserver')
        self.rclone_remote = self.backup_config.get('rclone_remote', 'cloudflare_r2')
        self.bucket_path = self.backup_config.get('bucket_path', 'normal')
        self.webhook_url = self.backup_config.get('webhook_url', '')
        
        # 备份历史记录文件
        self.history_file = 'backup_history.json'
        self.history = self._load_history()
    
    def _load_history(self) -> list:
        """加载备份历史记录"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
        return []
    
    def _save_history(self):
        """保存备份历史记录"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存备份历史失败: {e}")
    
    async def send_webhook_notification(self, title: str, content: str, status: str = "info"):
        """发送企业微信 webhook 通知"""
        if not self.webhook_url:
            return
        
        # 企业微信 webhook 消息格式
        # status: success, error, info
        status_emoji = {
            "success": "✅",
            "error": "❌",
            "info": "ℹ️"
        }
        
        # 企业微信 webhook 消息格式
        message = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"# {status_emoji.get(status, 'ℹ️')} {title}\n\n{content}\n\n**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=message,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    result = await response.json()
                    return result
        except Exception as e:
            print(f"发送 webhook 通知失败: {e}")
            return None
    
    async def execute_backup(self, selected_paths: list = None) -> Dict:
        """执行备份操作
        
        Args:
            selected_paths: 要备份的路径列表（相对于 mc_server_path），如果为 None 则备份全部
        """
        start_time = time.time()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_id = f"backup_{timestamp}"
        
        remote_path = f"{self.rclone_remote}:{self.bucket_path}/{timestamp}"
        
        # 如果指定了要备份的路径，使用 include 模式
        if selected_paths and len(selected_paths) > 0:
            # 构建多个 rclone 命令，每个路径单独同步
            backup_tasks = []
            for path in selected_paths:
                source_path = os.path.join(self.mc_server_path, path)
                # 确保路径存在
                if not os.path.exists(source_path):
                    continue
                
                rclone_cmd = [
                    'rclone',
                    'copy',  # 使用 copy 而不是 sync，因为只备份选中的路径
                    source_path,
                    f"{self.rclone_remote}:{self.bucket_path}/{timestamp}/{path}",
                    '--transfers', '4',
                    '--checkers', '8',
                    '--skip-links',
                    '--copy-links',
                    '--no-update-modtime',
                    '--progress',
                    '--stats', '1s',
                    '-v'
                ]
                backup_tasks.append(rclone_cmd)
        else:
            # 备份全部，使用原来的逻辑
            backup_tasks = [[
                'rclone',
                'sync',
                self.mc_server_path,
                remote_path,
                '--transfers', '4',
                '--checkers', '8',
                '--skip-links',
                '--copy-links',
                '--no-update-modtime',
                '--exclude', '*.tmp',
                '--exclude', '*.log',
                '--exclude', '*.lock',
                '--exclude', 'logs/**',
                '--exclude', 'crash-reports/**',
                '--progress',
                '--stats', '1s',
                '-v'
            ]]
        
        backup_record = {
            "id": backup_id,
            "timestamp": timestamp,
            "start_time": datetime.now().isoformat(),
            "status": "running",
            "remote_path": remote_path,
            "local_path": self.mc_server_path,
            "selected_paths": selected_paths or [],
            "output": "",
            "error": None,
            "duration": 0,
            "files_transferred": 0,
            "bytes_transferred": 0
        }
        
        self.history.insert(0, backup_record)
        self._save_history()
        
        # 发送开始通知
        paths_info = f"**备份路径**: `{self.mc_server_path}`"
        if selected_paths and len(selected_paths) > 0:
            paths_info += f"\n**选中路径**: {', '.join(selected_paths)}"
        else:
            paths_info += "\n**备份模式**: 全部备份"
        
        await self.send_webhook_notification(
            "备份任务开始",
            f"{paths_info}\n**目标**: `{remote_path}`\n**备份ID**: `{backup_id}`",
            "info"
        )
        
        try:
            # 执行所有备份任务
            all_output = ""
            all_error_output = ""
            total_files = 0
            total_bytes = 0
            all_success = True
            
            for rclone_cmd in backup_tasks:
                # 执行 rclone 命令
                process = await asyncio.create_subprocess_exec(
                    *rclone_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                output = stdout.decode('utf-8', errors='ignore')
                error_output = stderr.decode('utf-8', errors='ignore')
                
                all_output += output + "\n"
                if error_output:
                    all_error_output += error_output + "\n"
                
                if process.returncode != 0:
                    all_success = False
                
                # 解析每个任务的统计信息
                if output:
                    import re
                    lines = output.split('\n')
                    for line in lines:
                        if 'Transferred:' in line:
                            file_match = re.search(r'Transferred:\s*(\d+)', line)
                            if file_match:
                                try:
                                    total_files += int(file_match.group(1))
                                except:
                                    pass
                            
                            size_match = re.search(r'(\d+\.?\d*)\s*(B|KB|MB|GB|TB)', line, re.IGNORECASE)
                            if size_match:
                                try:
                                    size_value = float(size_match.group(1))
                                    size_unit = size_match.group(2).upper()
                                    multipliers = {
                                        'B': 1, 'KB': 1024, 'MB': 1024 * 1024,
                                        'GB': 1024 * 1024 * 1024, 'TB': 1024 * 1024 * 1024 * 1024
                                    }
                                    total_bytes += int(size_value * multipliers.get(size_unit, 1))
                                except:
                                    pass
                            break
            
            end_time = time.time()
            duration = round(end_time - start_time, 2)
            
            output = all_output
            error_output = all_error_output
            
            # 解析 rclone 输出，提取统计信息
            files_transferred = 0
            bytes_transferred = 0
            
            if output:
                import re
                # 尝试从输出中提取统计信息
                # rclone 输出格式示例: "Transferred:   123 / 456, 1.234 GB, 4.567 MB/s, ETA 0s"
                lines = output.split('\n')
                for line in lines:
                    # 匹配 "Transferred:" 行
                    if 'Transferred:' in line:
                        # 提取文件数: "Transferred:   123 / 456"
                        file_match = re.search(r'Transferred:\s*(\d+)', line)
                        if file_match:
                            try:
                                files_transferred = int(file_match.group(1))
                            except:
                                pass
                        
                        # 提取字节数: "1.234 GB" 或 "1.234 MB" 等
                        size_match = re.search(r'(\d+\.?\d*)\s*(B|KB|MB|GB|TB)', line, re.IGNORECASE)
                        if size_match:
                            try:
                                size_value = float(size_match.group(1))
                                size_unit = size_match.group(2).upper()
                                
                                multipliers = {
                                    'B': 1,
                                    'KB': 1024,
                                    'MB': 1024 * 1024,
                                    'GB': 1024 * 1024 * 1024,
                                    'TB': 1024 * 1024 * 1024 * 1024
                                }
                                bytes_transferred = int(size_value * multipliers.get(size_unit, 1))
                            except:
                                pass
                        break
            
            if all_success:
                backup_record.update({
                    "status": "success",
                    "output": output,
                    "duration": duration,
                    "files_transferred": total_files,
                    "bytes_transferred": total_bytes,
                    "end_time": datetime.now().isoformat()
                })
                
                # 发送成功通知
                await self.send_webhook_notification(
                    "备份任务完成",
                    f"**备份ID**: `{backup_id}`\n**状态**: ✅ 成功\n**耗时**: {duration} 秒\n**传输文件数**: {total_files}\n**传输数据量**: {self._format_bytes(total_bytes)}\n**目标路径**: `{remote_path}`",
                    "success"
                )
            else:
                backup_record.update({
                    "status": "error",
                    "output": output,
                    "error": error_output,
                    "duration": duration,
                    "end_time": datetime.now().isoformat()
                })
                
                # 发送失败通知
                error_preview = error_output[:500] if error_output else "未知错误"
                await self.send_webhook_notification(
                    "备份任务失败",
                    f"**备份ID**: `{backup_id}`\n**状态**: ❌ 失败\n**耗时**: {duration} 秒\n**错误信息**: \n```\n{error_preview}\n```",
                    "error"
                )
            
            # 更新历史记录
            for i, record in enumerate(self.history):
                if record['id'] == backup_id:
                    self.history[i] = backup_record
                    break
            self._save_history()
            
            return backup_record
            
        except Exception as e:
            end_time = time.time()
            duration = round(end_time - start_time, 2)
            error_msg = str(e)
            
            backup_record.update({
                "status": "error",
                "error": error_msg,
                "duration": duration,
                "end_time": datetime.now().isoformat()
            })
            
            # 更新历史记录
            for i, record in enumerate(self.history):
                if record['id'] == backup_id:
                    self.history[i] = backup_record
                    break
            self._save_history()
            
            # 发送错误通知
            await self.send_webhook_notification(
                "备份任务异常",
                f"**备份ID**: `{backup_id}`\n**状态**: ❌ 异常\n**错误信息**: \n```\n{error_msg}\n```",
                "error"
            )
            
            return backup_record
    
    def _format_bytes(self, bytes: int) -> str:
        """格式化字节数为可读格式"""
        if bytes == 0:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes < 1024.0:
                return f"{bytes:.2f} {unit}"
            bytes /= 1024.0
        return f"{bytes:.2f} PB"
    
    def get_history(self, limit: int = 20) -> list:
        """获取备份历史记录"""
        return self.history[:limit]
    
    def get_backup_by_id(self, backup_id: str) -> Optional[Dict]:
        """根据ID获取备份记录"""
        for record in self.history:
            if record['id'] == backup_id:
                return record
        return None
