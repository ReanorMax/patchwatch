# Справочник API

## Конечные точки REST API

Веб-интерфейс предоставляет несколько конечных точек REST API:

### Статус системы
- `GET /status`: Получить текущий статус мониторинга

### Управление системой
- `POST /control`: Запустить или остановить мониторинг

### Работа с журналами
- `GET /logs`: Получить записи журнала

### Конфигурация
- `POST /config`: Обновить конфигурацию

### Сканирование
- `POST /scan`: Запустить полное сканирование папки

## Форматы данных

### Запрос на управление системой
```json
{
  "action": "start" | "stop"
}
```

### Ответ о статусе
```json
{
  "status": "running" | "stopped",
  "monitoring": true | false,
  "last_event": "timestamp"
}
```

### Обновление конфигурации
```json
{
  "local_developer_folder": "string",
  "gitlab_url": "string",
  "gitlab_token": "string",
  "gitlab_project_id": "string",
  "git_author_name": "string",
  "git_author_email": "string",
  "auto_confirm": boolean,
  "auto_sync": boolean,
  "auto_delete": boolean
}
```

## Безопасность API

API использует базовую аутентификацию. В текущей реализации аутентификация отсутствует, что представляет собой потенциальную угрозу безопасности. Рекомендуется добавить аутентификацию для защиты управляющих функций.