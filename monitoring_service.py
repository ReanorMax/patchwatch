#!/usr/bin/env python3
"""
PatchWatch Real-time File Monitoring Service
Monitors local developer folders and syncs to GitLab with comprehensive logging
"""

import os
import sys
import json
import time
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError as e:
    print(f"❌ Missing dependencies: {e}")
    print("Please install: pip install watchdog requests")
    sys.exit(1)


@dataclass
class MonitoringConfig:
    """Configuration for monitoring service"""
    local_developer_folder: str
    gitlab_url: str = "http://10.19.1.20/Automatization/patchwatch"
    gitlab_token: str = "glpat-HgBE57H_YinfANkjP6P4"
    gitlab_project_id: str = "92"
    git_author_name: str = "Андрей Комаров"
    git_author_email: str = "prostopil@yandex.ru"
    log_level: str = "INFO"
    auto_confirm: bool = True
    auto_sync: bool = True
    auto_delete: bool = True


class FileChangeHandler(FileSystemEventHandler):
    """Handles file system events for monitoring"""
    
    def __init__(self, monitoring_service):
        self.monitoring_service = monitoring_service
        self.logger = logging.getLogger(f"{__name__}.FileChangeHandler")
    
    def on_created(self, event):
        """Handle file creation events"""
        if not event.is_directory:
            self.logger.info(f"📄 Новый файл создан: {event.src_path}")
            self.monitoring_service.process_file_change(event.src_path, "created")
    
    def on_modified(self, event):
        """Handle file modification events"""
        if not event.is_directory:
            self.logger.info(f"✏️ Файл изменен: {event.src_path}")
            self.monitoring_service.process_file_change(event.src_path, "modified")
    
    def on_moved(self, event):
        """Handle file move events"""
        if not event.is_directory:
            self.logger.info(f"📁 Файл перемещен: {event.src_path} → {event.dest_path}")
            self.monitoring_service.process_file_change(event.dest_path, "moved")
    
    def on_deleted(self, event):
        """Handle file deletion events"""
        if not event.is_directory:
            self.logger.warning(f"🗑️ Файл удален: {event.src_path}")
            self.monitoring_service.process_file_change(event.src_path, "deleted")


class PatchWatchMonitoringService:
    """Main monitoring service for PatchWatch"""
    
    def __init__(self, config: MonitoringConfig):
        self.config = config
        self.observer = None
        self.is_running = False
        self.processed_files = set()
        
        # Setup logging
        self.setup_logging()
        self.logger = logging.getLogger(__name__)
        
        # Create working directory
        self.working_dir = Path("monitoring_work")
        self.working_dir.mkdir(exist_ok=True)
        
        self.logger.info("🎯 PatchWatch Monitoring Service инициализирован")
        self.logger.info(f"📁 Отслеживаемая папка: {self.config.local_developer_folder}")
        self.logger.info(f"🌐 GitLab URL: {self.config.gitlab_url}")
        if self.config.auto_confirm:
            self.logger.info("✅ Автоподтверждение включено - автономная работа")
            self.logger.info(f"   🔄 Автосинхронизация: {'вкл.' if self.config.auto_sync else 'выкл.'}")
            self.logger.info(f"   🗑️ Автоудаление: {'вкл.' if self.config.auto_delete else 'выкл.'}")
        else:
            self.logger.warning("⚠️ Автоподтверждение выключено - ручное подтверждение")
    
    def setup_logging(self):
        """Setup comprehensive logging"""
        # Create logs directory
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # Setup logger
        logger = logging.getLogger()
        logger.setLevel(getattr(logging, self.config.log_level))
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_format)
        
        # File handler
        log_file = logs_dir / f"patchwatch_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        
        # Add handlers
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
    
    def start_monitoring(self) -> bool:
        """Start the monitoring service"""
        try:
            monitor_path = Path(self.config.local_developer_folder)
            
            if not monitor_path.exists():
                self.logger.error(f"❌ Папка для мониторинга не существует: {monitor_path}")
                return False
            
            self.logger.info("🚀 Запуск мониторинга файловой системы...")
            
            # Create event handler
            event_handler = FileChangeHandler(self)
            
            # Setup observer
            self.observer = Observer()
            self.observer.schedule(event_handler, str(monitor_path), recursive=True)
            
            # Start observer
            self.observer.start()
            self.is_running = True
            
            self.logger.info("✅ Мониторинг успешно запущен!")
            self.logger.info(f"👀 Отслеживаю папку: {monitor_path}")
            self.logger.info("🔄 Ожидаю изменения файлов...")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка запуска мониторинга: {e}")
            return False
    
    def stop_monitoring(self) -> bool:
        """Stop the monitoring service"""
        try:
            if self.observer and self.is_running:
                self.logger.info("🛑 Остановка мониторинга...")
                self.observer.stop()
                self.observer.join()
                self.is_running = False
                self.logger.info("✅ Мониторинг остановлен")
                return True
            else:
                self.logger.warning("⚠️ Мониторинг уже остановлен")
                return False
        except Exception as e:
            self.logger.error(f"❌ Ошибка остановки мониторинга: {e}")
            return False
    
    def process_file_change(self, file_path: str, change_type: str):
        """Process detected file changes"""
        try:
            file_path_obj = Path(file_path)
            
            # Skip temporary files
            if file_path_obj.name.startswith('.') or file_path_obj.suffix in ['.tmp', '.temp']:
                self.logger.debug(f"⏭️ Пропускаю временный файл: {file_path}")
                return
            
            # Skip already processed files
            if file_path in self.processed_files:
                self.logger.debug(f"⏭️ Файл уже обработан: {file_path}")
                return
            
            self.logger.info(f"🔍 Обработка файла: {file_path} (действие: {change_type})")
            
            # Analyze file path structure
            path_info = self.analyze_file_path(file_path_obj)
            
            if not path_info:
                self.logger.warning(f"⚠️ Файл не соответствует ожидаемой структуре: {file_path}")
                return
            
            self.logger.info(f"📋 Анализ пути:")
            self.logger.info(f"   📅 Дата папки: {path_info['date_folder']}")
            self.logger.info(f"   📁 Исходный путь: {path_info['source_path']}")
            self.logger.info(f"   🎯 Целевой путь: {path_info['target_path']}")
            self.logger.info(f"   📄 Имя файла: {path_info['filename']}")
            self.logger.info(f"   📦 Полный путь в Git: {path_info['full_target']}")
            
            # Sync to GitLab with auto-confirmation
            if change_type == "deleted":
                if self.config.auto_confirm and self.config.auto_delete:
                    self.logger.info(f"🤖 Автоподтверждение удаления: {path_info['filename']}")
                    success = self.delete_from_gitlab(path_info, file_path)
                    if success:
                        self.processed_files.discard(file_path)  # Remove from processed files
                        self.logger.info(f"✅ Файл успешно удален из GitLab!")
                    else:
                        self.logger.error(f"❌ Ошибка удаления файла из GitLab")
                else:
                    self.logger.warning(f"⚠️ Удаление пропущено (автоподтверждение выключено): {path_info['filename']}")
            else:
                if self.config.auto_confirm and self.config.auto_sync:
                    self.logger.info(f"🤖 Автоподтверждение синхронизации: {path_info['filename']}")
                    success = self.sync_to_gitlab(file_path_obj, path_info)
                    if success:
                        self.processed_files.add(file_path)
                        self.logger.info(f"✅ Файл успешно синхронизирован в GitLab!")
                    else:
                        self.logger.error(f"❌ Ошибка синхронизации файла в GitLab")
                else:
                    self.logger.warning(f"⚠️ Синхронизация пропущена (автоподтверждение выключено): {path_info['filename']}")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки файла {file_path}: {e}")
    
    def analyze_file_path(self, file_path: Path) -> Optional[Dict]:
        """Analyze file path to extract date folder and target path with proper path mappings"""
        try:
            parts = file_path.parts
            base_folder = Path(self.config.local_developer_folder).name
            
            # Find base folder index
            base_index = -1
            for i, part in enumerate(parts):
                if part == base_folder:
                    base_index = i
                    break
            
            if base_index == -1:
                return None
            
            # Look for date folder (YYYYMMDD format)
            date_folder = None
            date_index = -1
            
            for i in range(base_index + 1, len(parts)):
                part = parts[i]
                if len(part) == 8 and part.isdigit():
                    # Validate date format
                    try:
                        datetime.strptime(part, '%Y%m%d')
                        date_folder = part
                        date_index = i
                        break
                    except ValueError:
                        # Try DDMMYYYY format as fallback
                        try:
                            datetime.strptime(part, '%d%m%Y')
                            date_folder = part
                            date_index = i
                            break
                        except ValueError:
                            continue
            
            if not date_folder:
                return None
            
            # Extract path after "to" folder
            to_index = -1
            for i in range(date_index + 1, len(parts)):
                if parts[i] == "to":
                    to_index = i
                    break
            
            if to_index == -1:
                return None
            
            # Build source path (everything after "to")
            source_parts = parts[to_index + 1:-1]  # Exclude filename
            filename = parts[-1]
            
            source_path = "/".join(source_parts) if source_parts else ""
            
            # Apply path mappings according to project specifications
            target_path = self.apply_path_mappings(source_path)
            
            return {
                'date_folder': date_folder,
                'source_path': source_path,
                'target_path': target_path,
                'filename': filename,
                'full_target': f"data/{target_path}/{filename}" if target_path else f"data/{filename}"
            }
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка анализа пути файла: {e}")
            return None
    
    def apply_path_mappings(self, source_path: str) -> str:
        """Apply path mappings according to project specifications"""
        if not source_path:
            return ""
        
        # Path mappings (longer matches take precedence)
        mappings = [
            # Full path mappings (check these first for precedence)
            ("usr/local/httpd/htdocs", "htdocs"),
            ("usr/local/asterisk/etc/asterisk/script", "script"),
            ("home/storage/local", "home/storage/local"),
            
            # Shorter path mappings
            ("htdocs", "htdocs"),
            ("script", "script"),
        ]
        
        # Check mappings in order (longer first for precedence)
        for source_pattern, target_pattern in mappings:
            if source_path.startswith(source_pattern):
                # Replace the matching part
                remaining_path = source_path[len(source_pattern):].lstrip('/')
                if remaining_path:
                    return f"{target_pattern}/{remaining_path}"
                else:
                    return target_pattern
        
        # If no mapping found, return as-is under data/
        return source_path
    
    def read_file_content(self, file_path: Path) -> Optional[str]:
        """Read file content with proper encoding detection and retry logic"""
        max_retries = 3
        retry_delay = 0.5  # seconds
        
        for attempt in range(max_retries):
            try:
                # Check if file still exists
                if not file_path.exists():
                    self.logger.error(f"❌ Файл не найден: {file_path}")
                    return None
                
                # Check file size (skip empty files)
                try:
                    file_size = file_path.stat().st_size
                    if file_size == 0:
                        self.logger.warning(f"⚠️ Файл пустой: {file_path}")
                        return ""  # Return empty string for empty files
                except OSError as e:
                    self.logger.error(f"❌ Ошибка получения информации о файле {file_path}: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    return None
                
                # Try to read with different encodings
                encodings_to_try = ['utf-8', 'cp1251', 'cp866', 'latin-1']
                
                for encoding in encodings_to_try:
                    try:
                        with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                            content = f.read()
                            if content or file_size == 0:  # Successfully read or empty file
                                if attempt > 0:
                                    self.logger.info(f"✅ Файл прочитан успешно после {attempt + 1} попыток")
                                return content
                    except UnicodeDecodeError:
                        continue  # Try next encoding
                    except PermissionError:
                        break  # Don't try other encodings if permission denied
                    except Exception as e:
                        self.logger.debug(f"Ошибка чтения с кодировкой {encoding}: {e}")
                        continue
                
                # If all encodings failed, it might be a permission issue
                raise PermissionError(f"Не удалось прочитать файл ни с одной кодировкой")
                
            except PermissionError as e:
                if attempt < max_retries - 1:
                    self.logger.warning(f"⚠️ Ошибка доступа к файлу {file_path}, попытка {attempt + 1}/{max_retries}: {e}")
                    self.logger.info(f"⏳ Ожидание {retry_delay} сек перед повторной попыткой...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    self.logger.error(f"❌ Окончательная ошибка доступа к файлу {file_path}: {e}")
                    self.logger.info(f"💡 Возможные причины:")
                    self.logger.info(f"   • Файл используется другим процессом")
                    self.logger.info(f"   • Недостаточно прав доступа")
                    self.logger.info(f"   • Файл заблокирован антивирусом")
                    return None
            except Exception as e:
                if attempt < max_retries - 1:
                    self.logger.warning(f"⚠️ Ошибка чтения файла {file_path}, попытка {attempt + 1}/{max_retries}: {e}")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    self.logger.error(f"❌ Окончательная ошибка чтения файла {file_path}: {e}")
                    return None
        
        return None
    
    def check_token_permissions(self) -> bool:
        """Check GitLab user permissions"""
        try:
            api_url = "http://10.19.1.20/api/v4/user"
            headers = {'PRIVATE-TOKEN': self.config.gitlab_token}
            
            response = requests.get(api_url, headers=headers)
            
            if response.status_code == 200:
                user_info = response.json()
                self.logger.info(f"👤 Пользователь: {user_info.get('name')} ({user_info.get('username')})")
                self.logger.info(f"🔑 Уровень доступа: {user_info.get('access_level', 'Unknown')}")
                return True
            else:
                self.logger.error(f"❌ Ошибка проверки токена: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка проверки токена: {e}")
            return False
    
    def find_gitlab_project_id(self) -> Optional[str]:
        """Find GitLab project ID by name"""
        try:
            api_url = "http://10.19.1.20/api/v4/projects"
            headers = {'PRIVATE-TOKEN': self.config.gitlab_token}
            
            # Search for patchwatch project
            params = {'search': 'patchwatch', 'simple': 'true'}
            response = requests.get(api_url, headers=headers, params=params)
            
            if response.status_code == 200:
                projects = response.json()
                self.logger.info(f"🔍 Найдено проектов: {len(projects)}")
                
                for project in projects:
                    self.logger.info(f"   📁 Проект: {project.get('name')} (ID: {project.get('id')})")
                    if 'patchwatch' in project.get('name', '').lower():
                        project_id = str(project.get('id'))
                        self.logger.info(f"✅ Найден проект patchwatch с ID: {project_id}")
                        return project_id
                        
                # If not found by name, try first project
                if projects:
                    project_id = str(projects[0].get('id'))
                    self.logger.info(f"⚠️ Используем первый доступный проект (ID: {project_id})")
                    return project_id
            else:
                self.logger.error(f"❌ Ошибка получения списка проектов: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка поиска проекта: {e}")
            
        return None
    
    def sync_to_gitlab(self, file_path: Path, path_info: Dict) -> bool:
        """Sync file to GitLab repository"""
        try:
            self.logger.info(f"🌐 Синхронизация с GitLab...")
            
            # Read file content
            if not file_path.exists():
                self.logger.error(f"❌ Файл не найден: {file_path}")
                return False
            
            content = self.read_file_content(file_path)
            if content is None:
                return False
            
            # Check token permissions first
            if not hasattr(self, '_token_checked'):
                self.logger.info(f"🔍 Проверяем разрешения пользователя...")
                self.check_token_permissions()
                self._token_checked = True
            
            self.logger.info(f"📊 Анализ файла:")
            self.logger.info(f"   📁 Исходный файл: {file_path}")
            self.logger.info(f"   🎯 Целевой путь: {path_info['full_target']}")
            self.logger.info(f"   📝 Размер: {len(content)} символов")
            self.logger.info(f"   📅 Дата папки: {path_info['date_folder']}")
            
            # Find correct project ID
            project_id = self.find_gitlab_project_id()
            if not project_id:
                project_id = self.config.gitlab_project_id
                self.logger.warning(f"⚠️ Не удалось найти проект, используем ID: {project_id}")
            
            # Check project permissions
            project_api_url = f"http://10.19.1.20/api/v4/projects/{project_id}"
            headers = {'PRIVATE-TOKEN': self.config.gitlab_token}
            project_response = requests.get(project_api_url, headers=headers)
            
            if project_response.status_code == 200:
                project_info = project_response.json()
                permissions = project_info.get('permissions', {})
                project_access = permissions.get('project_access') or {}
                group_access = permissions.get('group_access') or {}
                
                self.logger.info(f"📁 Проект: {project_info.get('name')}")
                
                project_level = project_access.get('access_level', 'None')
                group_level = group_access.get('access_level', 'None')
                
                self.logger.info(f"🔑 Уровень доступа к проекту: {project_level}")
                self.logger.info(f"🔑 Уровень доступа к группе: {group_level}")
                
                # GitLab access levels: 10=Guest, 20=Reporter, 30=Developer, 40=Maintainer, 50=Owner
                max_access = max(
                    project_level if isinstance(project_level, int) else 0,
                    group_level if isinstance(group_level, int) else 0
                )
                
                if max_access < 30:  # Need at least Developer (30) for repository write
                    self.logger.warning(f"⚠️ Недостаточные разрешения! Нужен уровень 30+ (Developer), а у вас: {max_access}")
                    self.logger.info(f"📄 Уровни доступа GitLab: 10=Guest, 20=Reporter, 30=Developer, 40=Maintainer, 50=Owner")
                else:
                    self.logger.info(f"✅ Достаточные разрешения для записи в репозиторий")
            
            # Prepare GitLab API request with token authentication
            api_base_url = "http://10.19.1.20"  # Clean base URL
            file_path_encoded = path_info['full_target'].replace('/', '%2F')
            api_url = f"{api_base_url}/api/v4/projects/{project_id}/repository/files/{file_path_encoded}"
            
            headers = {
                'PRIVATE-TOKEN': self.config.gitlab_token,
                'Content-Type': 'application/json'
            }
            
            self.logger.info(f"🔗 GitLab API URL: {api_url}")
            
            # Prepare basic data for GitLab API
            import base64
            
            data = {
                'branch': 'main',
                'content': base64.b64encode(content.encode('utf-8')).decode('utf-8'),
                'encoding': 'base64',
                'commit_message': '',  # Will be set later based on operation
                'author_name': self.config.git_author_name,
                'author_email': self.config.git_author_email
            }
            
            # Check if file exists and validate branch
            try:
                # First check if main branch exists
                branch_url = f"{api_base_url}/api/v4/projects/{project_id}/repository/branches/main"
                branch_response = requests.get(branch_url, headers=headers)
                
                if branch_response.status_code != 200:
                    self.logger.warning(f"⚠️ Main branch не найден, попробуем master или создадим файл")
                    # Try with master branch
                    data['branch'] = 'master'
                    
                response = requests.get(api_url, headers=headers, params={'ref': data['branch']})
                file_exists = response.status_code == 200
                
            except Exception as e:
                self.logger.warning(f"⚠️ Не удалось проверить существование файла: {e}")
                file_exists = False
            
            # Generate improved commit message based on file operation
            if file_exists:
                commit_title = f"✏️ Update {path_info['filename']} from {path_info['date_folder']} via PatchWatch"
                commit_body = f"""📂 {file_path.parent}
📦 {path_info['full_target']}
🤖 via PatchWatch ({path_info['date_folder']})"""
                data['commit_message'] = f"{commit_title}\n\n{commit_body}"
                self.logger.info(f"📝 Обновление существующего файла в ветке {data['branch']}")
            else:
                commit_title = f"➕ Add {path_info['filename']} from {path_info['date_folder']} via PatchWatch"
                commit_body = f"""📂 {file_path.parent}
📦 {path_info['full_target']}
🤖 via PatchWatch ({path_info['date_folder']})"""
                data['commit_message'] = f"{commit_title}\n\n{commit_body}"
                self.logger.info(f"📄 Создание нового файла в ветке {data['branch']}")
            
            # Send request to GitLab
            if file_exists:
                response = requests.put(api_url, headers=headers, json=data)
            else:
                response = requests.post(api_url, headers=headers, json=data)
            
            if response.status_code in [200, 201]:
                self.logger.info(f"✅ Файл успешно синхронизирован с GitLab!")
                self.logger.info(f"🌐 Путь в GitLab: {path_info['full_target']}")
                self.logger.info(f"📝 Коммит: {commit_title}...")
                
                # Also create local backup
                sync_dir = Path("synced_to_gitlab")
                sync_dir.mkdir(exist_ok=True)
                target_file = sync_dir / path_info['full_target']
                target_file.parent.mkdir(parents=True, exist_ok=True)
                
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                backup_content = f"""# Synced to GitLab via PatchWatch
# Local source file: {file_path}
# GitLab target path: {path_info['full_target']}
# Date folder: {path_info['date_folder']}
# Target directory: {path_info['target_path']}
# Sync timestamp: {timestamp}
# Author: {self.config.git_author_name} <{self.config.git_author_email}>
# Commit: {data['commit_message'].split(chr(10))[0]}

{content}"""
                
                with open(target_file, 'w', encoding='utf-8') as f:
                    f.write(backup_content)
                
                self.logger.info(f"📋 Локальная копия: {target_file}")
                
                return True
            else:
                self.logger.error(f"❌ Ошибка GitLab API: {response.status_code}")
                self.logger.error(f"   Ответ: {response.text[:500]}...")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка синхронизации с GitLab: {e}")
            return False
    
    def delete_from_gitlab(self, path_info: Dict, local_file_path: Optional[str] = None) -> bool:
        """Delete file from GitLab repository"""
        try:
            self.logger.info(f"🗑️ Удаление файла из GitLab...")
            
            # Check token permissions first
            if not hasattr(self, '_token_checked'):
                self.logger.info(f"🔍 Проверяем разрешения пользователя...")
                self.check_token_permissions()
                self._token_checked = True
            
            self.logger.info(f"📊 Анализ удаляемого файла:")
            self.logger.info(f"   🎯 Целевой путь: {path_info['full_target']}")
            self.logger.info(f"   📅 Дата папки: {path_info['date_folder']}")
            
            # Find correct project ID
            project_id = self.find_gitlab_project_id()
            if not project_id:
                project_id = self.config.gitlab_project_id
                self.logger.warning(f"⚠️ Не удалось найти проект, используем ID: {project_id}")
            
            # Prepare GitLab API request
            api_base_url = "http://10.19.1.20"  # Clean base URL
            file_path_encoded = path_info['full_target'].replace('/', '%2F')
            api_url = f"{api_base_url}/api/v4/projects/{project_id}/repository/files/{file_path_encoded}"
            
            headers = {
                'PRIVATE-TOKEN': self.config.gitlab_token,
                'Content-Type': 'application/json'
            }
            
            self.logger.info(f"🔗 GitLab API URL: {api_url}")
            
            # Check if file exists in GitLab first
            try:
                # Try main branch first
                check_response = requests.get(api_url, headers=headers, params={'ref': 'main'})
                
                if check_response.status_code == 404:
                    # Try master branch
                    check_response = requests.get(api_url, headers=headers, params={'ref': 'master'})
                    branch = 'master'
                else:
                    branch = 'main'
                
                if check_response.status_code == 404:
                    self.logger.warning(f"⚠️ Файл не найден в GitLab: {path_info['full_target']}")
                    self.logger.info(f"✅ Файл уже удален или не существовал в GitLab")
                    
                    # Remove from local backup if exists
                    sync_dir = Path("synced_to_gitlab")
                    backup_file = sync_dir / path_info['full_target']
                    if backup_file.exists():
                        backup_file.unlink()
                        self.logger.info(f"📋 Локальная копия удалена: {backup_file}")
                    
                    return True
                    
                elif check_response.status_code == 200:
                    self.logger.info(f"📋 Файл найден в ветке {branch}, продолжаем удаление")
                else:
                    self.logger.error(f"❌ Ошибка проверки существования файла: {check_response.status_code}")
                    return False
                    
            except Exception as e:
                self.logger.error(f"❌ Ошибка проверки существования файла: {e}")
                return False
            
            # Prepare improved deletion commit message
            commit_title = f"🗑️ Delete {path_info['filename']} from {path_info['date_folder']} via PatchWatch"
            
            if local_file_path:
                local_display_path = Path(local_file_path).parent
            else:
                # Reconstruct local path from date folder structure
                local_display_path = f"[base_folder]/{path_info['date_folder']}/to/{path_info.get('source_path', path_info.get('target_path', ''))}"
            
            commit_body = f"""📂 {local_display_path}
📦 {path_info['full_target']}
🤖 via PatchWatch ({path_info['date_folder']})"""
            
            data = {
                'branch': branch,
                'commit_message': f"{commit_title}\n\n{commit_body}",
                'author_name': self.config.git_author_name,
                'author_email': self.config.git_author_email
            }
            
            # Send DELETE request to GitLab
            response = requests.delete(api_url, headers=headers, json=data)
            
            if response.status_code in [200, 204]:
                self.logger.info(f"✅ Файл успешно удален из GitLab!")
                self.logger.info(f"🌍 Путь в GitLab: {path_info['full_target']}")
                self.logger.info(f"📝 Коммит: {commit_title}")
                
                # Remove local backup if exists
                sync_dir = Path("synced_to_gitlab")
                backup_file = sync_dir / path_info['full_target']
                if backup_file.exists():
                    backup_file.unlink()
                    self.logger.info(f"📋 Локальная копия удалена: {backup_file}")
                    
                    # Remove empty parent directories
                    try:
                        parent_dir = backup_file.parent
                        while parent_dir != sync_dir and parent_dir.exists():
                            if not any(parent_dir.iterdir()):  # Directory is empty
                                parent_dir.rmdir()
                                self.logger.debug(f"📁 Пустая папка удалена: {parent_dir}")
                                parent_dir = parent_dir.parent
                            else:
                                break
                    except Exception as e:
                        self.logger.debug(f"⚠️ Не удалось очистить пустые папки: {e}")
                
                return True
            else:
                self.logger.error(f"❌ Ошибка GitLab API при удалении: {response.status_code}")
                self.logger.error(f"   Ответ: {response.text[:500]}...")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка удаления файла из GitLab: {e}")
            return False
    
    def get_status(self) -> Dict:
        """Get current monitoring status"""
        return {
            "running": self.is_running,
            "monitored_folder": self.config.local_developer_folder,
            "processed_files_count": len(self.processed_files),
            "gitlab_url": self.config.gitlab_url
        }


def load_monitoring_config() -> MonitoringConfig:
    """Load monitoring configuration"""
    config_file = Path("working_config.json")
    
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return MonitoringConfig(
                    local_developer_folder=data.get('local_developer_folder', str(Path.cwd() / 'test_asterisk_pbx')),
                    gitlab_url=data.get('gitlab_url', 'http://10.19.1.20/Automatization/patchwatch'),
                    gitlab_token=data.get('gitlab_token', 'glpat-iU4i1onU2dQY4k-UryFT'),
                    gitlab_project_id=data.get('gitlab_project_id', '92'),
                    git_author_name=data.get('git_author_name', 'Андрей Комаров'),
                    git_author_email=data.get('git_author_email', 'prostopil@yandex.ru'),
                    auto_confirm=data.get('auto_confirm', True),
                    auto_sync=data.get('auto_sync', True),
                    auto_delete=data.get('auto_delete', True)
                )
        except Exception as e:
            print(f"Warning: Could not load config: {e}")
    
    # Return default config with auto-confirmation enabled
    return MonitoringConfig(
        local_developer_folder=str(Path.cwd() / 'test_asterisk_pbx'),
        auto_confirm=True,
        auto_sync=True,
        auto_delete=True
    )


def main():
    """Main entry point for monitoring service"""
    print("🎯 PatchWatch Monitoring Service")
    print("=" * 50)
    
    # Load configuration
    config = load_monitoring_config()
    
    # Create monitoring service
    service = PatchWatchMonitoringService(config)
    
    # Start monitoring
    if service.start_monitoring():
        try:
            print("\n✅ Мониторинг запущен успешно!")
            print("📁 Отслеживаемая папка:", config.local_developer_folder)
            print("🌐 GitLab URL:", config.gitlab_url)
            print("\n💡 Создайте файл в структуре:")
            print("   [папка]/YYYYMMDD/to/htdocs/api/analog_numbers/filename.txt")
            print("\n🔄 Нажмите Ctrl+C для остановки...")
            
            # Keep running until interrupted
            while service.is_running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n🛑 Получен сигнал остановки...")
            service.stop_monitoring()
            print("✅ Мониторинг остановлен")
    else:
        print("❌ Не удалось запустить мониторинг")


if __name__ == "__main__":
    main()