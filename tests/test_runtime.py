import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from telegram.error import Conflict, InvalidToken, NetworkError, RetryAfter

import phronesisfy.bot as bot_module
from phronesisfy.cli import bot_lock, demo_repository
from phronesisfy.config import Settings
from phronesisfy.domain import ValidationError, parse_entry
from phronesisfy.repository import Repository


class StopPolling(BaseException):
    pass


@pytest.fixture
def repo(tmp_path):
    repository = Repository(tmp_path / 'finance.db')
    repository.initialize()
    return repository


def settings(repo):
    return Settings(repo.path, telegram_user_id=42, telegram_bot_token='test-token')


class FakeBot:
    def __init__(self, events=(), bootstrap=None):
        self.events = iter(events)
        self.bootstrap = bootstrap
        self.offsets = []
        self.webhook_options = []

    async def __aenter__(self):
        if self.bootstrap:
            raise self.bootstrap
        return self

    async def __aexit__(self, *_):
        return False

    async def delete_webhook(self, **kwargs):
        self.webhook_options.append(kwargs)

    async def get_updates(self, **kwargs):
        self.offsets.append(kwargs['offset'])
        event = next(self.events, StopPolling())
        if isinstance(event, BaseException):
            raise event
        return event


def test_polling_network_backoff_is_progressive_and_capped(monkeypatch, repo):
    fake = FakeBot([NetworkError('offline')] * 9)
    monkeypatch.setattr(bot_module, 'Bot', lambda *_: fake)
    delays = []

    async def sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(bot_module.asyncio, 'sleep', sleep)
    with pytest.raises(StopPolling):
        asyncio.run(bot_module.poll(settings(repo), repo))
    assert delays == [1, 2, 4, 8, 16, 32, 60, 60, 60]
    assert fake.webhook_options == [{'drop_pending_updates': False}]
    assert repo.get_offset() == 0


def test_bootstrap_retries_reconnect_and_reset_delay_after_success(monkeypatch, repo):
    bots = iter([FakeBot(bootstrap=NetworkError('offline')), FakeBot(bootstrap=NetworkError('offline')), FakeBot([[], NetworkError('offline')])])
    monkeypatch.setattr(bot_module, 'Bot', lambda *_: next(bots))
    delays = []

    async def sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(bot_module.asyncio, 'sleep', sleep)
    with pytest.raises(StopPolling):
        asyncio.run(bot_module.poll(settings(repo), repo))
    assert delays == [1, 2, 1]


@pytest.mark.parametrize('retry,expected', [(RetryAfter(7), 7), (RetryAfter(timedelta(seconds=9)), 9)])
def test_retry_after_respects_telegram_delay(monkeypatch, repo, retry, expected):
    monkeypatch.setattr(bot_module, 'Bot', lambda *_: FakeBot([retry]))
    delays = []

    async def sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(bot_module.asyncio, 'sleep', sleep)
    with pytest.raises(StopPolling):
        asyncio.run(bot_module.poll(settings(repo), repo))
    assert delays == [expected]


@pytest.mark.parametrize('error', [Conflict('other bot'), InvalidToken('invalid')])
@pytest.mark.parametrize('bootstrap', [False, True])
def test_conflict_and_invalid_token_are_fatal(monkeypatch, repo, error, bootstrap):
    fake = FakeBot(bootstrap=error) if bootstrap else FakeBot([error])
    monkeypatch.setattr(bot_module, 'Bot', lambda *_: fake)

    async def no_retry(_):
        raise AssertionError('Fatal configuration errors must not retry')

    monkeypatch.setattr(bot_module.asyncio, 'sleep', no_retry)
    with pytest.raises(ValidationError, match='Token inválido ou outro processo'):
        asyncio.run(bot_module.poll(settings(repo), repo))


def test_network_failure_after_save_replays_without_duplicate(monkeypatch, repo):
    replies = []

    async def reply(text, **_):
        replies.append(text)
        if len(replies) == 1:
            assert repo.get_offset() == 0
            assert len(repo.list_transactions()) == 1
            raise NetworkError('connection lost while replying')

    update = SimpleNamespace(update_id=12, effective_user=SimpleNamespace(id=42),
                             effective_chat=SimpleNamespace(id=42, type='private'), callback_query=None,
                             message=SimpleNamespace(text='/saida 35,90 alimentacao | Almoço', reply_text=reply))
    fake = FakeBot([[update], [update]])
    monkeypatch.setattr(bot_module, 'Bot', lambda *_: fake)

    async def sleep(_):
        pass

    monkeypatch.setattr(bot_module.asyncio, 'sleep', sleep)
    with pytest.raises(StopPolling):
        asyncio.run(bot_module.poll(settings(repo), repo))
    assert fake.offsets == [0, 0, 13]
    assert repo.get_offset() == 13
    assert len(repo.list_transactions()) == 1
    assert repo.balance() == -3590
    assert 'já foi processada' in replies[1]


def test_polling_resumes_from_persisted_offset_after_restart(monkeypatch, repo):
    repo.set_offset(800)
    reopened = Repository(repo.path)
    reopened.initialize()
    fake = FakeBot()
    monkeypatch.setattr(bot_module, 'Bot', lambda *_: fake)
    with pytest.raises(StopPolling):
        asyncio.run(bot_module.poll(settings(reopened), reopened))
    assert fake.offsets == [800]


def test_bootstrap_retry_after_then_recovers(monkeypatch, repo):
    bots = iter([FakeBot(bootstrap=RetryAfter(4)), FakeBot()])
    monkeypatch.setattr(bot_module, 'Bot', lambda *_: next(bots))
    delays = []

    async def sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(bot_module.asyncio, 'sleep', sleep)
    with pytest.raises(StopPolling):
        asyncio.run(bot_module.poll(settings(repo), repo))
    assert delays == [4]


def test_lock_prevents_second_bot_and_releases_after_exit(repo):
    with bot_lock(repo):
        with pytest.raises(ValidationError, match='Já existe um bot ativo'):
            with bot_lock(repo):
                pytest.fail('Second bot acquired the same lock')
        assert repo.balance() == 0  # Consultas não precisam do lock do bot.
    with bot_lock(repo):
        assert repo.balance() == 0


def test_demo_separate_from_personal_database_and_seed_once(monkeypatch, repo, tmp_path):
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'data'))
    demo = demo_repository(settings(repo))
    assert demo.path != repo.path
    assert repo.list_transactions() == []
    assert len(demo.list_transactions()) == 11
    balance = demo.balance()
    reopened = demo_repository(settings(repo))
    assert reopened.balance() == balance
    assert len(reopened.list_transactions()) == 11


def test_demo_refuses_personal_database_reserved_path(monkeypatch, tmp_path):
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
    with pytest.raises(ValidationError, match='reservado'):
        demo_repository(Settings(tmp_path / 'phronesisfy/demo.db'))


def test_backup_preserves_balance_offset_and_deleted_update_deduplication(repo, tmp_path):
    entry = parse_entry('/entrada 2500 salario | Salário', 'receita', date(2026, 10, 13))
    transaction, _ = repo.add(entry, telegram_update_id=22)
    repo.delete(transaction.id)
    repo.set_offset(23)
    path = tmp_path / 'backup.db'
    repo.backup(path)
    restored = Repository(path, initial_balance_cents=9000)
    restored.initialize()
    assert restored.balance() == 0
    assert restored.get_offset() == 23
    assert restored.add(entry, telegram_update_id=22) == (None, False)
    assert restored.list_transactions() == []
    assert path.stat().st_mode & 0o777 == 0o600


def test_backup_refuses_overwriting_existing_file_or_active_database(repo, tmp_path):
    existing = tmp_path / 'existing.txt'
    existing.write_text('preserve')
    for path in [existing, repo.path]:
        with pytest.raises(ValidationError):
            repo.backup(path)
    assert existing.read_text() == 'preserve'
