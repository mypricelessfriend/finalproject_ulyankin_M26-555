# ValutaTrade Hub

**ValutaTrade Hub** — комплексная платформа для отслеживания и симуляции торговли фиатными валютами и криптовалютами.

Проект состоит из двух основных сервисов:

1. **Core Service** — консольное приложение (CLI) для управления пользователями, виртуальными кошельками и симуляции сделок.
2. **Parser Service** — фоновый микросервис для сбора актуальных курсов валют из внешних API и кэширования их в локальное хранилище.

## Технологии

- Python 3.10+
- `uv` — управление зависимостями и сборка пакета
- Ruff — линтинг и форматирование кода (стандарт PEP 8)
- PrettyTable — форматированный вывод таблиц в CLI
- Requests — HTTP-клиенты для Parser Service
- Стандартная библиотека: `json`, `argparse`, `logging`, `hashlib`, `shlex`, `threading`, `dataclasses`

## Структура проекта

```text
finalproject_ulyankin_M26-555/
├── data/                         # JSON-хранилище (создается автоматически)
│   ├── users.json                # Пользователи
│   ├── portfolios.json           # Кошельки пользователей
│   ├── rates.json                # Кэш последних курсов (для Core)
│   └── exchange_rates.json       # История всех замеров (для Parser)
├── logs/                         # Логи (создаются автоматически)
│   ├── actions.log               # Лог операций Core (BUY/SELL/LOGIN)
│   └── parser.log                # Лог работы Parser Service
├── valutatrade_hub/              # Исходный код пакета
│   ├── core/                     # Бизнес-логика и модели (User, Wallet, Portfolio)
│   ├── infra/                    # Инфраструктура (синглтоны SettingsLoader, DatabaseManager)
│   ├── parser_service/           # Микросервис парсинга (API-клиенты, Scheduler, Storage)
│   ├── cli/                      # Командный интерфейс (argparse)
│   ├── decorators.py             # Декоратор @log_action
│   └── logging_config.py         # Настройка логирования и ротации
├── main.py                       # Точка входа
├── pyproject.toml                # Конфигурация проекта и зависимости
└── README.md
```

## Установка и запуск

Клонируйте репозиторий и перейдите в папку проекта:

```bash
git clone <repo-url>
cd finalproject_ulyankin_M26-555
```

Установите зависимости и соберите пакет с помощью `uv`:

```bash
uv sync
```

Запустите CLI:

```bash
uv run valutatrade
```

Также доступен запуск через:

```bash
uv run python main.py
```

## Переменные окружения

Для получения курсов фиатных валют используется [ExchangeRate-API](https://www.exchangerate-api.com/).  
API-ключ передается строго через переменные окружения и не хранится в коде.

### Linux / macOS

```bash
export EXCHANGERATE_API_KEY="ваш_ключ_из_личного_кабинета"
```

### Windows (PowerShell)

```powershell
$env:EXCHANGERATE_API_KEY = "ваш_ключ_из_личного_кабинета"
```

Ключ можно получить бесплатно на [официальном сайте ExchangeRate-API](https://www.exchangerate-api.com/).

Для **CoinGecko** API-ключ не требуется.

## Команды CLI

| Команда | Описание | Аргументы |
|---|---|---|
| `register` | Регистрация нового пользователя | `--username`, `--password` |
| `login` | Вход в систему | `--username`, `--password` |
| `show-portfolio` | Показать балансы и общую стоимость | `--base` (по умолчанию `USD`) |
| `buy` | Купить валюту | `--currency`, `--amount` |
| `sell` | Продать валюту | `--currency`, `--amount`, `--yes` (без подтверждения) |
| `get-rate` | Получить курс из кэша | `--from`, `--to` |
| `update-rates` | Запустить Parser Service и обновить курсы | `--source` (`coingecko` / `exchangerate`) |
| `show-rates` | Показать курсы из кэша | `--currency`, `--top`, `--base` |

## Примеры использования

```bash
uv run valutatrade register --username alice --password 1234
uv run valutatrade login --username alice --password 1234
uv run valutatrade buy --currency BTC --amount 0.05
uv run valutatrade show-portfolio
uv run valutatrade update-rates
uv run valutatrade show-rates --top 2
```

## Архитектура и особенности

- **ООП и инкапсуляция** — модели `User`, `Wallet` и `Portfolio` используют приватные атрибуты (`_balance`, `_user_id`) с доступом через `@property` и валидацией.
- **Безопасность** — пароли хешируются с использованием SHA-256 и уникальной соли (`secrets`).
- **Исключения** — в ядре реализованы доменные исключения (`InsufficientFundsError`, `CurrencyNotFoundError`, `ApiRequestError`), которые перехватываются в CLI и выводятся пользователю в понятном виде.
- **Синглтоны** — `SettingsLoader` (читает `pyproject.toml`) и `DatabaseManager` (атомарная запись JSON через `tmp -> rename`) гарантируют единое состояние приложения.
- **TTL-кэш** — курсы в `rates.json` имеют время жизни (`RATES_TTL_SECONDS = 300`). Если данные устарели, Core-сервис инициирует их обновление.
- **Логирование** — ведется в два файла с ротацией (`RotatingFileHandler`). Декоратор `@log_action` фиксирует операции `BUY`, `SELL` и `LOGIN` с указанием балансов до и после операции.


## Демонстрация работы

Записи терминала в формате asciinema (кликните по превью, чтобы открыть полную запись).

### Core Service — полный цикл

[![Core Service demo](https://asciinema.org/a/oMZDATlVDblK7zUY.svg)](https://asciinema.org/a/oMZDATlVDblK7zUY)

Показано: регистрация (`register`) → вход (`login`) → покупка (`buy --currency BTC --amount 0.05`) → продажа (`sell --currency BTC --amount 0.01`) → портфель (`show-portfolio`) → курс (`get-rate --from BTC --to USD`).

### Parser Service и обработка ошибок

[![Parser Service demo](https://asciinema.org/a/2E5fJCxcuo4Jlm5D.svg)](https://asciinema.org/a/2E5fJCxcuo4Jlm5D)

Показано: недостаточно средств (`InsufficientFundsError`) → неизвестная валюта в `get-rate` и `buy` (`CurrencyNotFoundError`) → обновление курсов (`update-rates`) → работа с кэшем (`show-rates`, `--top 2`, `--currency RUB`).