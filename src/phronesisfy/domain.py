"""Regras puras, independentes de Telegram, SQLite e interface."""
from dataclasses import dataclass
from datetime import date, datetime
import re
import unicodedata

MAX_AMOUNT_CENTS = 99_999_999_999
CATEGORIES = {
    "receita": ("salario", "freelance", "outros"),
    "despesa": ("alimentacao", "transporte", "moradia", "saude", "educacao", "lazer", "outros"),
}
LABELS = {"salario": "salário", "alimentacao": "alimentação", "saude": "saúde", "educacao": "educação"}


class ValidationError(ValueError):
    """Entrada que o usuário pode corrigir."""


@dataclass(frozen=True)
class Entry:
    kind: str
    amount_cents: int
    category: str
    description: str
    date: date


@dataclass(frozen=True)
class Transaction(Entry):
    id: int
    created_at: datetime
    telegram_update_id: int | None = None


@dataclass(frozen=True)
class Summary:
    income_cents: int
    expense_cents: int

    @property
    def result_cents(self) -> int:
        return self.income_cents - self.expense_cents


def parse_amount(value: str) -> int:
    # Sem separadores de milhar: 1.250 é ambíguo, 1250,50 é inequívoco.
    if not re.fullmatch(r"[0-9]{1,12}(?:[.,][0-9]{1,2})?", value):
        raise ValidationError("Valor inválido. Use 35,90 ou 35.90, sem separador de milhar.")
    whole, _, fraction = value.replace(",", ".").partition(".")
    amount = int(whole) * 100 + int(fraction.ljust(2, "0") or "0")
    if not 0 < amount <= MAX_AMOUNT_CENTS:
        raise ValidationError("Valor deve ser positivo e até R$ 999.999.999,99.")
    return amount


def parse_initial_balance(value: str) -> int:
    if re.fullmatch(r"-?0+(?:[.,]0{1,2})?", value):
        return 0
    sign = -1 if value.startswith("-") else 1
    return sign * parse_amount(value.removeprefix("-"))


def normalize_category(value: str, kind: str) -> str:
    value = "".join(c for c in unicodedata.normalize("NFD", value.lower()) if not unicodedata.combining(c))
    if kind not in CATEGORIES or value not in CATEGORIES[kind]:
        options = ", ".join(CATEGORIES.get(kind, ()))
        raise ValidationError(f"Categoria inválida para {kind}. Opções: {options}.")
    return value


def validate_entry(entry: Entry) -> Entry:
    if entry.kind not in CATEGORIES:
        raise ValidationError("Tipo deve ser receita ou despesa.")
    if type(entry.amount_cents) is not int or not 0 < entry.amount_cents <= MAX_AMOUNT_CENTS:
        raise ValidationError("Valor inválido em centavos.")
    category = normalize_category(entry.category, entry.kind)
    description = entry.description.strip()
    if not 1 <= len(description) <= 200 or any(unicodedata.category(c).startswith("C") for c in entry.description):
        raise ValidationError("Descrição obrigatória, até 200 caracteres e sem caracteres de controle.")
    if type(entry.date) is not date:
        raise ValidationError("Data inválida.")
    return Entry(entry.kind, entry.amount_cents, category, description, entry.date)


def parse_entry(text: str, kind: str, today: date) -> Entry:
    if kind not in CATEGORIES:
        raise ValidationError("Tipo inválido.")
    head, separator, description = text.partition("|")
    tokens = head.split()
    if tokens and tokens[0].startswith("/"):
        command = tokens.pop(0).split("@", 1)[0]
        if command != {"receita": "/entrada", "despesa": "/saida"}[kind]:
            raise ValidationError("Comando incompatível com o tipo de movimentação.")
    if not separator or len(tokens) not in (2, 3):
        raise ValidationError("Use /entrada 2500,00 salario | Salário ou /saida 35,90 alimentacao @2026-10-01 | Almoço.")
    movement_date = today
    if len(tokens) == 3:
        if not re.fullmatch(r"@[0-9]{4}-[0-9]{2}-[0-9]{2}", tokens[2]):
            raise ValidationError("Data deve ser @AAAA-MM-DD antes de |.")
        try:
            movement_date = date.fromisoformat(tokens[2][1:])
        except ValueError as exc:
            raise ValidationError("Data inexistente. Exemplo: @2026-10-01.") from exc
    return validate_entry(Entry(kind, parse_amount(tokens[0]), tokens[1], description, movement_date))


def validate_month(month: str) -> str:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", month):
        raise ValidationError("Mês deve ser AAAA-MM.")
    try:
        date.fromisoformat(month + "-01")
    except ValueError as exc:
        raise ValidationError("Mês inválido. Use AAAA-MM.") from exc
    return month


def format_brl(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, remainder = divmod(abs(cents), 100)
    return f"{sign}R$ {whole:,}".replace(",", ".") + f",{remainder:02d}"
