# Установка и настройка

## Системные требования

- **Python**: 3.7+ (рекомендуется 3.8+)
- **Операционная система**: Windows 10/11 или Windows Server
- **Доступ к сети**: Доступ к интернету для установки зависимостей
- **Доступ к GitLab**: Внутренний сервер GitLab по адресу http://10.19.1.20

## Шаги установки

### 1. Клонирование или копирование проекта

```bash
# Клонируйте репозиторий или скопируйте папку проекта
```

### 2. Установка зависимостей

```bash
cd patchwatch
pip install -r requirements.txt
```

### 3. Настройка системы

Создайте или отредактируйте `working_config.json` с соответствующими настройками:

```json
{
  "local_developer_folder": "C:\\path\\to\\your\\developer\\folder",
  "gitlab_url": "http://10.19.1.20/Automatization/patchwatch",
  "gitlab_token": "glpat-your-token-here",
  "gitlab_project_id": "92",
  "git_author_name": "Ваше имя",
  "git_author_email": "your.email@domain.com",
  "auto_confirm": true,
  "auto_sync": true,
  "auto_delete": true
}
```

### 4. Запуск системы

Выберите один из режимов работы:
- Веб-интерфейс: `python web_interface.py`
- Автономный режим: `python autonomous_monitor.py`