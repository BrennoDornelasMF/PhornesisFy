from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest

from phronesisfy.domain import ValidationError, format_brl, parse_amount, parse_entry
from phronesisfy.repository import Repository


TODAY = date(2026, 10, 13)


@pytest.mark.parametrize('value,cents', [('35,90', 3590), ('35.90', 3590), ('1', 100), ('0,01', 1), ('12.5', 1250), ('999999999.99', 99999999999)])
def test_parse_amount_exact_integer_cents(value, cents):
    assert parse_amount(value) == cents


@pytest.mark.parametrize('value', ['0', '0,00', '-1', '+1', '1.000,00', '1,000.00', '1.000', '1e3', 'NaN', 'inf', '.5', '1,', '', '1000000000', '1 000', '١٢'])
def test_invalid_amount_rejected(value):
    with pytest.raises(ValidationError):
        parse_amount(value)


def test_entry_parses_explicit_date_and_accent_alias():
    entry = parse_entry('/entrada 2500,00 salário @2026-10-01 | Salário mensal', 'receita', TODAY)
    assert (entry.kind, entry.amount_cents, entry.category, entry.description, entry.date) == ('receita', 250000, 'salario', 'Salário mensal', date(2026, 10, 1))


def test_entry_defaults_to_current_date():
    entry = parse_entry('/saida 35.90 alimentação | Almoço', 'despesa', TODAY)
    assert (entry.category, entry.date, entry.amount_cents) == ('alimentacao', TODAY, 3590)


@pytest.mark.parametrize('message,kind', [('/saida 20 salario | Teste', 'despesa'), ('/entrada 20 transporte | Teste', 'receita'), ('/saida 20 desconhecida | Teste', 'despesa'), ('/saida 20 lazer', 'despesa'), ('/saida 20 lazer | ', 'despesa'), ('/saida 20 lazer @2026-02-30 | Teste', 'despesa'), ('/saida 20 lazer @13/10/2026 | Teste', 'despesa'), ('/saida 20 lazer | ' + 'x' * 201, 'despesa'), ('/saida 20 lazer | Abc\x00def', 'despesa')])
def test_invalid_entry_rejected(message, kind):
    with pytest.raises(ValidationError):
        parse_entry(message, kind, TODAY)


@pytest.mark.parametrize('description', ['Texto\nquebrado', 'Texto\tcom tabulação', '\nTexto', 'Texto\n'])
def test_control_characters_in_description_rejected(description):
    with pytest.raises(ValidationError):
        parse_entry('/saida 20 lazer | ' + description, 'despesa', TODAY)


@pytest.mark.parametrize('cents,formatted', [(0, 'R$ 0,00'), (125050, 'R$ 1.250,50'), (-3590, '-R$ 35,90'), (1, 'R$ 0,01')])
def test_brl_formatting(cents, formatted):
    assert format_brl(cents) == formatted


@pytest.fixture
def repository(tmp_path):
    repo = Repository(tmp_path / 'finance.sqlite3', initial_balance_cents=10000)
    repo.initialize()
    return repo


def entry(amount='35,90', kind='despesa', category='alimentacao', when='2026-10-13'):
    command = '/entrada' if kind == 'receita' else '/saida'
    return parse_entry(f'{command} {amount} {category} @{when} | Movimento de teste', kind, TODAY)


def test_balances_summary_filters_and_deletion(repository):
    income, _ = repository.add(entry('2500', 'receita', 'salario'))
    expense, _ = repository.add(entry())
    repository.add(entry('100', when='2026-09-20'))
    assert repository.balance() == 246410
    summary = repository.summary('2026-10')
    assert (summary.income_cents, summary.expense_cents, summary.result_cents) == (250000, 3590, 246410)
    assert [t.id for t in repository.list_transactions(month='2026-10', kind='receita')] == [income.id]
    assert [t.id for t in repository.list_transactions(month='2026-10', category='alimentacao')] == [expense.id]
    assert repository.get(expense.id).amount_cents == 3590
    assert repository.delete(expense.id) is True
    assert repository.delete(expense.id) is False
    assert repository.get(expense.id) is None
    assert repository.balance() == 250000
    assert repository.summary('2026-10').expense_cents == 0


def test_initial_balance_is_persisted_once(repository):
    reopened = Repository(repository_path(repository), initial_balance_cents=99999)
    reopened.initialize()
    assert reopened.initial_balance_cents == 10000
    assert reopened.balance() == 10000
    assert reopened.summary('2026-10').income_cents == 0


def repository_path(repo):
    return repo.path


def test_duplicate_update_stays_processed_after_delete(repository):
    transaction, inserted = repository.add(entry(), telegram_update_id=123)
    assert inserted is True
    repeated, inserted = repository.add(entry('99,00'), telegram_update_id=123)
    assert inserted is False
    assert repeated.id == transaction.id
    assert repeated.amount_cents == 3590
    assert len(repository.list_transactions()) == 1
    repository.delete(transaction.id)
    _, inserted = repository.add(entry(), telegram_update_id=123)
    assert inserted is False
    assert repository.list_transactions() == []


def test_concurrent_connections_preserve_all_records(tmp_path):
    path = tmp_path / 'concurrent.sqlite3'
    Repository(path).initialize()

    def insert(update_id):
        return Repository(path).add(entry('0,01'), telegram_update_id=update_id)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(insert, range(20)))
    assert all(inserted for _, inserted in results)
    reader = Repository(path)
    assert len(reader.list_transactions()) == 20
    assert reader.balance() == -20


def test_duplicate_update_race_is_atomic(tmp_path):
    path = tmp_path / 'race.sqlite3'
    Repository(path).initialize()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: Repository(path).add(entry(), telegram_update_id=42), range(8)))
    assert sum(inserted for _, inserted in results) == 1
    assert Repository(path).balance() == -3590
