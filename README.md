# ValutaTrade Hub

Консольный симулятор валютного кошелька на Python.

Поддерживает регистрацию/вход, виртуальные кошельки по валютам,
покупку/продажу валюты, получение актуального курса с TTL-кэшем,
хранение данных в JSON и единый CLI.

## Стек

- Python ≥ 3.10
- [`uv`](https://docs.astral.sh/uv/) — инициализация, зависимости, запуск
- [`ruff`](https://docs.astral.sh/ruff/) — линтер и форматтер (PEP 8)
- [`prettytable`](https://pypi.org/project/prettytable/) — форматированный вывод таблиц
- Стандартная библиотека: `json`, `shlex`, `hashlib`, `secrets`, `datetime`, `argparse`

## Установка

```bash
git clone <repo-url>
cd finalproject_<фамилия>_<группа>
uv sync