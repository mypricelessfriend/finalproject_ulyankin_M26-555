"""CLI ValutaTrade Hub. Единственная точка входа для команд."""
from __future__ import annotations

import argparse
import shlex
import sys

from prettytable import PrettyTable

from ..core import usecases
from ..core.models import User


class _Session:
    user: User | None = None


_session = _Session()


def _require_login() -> User:
    if _session.user is None:
        raise PermissionError("Сначала выполните login")
    return _session.user


# команды
def cmd_register(args: argparse.Namespace) -> None:
    try:
        user = usecases.register_user(args.username, args.password)
        print(
            f"Пользователь '{user.username}' зарегистрирован (id={user.user_id}). "
            f"Войдите: login --username {user.username} --password ****"
        )
    except ValueError as exc:
        print(f"Ошибка: {exc}")


def cmd_login(args: argparse.Namespace) -> None:
    try:
        user = usecases.authenticate(args.username, args.password)
        _session.user = user
        print(f"Вы вошли как '{user.username}'")
    except ValueError as exc:
        print(f"Ошибка: {exc}")


def cmd_show_portfolio(args: argparse.Namespace) -> None:
    try:
        user = _require_login()
    except PermissionError as exc:
        print(exc)
        return

    base = (args.base or "USD").upper()
    if not usecases.is_known_currency(base):
        print(f"Неизвестная базовая валюта '{base}'")
        return

    portfolio = usecases.load_portfolio(user)
    wallets = portfolio.wallets
    if not wallets:
        print("Портфель пуст. Купите валюту: buy --currency USD --amount 100")
        return

    table = PrettyTable()
    table.field_names = ["Валюта", "Баланс", f"Стоимость ({base})"]
    table.align = "r"
    total = 0.0
    for code, wallet in wallets.items():
        try:
            rate, _ = usecases.get_rate(code, base)
            value = wallet.balance * rate
            total += value
            table.add_row([code, f"{wallet.balance:.4f}", f"{value:,.2f}"])
        except LookupError:
            table.add_row([code, f"{wallet.balance:.4f}", "—"])
    print(f"Портфель пользователя '{user.username}' (база: {base}):")
    print(table)
    print(f"ИТОГО: {total:,.2f} {base}")


def cmd_buy(args: argparse.Namespace) -> None:
    try:
        user = _require_login()
        res = usecases.buy_currency(user, args.currency, args.amount)
    except (PermissionError, ValueError, TypeError) as exc:
        print(f"Ошибка: {exc}")
        return
    rate = f"{res['rate']:.2f}" if res["rate"] else "?"
    print(f"Покупка выполнена: {res['amount']:.4f} {res['currency']} "
          f"по курсу {rate} USD/{res['currency']}")
    print("Изменения в портфеле:")
    print(f"- {res['currency']}: было {res['before']:.4f} → стало {res['after']:.4f}")
    if res["cost_usd"] is not None:
        print(f"Оценочная стоимость покупки: {res['cost_usd']:,.2f} USD")


def cmd_sell(args: argparse.Namespace) -> None:
    try:
        user = _require_login()
        res = usecases.sell_currency(
            user, args.currency, args.amount, skip_confirm=args.yes
        )
    except (PermissionError, ValueError, TypeError) as exc:
        print(f"Ошибка: {exc}")
        return
    if res is None:  # отменено confirm_action
        return
    rate = f"{res['rate']:.2f}" if res["rate"] else "?"
    print(f"Продажа выполнена: {res['amount']:.4f} {res['currency']} "
          f"по курсу {rate} USD/{res['currency']}")
    print("Изменения в портфеле:")
    print(f"- {res['currency']}: было {res['before']:.4f} → стало {res['after']:.4f}")
    if res["revenue_usd"] is not None:
        print(f"Оценочная выручка: {res['revenue_usd']:,.2f} USD")


def cmd_get_rate(args: argparse.Namespace) -> None:
    try:
        frm, to = args.from_.upper(), args.to.upper()
        rate, ts = usecases.get_rate(frm, to)
    except (ValueError, LookupError) as exc:
        print(f"Ошибка: {exc}")
        return
    print(f"Курс {frm}→{to}: {rate:.8g} "
          f"(обновлено: {ts.strftime('%Y-%m-%d %H:%M:%S')})")
    try:
        reverse, _ = usecases.get_rate(to, frm)
        print(f"Обратный курс {to}→{frm}: {reverse:.8g}")
    except LookupError:
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
    print("ValutaTrade Hub CLI. Команды: register, login, show-portfolio, "
          "buy, sell, get-rate. 'help' — справка, 'exit' — выход.")
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
    if len(sys.argv) > 1:
        run_argv(sys.argv[1:])
    else:
        interactive_loop()