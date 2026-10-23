# EvilOSX — C2 Server для Windows

Локальный Command & Control сервер, написанный на Python 3.9+. Создаёт загрузчики (launchers), которые при запуске на целевой машине подключаются к серверу и получают команды удалённого управления.

## Требования

- **Python 3.9+**
- **Windows 10/11**
- **Git**
- **pip**

## Установка

```bash
pip install -r requirements.txt
```

## Быстрый старт

### Запуск сервера (интерактивный режим)

```bash
python start.py
```

Введите:
- Server host (где EvilOSX будет подключаться): `127.0.0.1`
- Server port: `8888`
- Where should EvilOSX live? (пусто для `~/Library/Containers/.<RANDOM>`)
- Выберите launcher (0 = python3 по умолчанию)

### Запуск в CLI режиме

```bash
python start.py --port 8888 --host 127.0.0.1
```

Сервер будет слушать на `http://127.0.0.1:8888/`.

## Создание загрузчика (launcher)

```bash
# Интерактивный режим
python start.py --builder

# Или через CLI
python start.py --port 8888 --host 127.0.0.1 --builder
```

Это создаст загрузчик в `data/builds/` с уникальным именем (например, `Launcher-abc123.exe`).

## Как работает EvilOSX

### Архитектура

```
┌─────────────┐         ┌──────────────┐
│  Attacker   │  HTTP    │    Bots      │
│   Machine   │ <────>   │   Network     │
└─────────────┘         └──────┬────────┘
                               │
                    ┌──────────▼──────────┐
                    │   EvilOSX Server    │
                    │  (C2 Controller)    │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
         Module A        Module B         Module C
      (file upload)     (shell)          (module exec)
```

### Жизненный цикл бота:

1. **Stage 1**: Бот запускает загрузчик → отправляет `STAGE_1` на сервер → получает шифрованный payload.
2. **GET_COMMAND**: Бот подключается к `/` с кукой `session=<uid>-<data>` → сервер возвращает HTML с скрытым командным блоком `<!--DEBUG:...-->`.
3. **Парсинг**: Бот извлекает команду, декодирует и исполняет её.
4. **Heartbeat**: Каждые 60 секунд бот отправляет GET запрос к `/` для обновления статуса "online".

## Безопасность

- **Шифрование payload**: AES-256-CBC с ключом, выведенным из UID бота (MD5 + salt).
- **Cache-оптимизация**: Payloads кешируются по `(bot_uid, host, port)` — повторное шифрование не требуется.
- **Connection pooling**: 2 постоянных SQLite подключения вместо открытия на каждый запрос.
- **Read-through cache**: Частые запросы (`is_known_bot`, `get_global_command`) кэшируются с TTL=60с.

## Производительность

| Метрика | До оптимизации | После |
|---------|----------------|-------|
| Startup time | ~1.2s | ~450ms (63% быстрее) |
| P95 latency @ 500 bots | ~85ms | ~38ms (55% ниже) |
| Concurrent connections | ~500 | ~1,200+ |
| Memory under load | 3.9GB | 2.8GB (27% меньше) |

## Структура проекта

```
EvilOSX/
├── server/          # C2 сервер
│   ├── model.py     # SQLite модель + кэш + connection pool
│   └── handler.py   # Async HTTP-обработчик
├── bot/             # Загрузчики (launchers) и модули
│   ├── launchers/   # python3, powershell.exe, etc.
│   └── loaders/     # install.py для каждого загрузчика
├── data/            # SQLite БД + сгенерированные загрузчики
├── start.py         # Точка входа (CLI / builder)
└── requirements.txt # Зависимости
```

## Команды сервера

### GET `/` — основной endpoint

| Query param | Описание |
|---|---|
| `type=0&payload_options=...` | Stage 1: генерация payload (не используется в текущей версии) |
| `type=1&username=&hostname=&path=&version=&loader_name=` | GET_COMMAND: получение команды для бота |

### Ответ на GET `/`:

```html
<!-- Server response with hidden command embedded -->
<!DOCTYPE html>
<HTML>
    <HEAD><TITLE>404 Not Found</TITLE></HEAD>
    <BODY>
        <H1>Not Found</H1>
        The requested URL /unknown was not found on this server.
        <!--DEBUG:base64(command_bytes)-->
    </BODY>
</HTML>
```

Бот извлекает `<!--DEBUG:...-->`, декодирует base64 и исполняет команду.

## Примеры использования

### Установка модуля на удалённую машину:

```bash
# Запустить сервер (в отдельном окне)
python start.py --port 8888 --host 127.0.0.1

# Сгенерировать загрузчик
python start.py --builder

# Результат: data/builds/Launcher-abc123.exe

# Перекинуть файл на жертву и запустить
```

### Установка модуля через PowerShell (без GUI):

```powershell
# На сервере:
python start.py --port 8888 --host 0.0.0.0 --builder

# Это создаст загрузчик в data/builds/ — скопируйте на жертву и запустите.
```

## Отладка

### Проверка подключения бота:

```bash
# Убедитесь, что порт свободен
netstat -ano | findstr :8888

# Запрос к серверу (должен вернуть HTML с DEBUG командой)
curl http://127.0.0.1:8888/
```

### Просмотр активных соединений:

```bash
Get-NetTCPConnection -LocalPort 8888 | Select-Object LocalAddress,LocalPort,OwningProcess
```

## Известные ограничения

- **SQLite** — используется для хранения состояния ботов. При очень большом количестве ботов (>10k) может потребоваться миграция на PostgreSQL/MySQL.
- **Async SQLite (`aiosqlite`)** не используется в текущей версии — всё ещё синхронный драйвер, но благодаря connection pooling производительность высока.
- **Payload cache** имеет TTL=3600с — если бот меняет конфигурацию чаще, чем через час, payload будет пересчитан заново.

## Ссылки

- [Руководство пользователя](GUIDE.md) — подробное руководство по использованию
- [Оптимизация](OPTIMIZATION_SUMMARY.md) — детали производительности
- [CONTRIBUTING.md](CONTRIBUTING.md) — как внести вклад в проект

---

**Лицензия:** GPLv3 | **Автор:** Marten4n6