"""CLI ValutaTrade Hub. Единственная точка входа для команд."""
from __future__ import annotations

import argparse
import shlex
import sys

from prettytable import PrettyTable

from ..core import usecases
from ..core.currencies import get_currency
from ..core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    ValutaTradeError,
)
from ..core.models import User


class _Session:
    user: User | None = None


_session = _Session()


def _require_login() -> User:
    if _session.user is None:
        raise PermissionError("Сначала выполните login")
    return _session.user


def _fmt_rate(rate: float) -> str:
    if rate == 0:
        return "0"
    if rate < 0.001:
        return f"{rate:.8f}"
    if rate < 1:
        return f"{rate:.6f}".rstrip("0").rstrip(".")
    return f"{rate:.4f}".rstrip("0").rstrip(".")


def _print_currency_not_found(exc: CurrencyNotFoundError, hint: str = "get-rate") -> None:
    supported = ", ".join(usecases.known_currencies())
    print(exc)
    print(f"Подсказка: help {hint}; поддерживаемые коды: {supported}")


def _print_api_error(exc: ApiRequestError) -> None:
    print(exc)
    print("Повторите попытку позже или проверьте сетевое подключение.")


# команды
def cmd_register(args: argparse.Namespace) -> None:
    try:
        user = usecases.register_user(args.username, args.password)
        print(
            f"Пользователь '{user.username}' зарегистрирован (id={user.user_id}). "
            f"Войдите: login --username {user.username} --password ****"
        )
    except ValueError as exc:
        print(exc)


def cmd_login(args: argparse.Namespace) -> None:
    try:
        user = usecases.authenticate(args.username, args.password)
        _session.user = user
        print(f"Вы вошли как '{user.username}'")
    except ValueError as exc:
        print(exc)


def cmd_show_portfolio(args: argparse.Namespace) -> None:
    try:
        user = _require_login()
    except PermissionError as exc:
        print(exc)
        return

    base = (args.base or "USD").upper()
    try:
        get_currency(base)
    except CurrencyNotFoundError as exc:
        _print_currency_not_found(exc, hint="show-portfolio")
        return

    portfolio = usecases.load_portfolio(user)
    wallets = portfolio.wallets
    if not wallets:
        print("Портфель пуст. Купите валюту: buy --currency USD --amount 100")
        return

    def rate_getter(code: str, base_cur: str):
        try:
            return usecases.get_rate(code, base_cur)[0]
        except (CurrencyNotFoundError, ApiRequestError):
            return None

    table = PrettyTable()
    table.field_names = ["Валюта", "Баланс", f"Стоимость ({base})"]
    table.align = "r"
    for code, wallet in wallets.items():
        rate = rate_getter(code, base)
        if rate is None:
            table.add_row([code, f"{wallet.balance:.4f}", "—"])
        else:
            table.add_row(
                [code, f"{wallet.balance:.4f}", f"{wallet.balance * rate:,.2f}"]
            )

    print(f"Портфель пользователя '{user.username}' (база: {base}):")
    print(table)

    try:
        total = portfolio.get_total_value(base, rate_getter=rate_getter)
        print(f"ИТОГО: {total:,.2f} {base}")
    except LookupError:
        print("ИТОГО: не удалось посчитать (нет курсов для некоторых валют)")


def cmd_buy(args: argparse.Namespace) -> None:
    try:
        user = _require_login()
        res = usecases.buy_currency(user.user_id, args.currency, args.amount)
    except PermissionError as exc:
        print(exc)
        return
    except CurrencyNotFoundError as exc:
        _print_currency_not_found(exc, hint="buy")
        return
    except ApiRequestError as exc:
        _print_api_error(exc)
        return
    except (ValueError, TypeError) as exc:
        print(exc)
        return
    except ValutaTradeError as exc:
        print(exc)
        return

    base = res.get("base", "USD")
    if res["rate"] is not None:
        print(
            f"Покупка выполнена: {res['amount']:.4f} {res['currency']} "
            f"по курсу {res['rate']:.2f} {base}/{res['currency']}"
        )
    else:
        print(f"Покупка выполнена: {res['amount']:.4f} {res['currency']}")
        print(f"Не удалось получить курс для {res['currency']}→{base}")

    print("Изменения в портфеле:")
    print(f"- {res['currency']}: было {res['before']:.4f} → стало {res['after']:.4f}")

    if res.get("cost_base") is not None:
        print(f"Оценочная стоимость покупки: {res['cost_base']:,.2f} {base}")
    if res.get("base_charged") is not None:
        print(f"Списано с {base}: {res['base_charged']:,.2f} {base}")


def cmd_sell(args: argparse.Namespace) -> None:
    try:
        user = _require_login()
        res = usecases.sell_currency(
            user.user_id, args.currency, args.amount, skip_confirm=args.yes
        )
    except PermissionError as exc:
        print(exc)
        return
    except CurrencyNotFoundError as exc:
        _print_currency_not_found(exc, hint="sell")
        return
    except InsufficientFundsError as exc:
        print(exc)
        return
    except ApiRequestError as exc:
        _print_api_error(exc)
        return
    except (ValueError, TypeError) as exc:
        print(exc)
        return
    except ValutaTradeError as exc:
        print(exc)
        return

    if res is None:  # отменено confirm_action
        return

    base = res.get("base", "USD")
    if res["rate"] is not None:
        print(
            f"Продажа выполнена: {res['amount']:.4f} {res['currency']} "
            f"по курсу {res['rate']:.2f} {base}/{res['currency']}"
        )
    else:
        print(f"Продажа выполнена: {res['amount']:.4f} {res['currency']}")
        print(f"Не удалось получить курс для {res['currency']}→{base}")

    print("Изменения в портфеле:")
    print(f"- {res['currency']}: было {res['before']:.4f} → стало {res['after']:.4f}")

    if res.get("revenue_base") is not None:
        print(f"Оценочная выручка: {res['revenue_base']:,.2f} {base}")
    if res.get("base_credited") is not None:
        print(f"Начислено на {base}: {res['base_credited']:,.2f} {base}")


def cmd_get_rate(args: argparse.Namespace) -> None:
    try:
        frm, to = args.from_.upper(), args.to.upper()
        rate, ts = usecases.get_rate(frm, to)
    except CurrencyNotFoundError as exc:
        _print_currency_not_found(exc, hint="get-rate")
        return
    except ApiRequestError as exc:
        _print_api_error(exc)
        return
    except ValueError as exc:
        print(exc)
        return

    print(
        f"Курс {frm}→{to}: {_fmt_rate(rate)} "
        f"(обновлено: {ts.strftime('%Y-%m-%d %H:%M:%S')})"
    )
    try:
        reverse, _ = usecases.get_rate(to, frm)
        print(f"Обратный курс {to}→{frm}: {_fmt_rate(reverse)}")
    except (CurrencyNotFoundError, ApiRequestError):
        pass


# парсер
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="valutatrade", description="ValutaTrade Hub — симулятор валютного кошелька"
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("register", help="зарегистрировать нового пользователя")
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("login", help="войти в систему")
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("show-portfolio", help="показать портфель")
    p.add_argument("--base", default="USD", help="базовая валюта (по умолчанию USD)")
    p.set_defaults(func=cmd_show_portfolio)

    p = sub.add_parser("buy", help="купить валюту")
    p.add_argument("--currency", required=True)
    p.add_argument("--amount", type=float, required=True)
    p.set_defaults(func=cmd_buy)

    p = sub.add_parser("sell", help="продать валюту")
    p.add_argument("--currency", required=True)
    p.add_argument("--amount", type=float, required=True)
    p.add_argument("--yes", "-y", action="store_true", help="без подтверждения")
    p.set_defaults(func=cmd_sell)

    p = sub.add_parser("get-rate", help="получить курс валюты")
    p.add_argument("--from", dest="from_", required=True)
    p.add_argument("--to", required=True)
    p.set_defaults(func=cmd_get_rate)

    return parser


# точка входа
def run_argv(argv: list[str]) -> None:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return
    if not getattr(args, "func", None):
        parser.print_help()
        return
    args.func(args)


def run_command(line: str) -> None:
    try:
        tokens = shlex.split(line)
    except ValueError as exc:
        print(f"Ошибка разбора команды: {exc}")
        return
    if tokens:
        run_argv(tokens)


def interactive_loop() -> None:
    print(
        "ValutaTrade Hub CLI. Команды: register, login, show-portfolio, "
        "buy, sell, get-rate. 'help' — справка, 'exit' — выход."
    )
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            break
        if line.lower() == "help":
            build_parser().print_help()
            continue
        run_command(line)


def main() -> None:
    from ..logging_config import setup_logging
    setup_logging()
    if len(sys.argv) > 1:
        run_argv(sys.argv[1:])
    else:
        interactive_loop()