#!/usr/bin/env python3
"""
PatchWatch Web Interface
Web interface for configuring and monitoring PatchWatch service
"""

import json
import time
import subprocess
import threading
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Import monitoring service
try:
    from monitoring_service import PatchWatchMonitoringService, MonitoringConfig, load_monitoring_config
except ImportError:
    print("Warning: monitoring_service not available")
    PatchWatchMonitoringService = None

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse
    from pydantic import BaseModel
    import uvicorn
except ImportError as e:
    print(f"❌ Missing dependencies: {e}")
    exit(1)


class PathTestRequest(BaseModel):
    path: str
    path_type: str = "local"


class MonitoringControlRequest(BaseModel):
    action: str  # "start" or "stop"


class FullScanRequest(BaseModel):
    force_resync: bool = False  # Принудительно синхронизировать все файлы


class ConfigUpdateRequest(BaseModel):
    local_developer_folder: str
    path_type: str = "local"
    gitlab_url: str = "http://10.19.1.20/Automatization/patchwatch"
    gitlab_token: str = "glpat-HgBE57H_YinfANkjP6P4"
    gitlab_project_id: str = "92"
    git_author_name: str = "Андрей Комаров"
    git_author_email: str = "prostopil@yandex.ru"


def full_scan_folder(base_path: str, force_resync: bool = False) -> Dict[str, Any]:
    """Полное сканирование папки для поиска файлов для синхронизации и удаления"""
    import re
    
    try:
        base_path_obj = Path(base_path)
        if not base_path_obj.exists():
            return {
                "success": False, 
                "error": f"Папка не найдена: {base_path}",
                "scanned_files": 0,
                "processed_files": 0,
                "deleted_files": 0
            }
        
        # Поиск папок с датами (YYYYMMDD)
        date_pattern = re.compile(r'^\d{8}$')
        scanned_files = 0
        processed_files = 0
        deleted_files = 0
        scan_results = []
        
        print(f"🔍 Начинаю полное сканирование: {base_path}")
        
        # Создаем множество существующих файлов для проверки удалений
        existing_files = set()
        
        # Сканируем локальные файлы
        for date_dir in base_path_obj.iterdir():
            if not date_dir.is_dir() or not date_pattern.match(date_dir.name):
                continue
                
            print(f"📅 Проверяю папку даты: {date_dir.name}")
            
            # Поиск файлов в структуре to/htdocs/api/analog_numbers/
            target_path = date_dir / "to" / "htdocs" / "api" / "analog_numbers"
            if not target_path.exists():
                continue
                
            for file_path in target_path.rglob("*"):
                if file_path.is_file():
                    scanned_files += 1
                    
                    # Добавляем файл в множество существующих
                    relative_path = str(file_path.relative_to(base_path_obj))
                    existing_files.add(relative_path)
                    
                    # Пропускаем временные файлы
                    if file_path.name.startswith('.') or file_path.suffix in ['.tmp', '.temp']:
                        continue
                    
                    # Обрабатываем файл через мониторинг
                    if monitoring_service_instance:
                        try:
                            monitoring_service_instance.process_file_change(str(file_path), "scan")
                            processed_files += 1
                            scan_results.append({
                                "file": relative_path,
                                "status": "processed",
                                "action": "sync",
                                "size": file_path.stat().st_size
                            })
                        except Exception as e:
                            scan_results.append({
                                "file": relative_path,
                                "status": "error",
                                "action": "sync",
                                "error": str(e)
                            })
        
        # Проверяем удаленные файлы, сравнивая с backup-ом
        sync_dir = Path("synced_to_gitlab")
        if sync_dir.exists():
            print(f"🔍 Проверяю удаленные файлы в backup директории...")
            
            # Проходим по всем файлам в backup
            for backup_file in sync_dir.rglob("*"):
                if backup_file.is_file() and backup_file.name != '.gitkeep':
                    # Получаем относительный путь файла в backup
                    backup_relative = backup_file.relative_to(sync_dir)
                    
                    # Пропускаем файлы не из папки data
                    if not str(backup_relative).startswith('data/'):
                        continue
                    
                    # Преобразуем путь back в локальную структуру
                    # data/htdocs/api/analog_numbers/file.txt -> YYYYMMDD/to/htdocs/api/analog_numbers/file.txt
                    backup_parts = backup_relative.parts
                    if len(backup_parts) >= 4 and backup_parts[0] == 'data':
                        # Попытаемся найти соответствующий локальный файл
                        # Для этого проверим все папки с датами
                        file_found = False
                        
                        for date_dir in base_path_obj.iterdir():
                            if not date_dir.is_dir() or not date_pattern.match(date_dir.name):
                                continue
                            
                            # Построим ожидаемый путь файла
                            expected_local_path = date_dir / "to" / Path(*backup_parts[1:])
                            relative_expected = str(expected_local_path.relative_to(base_path_obj))
                            
                            if relative_expected in existing_files:
                                file_found = True
                                break
                        
                        # Если файл не найден в локальной папке, но есть в backup - удаляем
                        if not file_found and monitoring_service_instance:
                            try:
                                # Анализируем путь для получения информации о файле
                                # Создаем фиктивный путь для анализа
                                dummy_path = base_path_obj / "20000101" / "to" / Path(*backup_parts[1:])
                                path_info = monitoring_service_instance.analyze_file_path(dummy_path)
                                
                                if path_info:
                                    # Обновляем path_info с правильным target path из backup
                                    path_info['full_target'] = str(backup_relative).replace('\\', '/')
                                    
                                    print(f"🗑️ Обнаружен удаленный файл: {backup_relative}")
                                    success = monitoring_service_instance.delete_from_gitlab(path_info, None)  # None because file is already deleted locally
                                    
                                    if success:
                                        deleted_files += 1
                                        scan_results.append({
                                            "file": str(backup_relative),
                                            "status": "deleted",
                                            "action": "delete",
                                            "size": backup_file.stat().st_size
                                        })
                                    else:
                                        scan_results.append({
                                            "file": str(backup_relative),
                                            "status": "error",
                                            "action": "delete",
                                            "error": "Failed to delete from GitLab"
                                        })
                                        
                            except Exception as e:
                                scan_results.append({
                                    "file": str(backup_relative),
                                    "status": "error",
                                    "action": "delete",
                                    "error": str(e)
                                })
        
        message = f"Сканирование завершено: {scanned_files} файлов просканировано, {processed_files} обработано"
        if deleted_files > 0:
            message += f", {deleted_files} удалено"
        
        return {
            "success": True,
            "scanned_files": scanned_files,
            "processed_files": processed_files,
            "deleted_files": deleted_files,
            "results": scan_results[-15:],  # Последние 15 результатов
            "message": message
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка сканирования: {str(e)}",
            "scanned_files": 0,
            "processed_files": 0,
            "deleted_files": 0
        }


def start_monitoring(config_path: str) -> bool:
    """Start monitoring process"""
    global monitoring_process, monitoring_active, monitoring_service_instance
    
    if monitoring_active:
        return True
    
    try:
        if PatchWatchMonitoringService is None:
            print("❌ Monitoring service not available")
            return False
        
        # Load configuration
        try:
            if 'load_monitoring_config' in globals():
                config = load_monitoring_config()
            else:
                raise ImportError("load_monitoring_config not available")
        except (ImportError, NameError, AttributeError):
            # If load_monitoring_config is not available, use load_config instead
            config_data = load_config()
            from monitoring_service import MonitoringConfig
            config = MonitoringConfig(
                local_developer_folder=config_data['local_developer_folder'],
                gitlab_url=config_data.get('gitlab_url', 'http://10.19.1.20/Automatization/patchwatch'),
                gitlab_token=config_data.get('gitlab_token', 'glpat-HgBE57H_YinfANkjP6P4'),
                gitlab_project_id=config_data.get('gitlab_project_id', '92'),
                git_author_name=config_data.get('git_author_name', 'Андрей Комаров'),
                git_author_email=config_data.get('git_author_email', 'prostopil@yandex.ru')
            )
        
        # Create and start monitoring service
        monitoring_service_instance = PatchWatchMonitoringService(config)
        
        if monitoring_service_instance.start_monitoring():
            monitoring_active = True
            print(f"🚀 Monitoring started for: {config.local_developer_folder}")
            return True
        else:
            print("❌ Failed to start monitoring service")
            return False
            
    except Exception as e:
        print(f"Error starting monitoring: {e}")
        return False


def stop_monitoring() -> bool:
    """Stop monitoring process"""
    global monitoring_process, monitoring_active, monitoring_service_instance
    
    try:
        if monitoring_service_instance:
            monitoring_service_instance.stop_monitoring()
            monitoring_service_instance = None
        
        if monitoring_process:
            monitoring_process.terminate()
            monitoring_process = None
            
        monitoring_active = False
        print("🛑 Monitoring stopped")
        return True
    except Exception as e:
        print(f"Error stopping monitoring: {e}")
        return False


def get_monitoring_status() -> Dict[str, Any]:
    """Get current monitoring status"""
    global monitoring_service_instance
    
    base_status = {
        "active": monitoring_active,
        "status": "running" if monitoring_active else "stopped"
    }
    
    if monitoring_service_instance:
        service_status = monitoring_service_instance.get_status()
        base_status.update({
            "processed_files_count": service_status.get("processed_files_count", 0),
            "monitored_folder": service_status.get("monitored_folder", ""),
            "gitlab_url": service_status.get("gitlab_url", "")
        })
    
    return base_status


def test_path(path: str) -> Dict[str, Any]:
    try:
        path_obj = Path(path)
        start_time = time.time()
        
        result = {
            'accessible': False,
            'path_exists': path_obj.exists(),
            'is_directory': False,
            'readable': False,
            'writable': False,
            'response_time': 0,
            'error_details': None
        }
        
        if result['path_exists']:
            result['is_directory'] = path_obj.is_dir()
            
            if result['is_directory']:
                try:
                    list(path_obj.iterdir())
                    result['readable'] = True
                except PermissionError:
                    result['readable'] = False
                    result['error_details'] = "No read permission"
                
                try:
                    test_file = path_obj / '.patchwatch_test'
                    test_file.write_text('test')
                    test_file.unlink()
                    result['writable'] = True
                except:
                    result['writable'] = False
                
                result['accessible'] = result['readable']
            else:
                result['error_details'] = "Path is not a directory"
        else:
            result['error_details'] = "Path does not exist"
        
        result['response_time'] = time.time() - start_time
        return result
        
    except Exception as e:
        return {
            'accessible': False,
            'error_details': str(e),
            'response_time': 0
        }


def load_config() -> Dict[str, Any]:
    """Load configuration"""
    config_file = Path("working_config.json")
    
    default_config = {
        'local_developer_folder': "C:\\Users\\BLACK\\Desktop\\asterisk-pbx",
        'path_type': 'local',
        'gitlab_url': 'http://10.19.1.20/Automatization/patchwatch',
        'gitlab_token': 'glpat-HgBE57H_YinfANkjP6P4',
        'gitlab_project_id': '92',
        'git_author_name': 'Андрей Комаров',
        'git_author_email': 'prostopil@yandex.ru'
    }
    
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                default_config.update(config)
        except:
            pass
    
    return default_config


def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration"""
    try:
        config_file = Path("working_config.json")
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


# Global monitoring state
monitoring_process = None
monitoring_active = False
monitoring_service_instance = None

# Create FastAPI app
app = FastAPI(title="PatchWatch Configuration", version="1.0.0")


@app.get("/", response_class=HTMLResponse)
async def main_page():
    """Main configuration page"""
    config = load_config()
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>PatchWatch Configuration</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; text-align: center; }}
        .form-group {{ margin-bottom: 20px; }}
        label {{ display: block; margin-bottom: 5px; font-weight: bold; color: #333; }}
        input, select {{ width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 5px; font-size: 16px; }}
        input:focus, select:focus {{ border-color: #667eea; outline: none; }}
        .btn {{ padding: 12px 20px; margin: 5px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }}
        .btn-primary {{ background: #667eea; color: white; }}
        .btn-secondary {{ background: #6c757d; color: white; }}
        .btn-success {{ background: #28a745; color: white; }}
        .btn:hover {{ opacity: 0.9; }}
        .info-box {{ background: #e3f2fd; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #2196f3; }}
        .alert {{ padding: 15px; border-radius: 5px; margin: 10px 0; display: none; }}
        .alert-success {{ background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }}
        .alert-error {{ background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }}
        .status {{ margin: 10px 0; padding: 10px; border-radius: 5px; }}
        .status-ok {{ background: #d4edda; color: #155724; }}
        .status-indicator {{ display: inline-block; padding: 4px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; }}
        .status-running {{ background: #d4edda; color: #155724; }}
        .status-stopped {{ background: #f8d7da; color: #721c24; }}
        .monitoring-controls {{ background: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #ffc107; }}
        .btn:disabled {{ background: #6c757d; cursor: not-allowed; opacity: 0.6; }}
        .collapsible {{ cursor: pointer; padding: 10px; background-color: #f1f1f1; border: none; outline: none; width: 100%; text-align: left; font-size: 15px; }}
        .content {{ padding: 0 18px; max-height: 0; overflow: hidden; transition: max-height 0.2s ease-out; background-color: #f9f9f9; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 PatchWatch Configuration</h1>
            <p>Configure local developer folder for GitLab synchronization</p>
        </div>
        
        <div class="info-box">
            <h3>📋 System Information</h3>
            <p><strong>GitLab Source of Truth:</strong> <a href="{config['gitlab_url']}/-/tree/main/data" target="_blank">{config['gitlab_url']}/-/tree/main/data</a></p>
            <p><strong>Git Author:</strong> {config['git_author_name']} &lt;{config['git_author_email']}&gt;</p>
            <p><strong>Current Local Folder:</strong> <span id="currentFolder">{config['local_developer_folder']}</span></p>
        </div>
        
        <div id="statusArea"></div>
        <div id="alertArea"></div>
        
        <div class="form-group">
            <label for="localPath">Local Developer Folder Path:</label>
            <input type="text" id="localPath" value="{config['local_developer_folder']}" 
                   placeholder="C:\\path\\to\\folder or \\\\server\\share\\folder">
            <small>Path where developers drop new files (can be local or network path)</small>
        </div>
        
        <div class="form-group">
            <label for="pathType">Path Type:</label>
            <select id="pathType">
                <option value="local" {"selected" if config['path_type'] == 'local' else ""}>Local Path</option>
                <option value="unc" {"selected" if config['path_type'] == 'unc' else ""}>UNC Network Path</option>
                <option value="smb" {"selected" if config['path_type'] == 'smb' else ""}>SMB Share</option>
            </select>
        </div>
        
        <div class="form-group">
            <button class="btn btn-secondary" onclick="testPath()">🔍 Test Path</button>
            <button class="btn btn-primary" onclick="saveConfig()">💾 Save Configuration</button>
            <button class="btn btn-secondary" onclick="loadStatus()">🔄 Refresh Status</button>
        </div>
        
        <button type="button" class="collapsible">🌐 GitLab Repository Configuration</button>
        <div class="content">
            <div class="info-box">
                <p>Configure the target GitLab repository for synchronization:</p>
                
                <div class="form-group">
                    <label for="gitlabUrl">GitLab Repository URL:</label>
                    <input type="text" id="gitlabUrl" value="{config['gitlab_url']}" 
                           placeholder="http://your-gitlab.com/group/project">
                    <small>GitLab repository URL (without /-/tree/main/data suffix)</small>
                </div>
                
                <div class="form-group">
                    <label for="gitlabToken">GitLab Access Token:</label>
                    <input type="password" id="gitlabToken" value="{config['gitlab_token']}" 
                           placeholder="glpat-xxxxxxxxxxxxx">
                    <small>Personal Access Token with Maintainer permissions (glpat-*)</small>
                </div>
                
                <div class="form-group">
                    <label for="gitlabProjectId">GitLab Project ID:</label>
                    <input type="text" id="gitlabProjectId" value="{config['gitlab_project_id']}" 
                           placeholder="92">
                    <small>Numeric project ID from GitLab</small>
                </div>
                
                <div class="form-group">
                    <label for="gitAuthorName">Git Author Name:</label>
                    <input type="text" id="gitAuthorName" value="{config['git_author_name']}" 
                           placeholder="Андрей Комаров">
                </div>
                
                <div class="form-group">
                    <label for="gitAuthorEmail">Git Author Email:</label>
                    <input type="email" id="gitAuthorEmail" value="{config['git_author_email']}" 
                           placeholder="prostopil@yandex.ru">
                </div>
                
                <div class="form-group">
                    <button class="btn btn-success" onclick="saveGitLabConfig()">💾 Save GitLab Config</button>
                    <button class="btn btn-secondary" onclick="testGitLabConnection()">🔗 Test Connection</button>
                </div>
            </div>
        </div>
        
        <div class="monitoring-controls">
            <h3>🔄 Monitoring Controls</h3>
            <p>Start or stop monitoring the configured local developer folder:</p>
            <div id="monitoringStatus" class="status">Status: <span id="monitoringStatusText">Loading...</span></div>
            <div id="monitoringStats" class="info-box" style="display: none;">
                <p><strong>📊 Processed Files:</strong> <span id="processedCount">0</span></p>
                <p><strong>📁 Monitored Folder:</strong> <span id="monitoredFolder">-</span></p>
            </div>
            <div class="form-group">
                <button id="startBtn" class="btn btn-primary" onclick="startMonitoring()">▶️ Start Monitoring</button>
                <button id="stopBtn" class="btn btn-secondary" onclick="stopMonitoring()">⏹️ Stop Monitoring</button>
                <button class="btn btn-success" onclick="fullScan()">🔍 Сканировать папку</button>
                <button class="btn btn-secondary" onclick="showLogs()">📄 View Logs</button>
            </div>
            <small><strong>Note:</strong> Monitoring will watch for changes in the local folder and sync them to GitLab automatically.</small>
        </div>
        
        <div id="logsSection" class="info-box" style="display: none;">
            <h3>📄 Recent Logs</h3>
            <div id="logsContent" style="background: #f8f9fa; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px; max-height: 300px; overflow-y: auto;">
                Loading logs...
            </div>
            <div style="margin-top: 10px;">
                <button class="btn btn-secondary" onclick="refreshLogs()">🔄 Refresh Logs</button>
                <button class="btn btn-secondary" onclick="hideLogs()">❌ Hide Logs</button>
            </div>
        </div>
        
        <div class="info-box">
            <h3>💡 Next Steps</h3>
            <ol>
                <li>Configure the local developer folder path above</li>
                <li>Test the path to ensure it's accessible</li>
                <li>Save the configuration</li>
                <li>Use the "Start Monitoring" button above to begin watching for changes</li>
                <li>Files added to the local folder will be automatically synced to GitLab</li>
            </ol>
        </div>
        
        <div class="info-box">
            <h3>🗂️ Path Mapping</h3>
            <p><strong>htdocs/</strong> → <code>data/htdocs/</code></p>
            <p><strong>script/</strong> → <code>data/script/</code></p>
            <p><strong>home/storage/local/</strong> → <code>data/home/storage/local/</code></p>
        </div>
    </div>
    
    <script>
        // Collapsible functionality for GitLab configuration
        document.addEventListener('DOMContentLoaded', function() {{
            var coll = document.getElementsByClassName("collapsible");
            for (var i = 0; i < coll.length; i++) {{
                coll[i].addEventListener("click", function() {{
                    this.classList.toggle("active");
                    var content = this.nextElementSibling;
                    if (content.style.maxHeight) {{
                        content.style.maxHeight = null;
                    }} else {{
                        content.style.maxHeight = content.scrollHeight + "px";
                    }}
                }});
            }}
        }});
        
        async function showAlert(message, type = 'info') {{
            const alertArea = document.getElementById('alertArea');
            const alertClass = type === 'error' ? 'alert-error' : 'alert-success';
            
            alertArea.innerHTML = `<div class="alert ${{alertClass}}" style="display: block;">${{message}}</div>`;
            
            setTimeout(() => {{
                alertArea.innerHTML = '';
            }}, 5000);
        }}
        
        async function testPath() {{
            const path = document.getElementById('localPath').value;
            const pathType = document.getElementById('pathType').value;
            
            if (!path.trim()) {{
                showAlert('Please enter a path to test', 'error');
                return;
            }}
            
            try {{
                const response = await fetch('/test-path', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        path: path,
                        path_type: pathType
                    }})
                }});
                
                const result = await response.json();
                
                if (result.accessible) {{
                    showAlert(`✅ Path is accessible! Response time: ${{result.response_time.toFixed(2)}}s`, 'success');
                }} else {{
                    showAlert(`❌ Path is not accessible: ${{result.error_details}}`, 'error');
                }}
            }} catch (error) {{
                showAlert(`❌ Error testing path: ${{error.message}}`, 'error');
            }}
        }}
        
        async function saveConfig() {{
            const localPath = document.getElementById('localPath').value;
            const pathType = document.getElementById('pathType').value;
            
            try {{
                const response = await fetch('/save-config', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        local_developer_folder: localPath,
                        path_type: pathType
                    }})
                }});
                
                const result = await response.json();
                showAlert('✅ Configuration saved successfully!', 'success');
                document.getElementById('currentFolder').textContent = localPath;
            }} catch (error) {{
                showAlert(`❌ Error saving configuration: ${{error.message}}`, 'error');
            }}
        }}
        
        async function saveGitLabConfig() {{
            const gitlabUrl = document.getElementById('gitlabUrl').value;
            const gitlabToken = document.getElementById('gitlabToken').value;
            const gitlabProjectId = document.getElementById('gitlabProjectId').value;
            const gitAuthorName = document.getElementById('gitAuthorName').value;
            const gitAuthorEmail = document.getElementById('gitAuthorEmail').value;
            
            try {{
                const response = await fetch('/save-config', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        gitlab_url: gitlabUrl,
                        gitlab_token: gitlabToken,
                        gitlab_project_id: gitlabProjectId,
                        git_author_name: gitAuthorName,
                        git_author_email: gitAuthorEmail
                    }})
                }});
                
                const result = await response.json();
                showAlert('✅ GitLab configuration saved successfully!', 'success');
            }} catch (error) {{
                showAlert(`❌ Error saving GitLab configuration: ${{error.message}}`, 'error');
            }}
        }}
        
        async function testGitLabConnection() {{
            const gitlabUrl = document.getElementById('gitlabUrl').value;
            const gitlabToken = document.getElementById('gitlabToken').value;
            
            try {{
                const response = await fetch('/test-gitlab', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        gitlab_url: gitlabUrl,
                        gitlab_token: gitlabToken
                    }})
                }});
                
                const result = await response.json();
                
                if (result.success) {{
                    showAlert(`✅ Connected to GitLab as ${{result.user_name}} (${{result.username}})`, 'success');
                }} else {{
                    showAlert(`❌ GitLab connection failed: ${{result.error}}`, 'error');
                }}
            }} catch (error) {{
                showAlert(`❌ Error testing GitLab connection: ${{error.message}}`, 'error');
            }}
        }}
        
        async function loadStatus() {{
            try {{
                const response = await fetch('/monitoring/status');
                const monitoringData = await response.json();
                updateMonitoringStatus(monitoringData);
            }} catch (error) {{
                console.error('Error loading status:', error);
            }}
        }}
        
        async function startMonitoring() {{
            try {{
                const response = await fetch('/monitoring', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{action: 'start'}})
                }});
                
                const result = await response.json();
                if (response.ok) {{
                    showAlert('✅ Monitoring started successfully!', 'success');
                    loadStatus();
                }} else {{
                    showAlert(`❌ Failed to start monitoring: ${{result.detail}}`, 'error');
                }}
            }} catch (error) {{
                showAlert(`❌ Error starting monitoring: ${{error.message}}`, 'error');
            }}
        }}
        
        async function stopMonitoring() {{
            try {{
                const response = await fetch('/monitoring', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{action: 'stop'}})
                }});
                
                const result = await response.json();
                if (response.ok) {{
                    showAlert('✅ Monitoring stopped successfully!', 'success');
                    loadStatus();
                }} else {{
                    showAlert(`❌ Failed to stop monitoring: ${{result.detail}}`, 'error');
                }}
            }} catch (error) {{
                showAlert(`❌ Error stopping monitoring: ${{error.message}}`, 'error');
            }}
        }}
        
        async function fullScan() {{
            try {{
                const response = await fetch('/full-scan', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{force_resync: false}})
                }});
                
                const result = await response.json();
                if (result.success) {{
                    let message = `✅ Full scan completed successfully!\\n\\n📊 Results:\\n📁 Scanned files: ${{result.scanned_files}}\\n✅ Processed files: ${{result.processed_files}}`;
                    
                    // Добавляем детали об удаленных файлах
                    if (result.deleted_files && result.deleted_files > 0) {{
                        message += `\\n🗑️ Удалено файлов из GitLab: ${{result.deleted_files}}`;
                    }}
                    
                    // Показываем результаты последних операций
                    if (result.results && result.results.length > 0) {{
                        message += `\\n\\nПоследние операции:`;
                        result.results.forEach(item => {{
                            const actionIcon = item.action === 'delete' ? '🗑️' : (item.action === 'sync' ? '🔄' : '📄');
                            const statusIcon = item.status === 'error' ? '❌' : '✅';
                            message += `\\n${{actionIcon}} ${{statusIcon}} ${{item.file}}`;
                            if (item.error) {{
                                message += ` (Ошибка: ${{item.error}})`;
                            }}
                        }});
                    }}
                    
                    showAlert(message, 'success');
                    
                    // Обновляем логи чтобы показать результаты сканирования
                    if (document.getElementById('logsSection').style.display !== 'none') {{
                        refreshLogs();
                    }}
                }} else {{
                    showAlert(`❌ Ошибка сканирования: ${{result.error}}`, 'error');
                }}
            }} catch (error) {{
                showAlert(`❌ Ошибка сканирования: ${{error.message}}`, 'error');
            }}
        }}
        
        function updateMonitoringStatus(monitoringData) {{
            const statusText = document.getElementById('monitoringStatusText');
            const startBtn = document.getElementById('startBtn');
            const stopBtn = document.getElementById('stopBtn');
            const monitoringStatus = document.getElementById('monitoringStatus');
            const monitoringStats = document.getElementById('monitoringStats');
            
            if (monitoringData.active) {{
                statusText.innerHTML = '<span class="status-indicator status-running">Running</span>';
                startBtn.disabled = true;
                stopBtn.disabled = false;
                monitoringStatus.className = 'status status-ok';
                
                // Show and update statistics
                if (monitoringStats) {{
                    monitoringStats.style.display = 'block';
                    document.getElementById('processedCount').textContent = monitoringData.processed_files_count || 0;
                    document.getElementById('monitoredFolder').textContent = monitoringData.monitored_folder || '-';
                }}
            }} else {{
                statusText.innerHTML = '<span class="status-indicator status-stopped">Stopped</span>';
                startBtn.disabled = false;
                stopBtn.disabled = true;
                monitoringStatus.className = 'status';
                
                // Hide statistics
                if (monitoringStats) {{
                    monitoringStats.style.display = 'none';
                }}
            }}
        }}
        
        async function showLogs() {{
            const logsSection = document.getElementById('logsSection');
            logsSection.style.display = 'block';
            await refreshLogs();
        }}
        
        function hideLogs() {{
            document.getElementById('logsSection').style.display = 'none';
        }}
        
        async function refreshLogs() {{
            try {{
                const response = await fetch('/logs');
                const data = await response.json();
                
                const logsContent = document.getElementById('logsContent');
                if (data.logs && data.logs.length > 0) {{
                    logsContent.innerHTML = data.logs.map(log => `<div>${{log}}</div>`).join('');
                }} else {{
                    logsContent.innerHTML = 'No logs available or logs file not found.';
                }}
                
                // Auto-scroll to bottom
                logsContent.scrollTop = logsContent.scrollHeight;
            }} catch (error) {{
                document.getElementById('logsContent').innerHTML = `Error loading logs: ${{error.message}}`;
            }}
        }}
        
        // Load status on page load
        window.onload = function() {{
            loadStatus();
        }};
    </script>
</body>
</html>'''
    
    return HTMLResponse(content=html)


@app.post("/test-path")
async def test_path_endpoint(request: PathTestRequest):
    """Test path accessibility"""
    result = test_path(request.path)
    return JSONResponse(result)


@app.post("/test-gitlab")
async def test_gitlab_connection(request: dict):
    """Test GitLab connection"""
    try:
        gitlab_url = request.get('gitlab_url', '').rstrip('/')
        gitlab_token = request.get('gitlab_token', '')
        
        if not gitlab_url or not gitlab_token:
            return JSONResponse({
                "success": False,
                "error": "GitLab URL and token are required"
            })
        
        # Test connection by getting user info
        api_url = f"{gitlab_url}/api/v4/user"
        headers = {'PRIVATE-TOKEN': gitlab_token}
        
        import requests
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            user_info = response.json()
            return JSONResponse({
                "success": True,
                "user_name": user_info.get('name', 'Unknown'),
                "username": user_info.get('username', 'Unknown'),
                "access_level": "Valid token"
            })
        elif response.status_code == 401:
            return JSONResponse({
                "success": False,
                "error": "Invalid token or insufficient permissions"
            })
        else:
            return JSONResponse({
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:100]}"
            })
            
    except requests.exceptions.ConnectTimeout:
        return JSONResponse({
            "success": False,
            "error": "Connection timeout - check GitLab URL"
        })
    except requests.exceptions.ConnectionError:
        return JSONResponse({
            "success": False,
            "error": "Connection failed - check GitLab URL and network"
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"Test failed: {str(e)}"
        })


@app.post("/save-config")
async def save_config_endpoint(request: ConfigUpdateRequest):
    """Save configuration"""
    try:
        config = load_config()
        
        # Update all fields that are provided
        config['local_developer_folder'] = request.local_developer_folder
        config['path_type'] = request.path_type
        
        # Update GitLab configuration if provided
        if hasattr(request, 'gitlab_url') and request.gitlab_url:
            config['gitlab_url'] = request.gitlab_url
        if hasattr(request, 'gitlab_token') and request.gitlab_token:
            config['gitlab_token'] = request.gitlab_token
        if hasattr(request, 'gitlab_project_id') and request.gitlab_project_id:
            config['gitlab_project_id'] = request.gitlab_project_id
        if hasattr(request, 'git_author_name') and request.git_author_name:
            config['git_author_name'] = request.git_author_name
        if hasattr(request, 'git_author_email') and request.git_author_email:
            config['git_author_email'] = request.git_author_email
        
        if save_config(config):
            return JSONResponse({"message": "Configuration saved successfully"})
        else:
            raise HTTPException(status_code=500, detail="Failed to save configuration")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/monitoring")
async def control_monitoring(request: MonitoringControlRequest):
    """Start or stop monitoring"""
    try:
        config = load_config()
        
        if request.action == "start":
            if start_monitoring(config['local_developer_folder']):
                return JSONResponse({"message": "Monitoring started successfully", "status": "running"})
            else:
                raise HTTPException(status_code=500, detail="Failed to start monitoring")
        elif request.action == "stop":
            if stop_monitoring():
                return JSONResponse({"message": "Monitoring stopped successfully", "status": "stopped"})
            else:
                raise HTTPException(status_code=500, detail="Failed to stop monitoring")
        else:
            raise HTTPException(status_code=400, detail="Invalid action. Use 'start' or 'stop'")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/full-scan")
async def full_scan_endpoint(request: FullScanRequest):
    """Полное сканирование локальной папки"""
    try:
        config = load_config()
        base_path = config['local_developer_folder']
        
        # Убеждаемся, что мониторинг сервис запущен
        if not monitoring_service_instance:
            # Попытаемся запустить мониторинг
            start_monitoring(base_path)
            
        if not monitoring_service_instance:
            raise HTTPException(
                status_code=500, 
                detail="Мониторинг сервис не запущен. Пожалуйста, сначала запустите мониторинг."
            )
        
        # Выполняем полное сканирование
        result = full_scan_folder(base_path, request.force_resync)
        
        return JSONResponse(result)
        
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"Ошибка сервера: {str(e)}",
            "scanned_files": 0,
            "processed_files": 0
        })


@app.get("/monitoring/status")
async def get_monitoring_status_endpoint():
    """Get monitoring status"""
    status = get_monitoring_status()
    return JSONResponse(status)


@app.get("/logs")
async def get_logs():
    """Get recent log entries"""
    try:
        from datetime import datetime
        import os
        
        # Get absolute path to logs directory
        current_dir = Path(__file__).parent
        logs_dir = current_dir / "logs"
        
        if not logs_dir.exists():
            return JSONResponse({"logs": ["❌ Logs directory not found at: " + str(logs_dir)]})
        
        # Get all log files and find the most recent one
        log_files = sorted(logs_dir.glob("patchwatch_*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
        
        if not log_files:
            return JSONResponse({"logs": ["❌ No log files found in logs directory"]})
        
        # Use the most recent log file
        log_file = log_files[0]
        today = datetime.now().strftime('%Y%m%d')
        log_date = log_file.stem.replace('patchwatch_', '')
        
        if log_date != today:
            status_msg = f"📅 Showing logs from {log_date} (most recent available)"
        else:
            status_msg = f"📅 Showing today's logs ({today})"
        
        # Read last 50 lines for better context (increased from 30)
        encodings_to_try = ['utf-8', 'cp1251', 'cp866', 'latin-1']
        
        for encoding in encodings_to_try:
            try:
                with open(log_file, 'r', encoding=encoding, errors='ignore') as f:
                    lines = f.readlines()
                    recent_lines = lines[-50:] if len(lines) > 50 else lines
                    
                # Clean up and format lines
                clean_lines = [status_msg]  # Add status message first
                for line in recent_lines:
                    line = line.strip()
                    # Filter out noise but keep important monitoring events
                    if line and not line.startswith('INFO:     127.0.0.1'):
                        # Highlight important events with icons
                        if '✅ Файл успешно синхронизирован' in line:
                            line = f"🎆 {line}"
                        elif '❌ Ошибка' in line:
                            line = f"🚨 {line}"
                        elif '🔍 Обработка файла' in line:
                            line = f"📝 {line}"
                        elif '🔄 Мониторинг' in line or '🚀 Запуск' in line:
                            line = f"🚀 {line}"
                        elif '📋 Анализ пути' in line:
                            line = f"🔎 {line}"
                        elif '🌐 Синхронизация с GitLab' in line:
                            line = f"☁️ {line}"
                        clean_lines.append(line)
                
                if len(clean_lines) <= 1:  # Only status message
                    clean_lines.append("📋 Мониторинг запущен, ожидаю изменения файлов...")
                
                return JSONResponse({"logs": clean_lines})
                
            except UnicodeDecodeError:
                continue  # Try next encoding
            except Exception as e:
                return JSONResponse({"logs": [f"❌ Ошибка чтения с кодировкой {encoding}: {str(e)}"]})
        
        # If all encodings failed, read as binary and filter
        try:
            with open(log_file, 'rb') as f:
                content = f.read()
                # Try to decode with errors='replace' to show what we can
                text_content = content.decode('utf-8', errors='replace')
                lines = text_content.split('\\n')
                recent_lines = lines[-30:] if len(lines) > 30 else lines
                
            clean_lines = []
            for line in recent_lines:
                line = line.strip()
                if line and not line.startswith('INFO:     127.0.0.1'):
                    clean_lines.append(line)
            
            if not clean_lines:
                clean_lines = ["📝 Логи найдены, но есть проблемы с кодировкой"]
                
            return JSONResponse({"logs": clean_lines})
            
        except Exception as e:
            return JSONResponse({"logs": [f"❌ Критическая ошибка чтения файла: {str(e)}"]})
        
    except Exception as e:
        return JSONResponse({"logs": [f"❌ Error reading logs: {str(e)}"]})


@app.get("/debug")
async def debug_info():
    """Debug information about paths and files"""
    import os
    from datetime import datetime
    
    current_dir = Path(__file__).parent
    logs_dir = current_dir / "logs"
    today = datetime.now().strftime('%Y%m%d')
    log_file = logs_dir / f"patchwatch_{today}.log"
    
    debug_info = {
        "current_working_dir": os.getcwd(),
        "script_dir": str(current_dir),
        "logs_dir_path": str(logs_dir),
        "logs_dir_exists": logs_dir.exists(),
        "log_file_path": str(log_file),
        "log_file_exists": log_file.exists(),
        "log_file_size": log_file.stat().st_size if log_file.exists() else 0
    }
    
    if logs_dir.exists():
        debug_info["log_files"] = [f.name for f in logs_dir.glob("*.log")]
    
    return JSONResponse(debug_info)


@app.get("/status")
async def get_status():
    """Get system status"""
    config = load_config()
    path_test = test_path(config['local_developer_folder'])
    monitoring_status = get_monitoring_status()
    
    return JSONResponse({
        "status": "ok" if path_test['accessible'] else "warning",
        "local_path_accessible": path_test['accessible'],
        "monitoring": monitoring_status,
        "configuration": config
    })


def main():
    """Start the web interface"""
    print("🚀 Starting PatchWatch Web Interface...")
    print("🌐 Access the web interface at: http://localhost:8085")
    print("💡 Press Ctrl+C to stop the server")
    
    try:
        uvicorn.run("web_interface:app", host="0.0.0.0", port=8085, reload=False)
    except KeyboardInterrupt:
        print("\\n🛑 Stopping web interface...")
    except Exception as e:
        print(f"❌ Error starting web interface: {e}")


if __name__ == "__main__":
    main()