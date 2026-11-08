"""Доменные классы: User, Wallet, Portfolio."""

from __future__ import annotations

from datetime import datetime

from .currencies import Currency, get_currency
from .exceptions import InsufficientFundsError
from .utils import hash_password, new_salt


class User:
    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime | str,
    ) -> None:
        self._user_id: int = int(user_id)
        self._username: str = ""
        self.username = username
        self._hashed_password: str = hashed_password
        self._salt: str = salt
        if isinstance(registration_date, str):
            registration_date = datetime.fromisoformat(registration_date)
        self._registration_date: datetime = registration_date

    # getters/setters
    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        return self._hashed_password

    @property
    def salt(self) -> str:
        return self._salt

    @property
    def registration_date(self) -> datetime:
        return self._registration_date

    @property
    def password(self) -> str:
        """Возвращает хэш (не plain). Сеттер — для валидации и смены пароля."""
        return self._hashed_password

    @password.setter
    def password(self, value: str) -> None:
        if not isinstance(value, str) or len(value) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")
        self.change_password(value)

    # методы
    def get_user_info(self) -> str:
        return (
            f"ID: {self._user_id}, Имя: {self._username}, "
            f"Дата регистрации: {self._registration_date.isoformat()}"
        )

    def verify_password(self, password: str) -> bool:
        return hash_password(password, self._salt) == self._hashed_password

    def change_password(self, new_password: str) -> None:
        if not isinstance(new_password, str) or len(new_password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")
        self._salt = new_salt()
        self._hashed_password = hash_password(new_password, self._salt)

    def to_dict(self) -> dict:
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
        }

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> User:
        if not isinstance(password, str) or len(password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")
        salt = new_salt()
        return cls(user_id, username, hash_password(password, salt), salt, datetime.now())

    @classmethod
    def from_dict(cls, data: dict) -> User:
        return cls(
            data["user_id"],
            data["username"],
            data["hashed_password"],
            data["salt"],
            data["registration_date"],
        )

    def __repr__(self) -> str:
        return f"User(id={self._user_id}, username={self._username!r})"


class Wallet:
    def __init__(self, currency_code: str, balance: float = 0.0) -> None:
        # валидация кода через реестр валют — бросает CurrencyNotFoundError
        self._currency: Currency = get_currency(currency_code)
        self._balance: float = 0.0
        self.balance = balance

    @property
    def currency_code(self) -> str:
        return self._currency.code

    @property
    def currency(self) -> Currency:
        return self._currency

    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, value) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        self._validate_amount(amount, "пополнения")
        self._balance += float(amount)

    def withdraw(self, amount: float) -> None:
        self._validate_amount(amount, "снятия")
        if amount > self._balance:
            raise InsufficientFundsError(self._balance, float(amount), self.currency_code)
        self._balance -= float(amount)

    def get_balance_info(self) -> str:
        return f"{self.currency_code}: {self._balance:.4f}"

    def to_dict(self) -> dict:
        return {"currency_code": self.currency_code, "balance": self._balance}

    @classmethod
    def from_dict(cls, data: dict) -> Wallet:
        return cls(data["currency_code"], data.get("balance", 0.0))

    @staticmethod
    def _validate_amount(amount: float, kind: str) -> None:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError(f"Сумма {kind} должна быть числом")
        if amount <= 0:
            raise ValueError(f"Сумма {kind} должна быть положительной")

    def __repr__(self) -> str:
        return f"Wallet({self.currency_code}, balance={self._balance})"


class Portfolio:
    def __init__(
        self,
        user_id: int,
        wallets: dict[str, Wallet] | None = None,
        user: User | None = None,
    ) -> None:
        self._user_id: int = int(user_id)
        self._wallets: dict[str, Wallet] = dict(wallets or {})
        self._user: User | None = user

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def user(self) -> User | None:
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        return dict(self._wallets)

    def add_currency(self, currency_code: str) -> Wallet:
        code = get_currency(currency_code).code  # валидация + нормализация
        if code in self._wallets:
            raise ValueError(f"Кошелёк '{code}' уже существует")
        wallet = Wallet(code)
        self._wallets[code] = wallet
        return wallet

    def get_wallet(self, currency_code: str) -> Wallet | None:
        if not isinstance(currency_code, str):
            return None
        return self._wallets.get(currency_code.upper().strip())

    def get_total_value(
        self,
        base_currency: str = "USD",
        rate_getter=None,
    ) -> float:
        base = get_currency(base_currency).code
        getter = rate_getter or _default_rate
        total = 0.0
        for code, wallet in self._wallets.items():
            rate = getter(code, base)
            if rate is None:
                raise LookupError(f"Не удалось получить курс {code}→{base}")
            total += wallet.balance * rate
        return total

    def __repr__(self) -> str:
        return f"Portfolio(user_id={self._user_id}, wallets={list(self._wallets)})"


# фиксированные курсы (fallback, если rate_getter не передан)
exchange_rates = {
    ("USD", "USD"): 1.0,
    ("EUR", "USD"): 1.0786,
    ("GBP", "USD"): 1.27,
    ("BTC", "USD"): 59337.21,
    ("ETH", "USD"): 3720.00,
    ("RUB", "USD"): 0.01016,
}


def _default_rate(frm: str, to: str) -> float | None:
    frm, to = frm.upper(), to.upper()
    if frm == to:
        return 1.0
    if (frm, to) in exchange_rates:
        return exchange_rates[(frm, to)]
    if (to, frm) in exchange_rates:
        return 1.0 / exchange_rates[(to, frm)]
    return None
