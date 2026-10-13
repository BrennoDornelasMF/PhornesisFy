"""Integração local: processos independentes, bot simulado e TUI headless."""
import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from phronesisfy.config import Settings
from phronesisfy.domain import Entry
from phronesisfy.repository import Repository


@pytest.fixture
def repository(tmp_path):
    repo = Repository(tmp_path / "finance.db", initial_balance_cents=10000)
    repo.initialize()
    return repo


def test_independent_connections_persistence_and_backup(repository, tmp_path):
    second = Repository(repository.path, initial_balance_cents=999)
    second.initialize()
    saved, created = repository.add(Entry("receita", 250000, "salario", "Salário", date(2026, 10, 1)), 71)
    assert created
    assert second.balance() == 260000
    assert second.initial_balance_cents == 10000
    expense, _ = second.add(Entry("despesa", 3590, "alimentacao", "Almoço", date(2026, 10, 2)), 72)
    assert repository.summary("2026-10").result_cents == 246410
    assert repository.balance() == 256410
    repository.backup(tmp_path / "backup.db")
    assert Repository(tmp_path / "backup.db").balance() == 256410
    assert second.delete(expense.id)
    assert repository.balance() == 260000
    assert repository.get(saved.id).description == "Salário"


@pytest.mark.parametrize("change", ["user", "chat", "id", "nonce", "expired"])
def test_confirmation_bound_to_operation(repository, change):
    tx, _ = repository.add(Entry("despesa", 1000, "outros", "Teste", date(2026, 10, 1)))
    repository.set_pending(10, 20, tx.id, "nonce", 100)
    args = [10, 20, tx.id, "nonce", 99]
    args[{"user": 0, "chat": 1, "id": 2, "nonce": 3, "expired": 4}[change]] = {
        "user": 11, "chat": 21, "id": tx.id + 1, "nonce": "old", "expired": 100,
    }[change]
    assert not repository.confirm_delete(*args)
    assert repository.get(tx.id) is not None
    assert repository.confirm_delete(10, 20, tx.id, "nonce", 99)
    assert not repository.confirm_delete(10, 20, tx.id, "nonce", 99)


def test_deleted_update_never_recreates_transaction(repository):
    entry = Entry("receita", 100, "outros", "Teste", date(2026, 10, 1))
    tx, _ = repository.add(entry, 9)
    repository.delete(tx.id)
    duplicate, created = repository.add(entry, 9)
    assert duplicate is None and not created
    assert repository.list_transactions() == []


def fake_update(text=None, *, user=10, chat=10, chat_type="private", update_id=1, callback=None):
    message = SimpleNamespace(text=text, reply_text=AsyncMock()) if text is not None else None
    query = SimpleNamespace(data=callback, answer=AsyncMock(), edit_message_text=AsyncMock()) if callback else None
    return SimpleNamespace(effective_user=SimpleNamespace(id=user),
                           effective_chat=SimpleNamespace(id=chat, type=chat_type),
                           message=message, callback_query=query, update_id=update_id)


@pytest.mark.parametrize("text", ["/saldo", "/resumo", "/ultimas", "/excluir 1", "/cancelar", "/saida 10 lazer | Cinema"])
@pytest.mark.parametrize("identity", [{"user": 99}, {"chat_type": "group"}])
def test_all_commands_reject_unauthorized(repository, text, identity):
    from phronesisfy.bot import TelegramController, is_authorized
    settings = Settings(repository.path, telegram_user_id=10)
    update = fake_update(text, **identity)
    assert not is_authorized(update, settings)
    asyncio.run(TelegramController(repository, settings).handle(update))
    update.message.reply_text.assert_not_awaited()
    assert repository.list_transactions() == []


def test_bot_full_flow_validation_deduplication_and_confirmation(repository):
    from phronesisfy.bot import TelegramController
    controller = TelegramController(repository, Settings(repository.path, telegram_user_id=10))

    async def scenario():
        invalid = fake_update("/saida -10 lazer | Cinema")
        await controller.handle(invalid)
        assert repository.list_transactions() == []
        assert "Não registrado" in invalid.message.reply_text.call_args.args[0]
        update = fake_update("/entrada 2500,00 salario @2026-10-01 | Salário mensal", update_id=20)
        await controller.handle(update)
        await controller.handle(update)
        assert len(repository.list_transactions()) == 1
        tx = repository.list_transactions()[0]
        request = fake_update(f"/excluir {tx.id}", update_id=21)
        await controller.handle(request)
        assert repository.get(tx.id)
        keyboard = request.message.reply_text.call_args.kwargs["reply_markup"]
        callback = keyboard.inline_keyboard[0][0].callback_data
        for identity in [{"user": 99}, {"chat_type": "group"}]:
            unauthorized = fake_update(callback=callback, **identity)
            await controller.handle(unauthorized)
            unauthorized.callback_query.answer.assert_awaited_once()
            unauthorized.callback_query.edit_message_text.assert_not_awaited()
            assert repository.get(tx.id)
        confirmation = fake_update(callback=callback)
        await controller.handle(confirmation)
        assert repository.get(tx.id) is None
        assert repository.balance() == 10000
        await controller.handle(update)
        assert repository.list_transactions() == []

    asyncio.run(scenario())


def test_tui_refresh_filters_focus_navigation_and_resize(repository):
    from phronesisfy.tui import FinanceApp
    from textual.widgets import DataTable, Input, Select, Static

    for index in range(40):
        repository.add(Entry("despesa", 100 + index, "lazer", f"Cinema {index}", date(2026, 10, 1)))

    async def scenario():
        app = FinanceApp(repository)
        async with app.run_test(size=(120, 40)) as pilot:
            month = app.query_one("#month", Input)
            kind = app.query_one("#kind", Select)
            category = app.query_one("#category", Select)
            table = app.query_one("#history", DataTable)
            month.value = "2026-10"
            kind.value = "despesa"
            category.value = "lazer"
            await pilot.pause()
            table.focus()
            table.move_cursor(row=20, scroll=True, animate=False)
            await pilot.pause()
            selected = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            scroll_y = table.scroll_y
            writer = Repository(repository.path)
            writer.add(Entry("despesa", 3590, "lazer", "Novo cinema", date(2026, 10, 2)), 1000)
            await pilot.pause(1.2)
            assert table.row_count == 41
            assert month.value == "2026-10"
            assert kind.value == "despesa" and category.value == "lazer"
            assert app.focused is table
            assert table.coordinate_to_cell_key(table.cursor_coordinate).row_key == selected
            assert table.scroll_y == scroll_y
            month.focus()
            writer.add(Entry("receita", 5000, "outros", "Extra", date(2026, 10, 2)))
            await pilot.pause(1.2)
            assert app.focused is month
            assert "R$" in str(app.query_one("#balance", Static).render())
            month.value = "2026-13"
            await pilot.pause()
            assert table.row_count == 41
            assert "Mês inválido" in str(app.query_one("#status", Static).render())
            await pilot.resize_terminal(60, 20)
            assert app.screen.has_class("too-small")
            assert app.query_one("#small", Static).display
            await pilot.resize_terminal(120, 40)
            assert not app.screen.has_class("too-small")
            for size in [(80, 24), (100, 30), (120, 40)]:
                await pilot.resize_terminal(*size)
                await pilot.pause()
                assert not app.screen.has_class("too-small")
                assert app.query_one("#content").display
                assert table.region.height >= 5

            from phronesisfy.bot import TelegramController
            controller = TelegramController(writer, Settings(writer.path, telegram_user_id=10))
            month.value = "2026-10"
            await controller.handle(fake_update("/saida 42,90 lazer @2026-10-03 | Via Telegram", update_id=2000))
            await pilot.pause(1.2)
            assert table.row_count == 42
            assert any(t.description == "Via Telegram" for t in repository.list_transactions())

    asyncio.run(scenario())


@pytest.mark.parametrize("text", ["/entrada", "/saida", "/excluir", "/entrada 10 salario", "/saida 1.250 lazer | Cinema"])
def test_invalid_command_does_not_write(repository, text):
    from phronesisfy.bot import TelegramController
    update = fake_update(text)
    asyncio.run(TelegramController(repository, Settings(repository.path, telegram_user_id=10)).handle(update))
    assert repository.list_transactions() == []
    assert "Não registrado" in update.message.reply_text.call_args.args[0]


def test_stale_callback_does_not_cancel_latest_request(repository):
    from phronesisfy.bot import TelegramController
    controller = TelegramController(repository, Settings(repository.path, telegram_user_id=10))
    first, _ = repository.add(Entry("despesa", 1000, "lazer", "Primeiro", date(2026, 10, 1)))
    second, _ = repository.add(Entry("despesa", 2000, "lazer", "Segundo", date(2026, 10, 1)))

    async def scenario():
        old = fake_update(f"/excluir {first.id}")
        latest = fake_update(f"/excluir {second.id}")
        await controller.handle(old)
        await controller.handle(latest)
        old_buttons = old.message.reply_text.call_args.kwargs["reply_markup"].inline_keyboard
        latest_buttons = latest.message.reply_text.call_args.kwargs["reply_markup"].inline_keyboard
        for row in old_buttons:
            stale = fake_update(callback=row[0].callback_data)
            await controller.handle(stale)
            stale.callback_query.edit_message_text.assert_not_awaited()
        assert repository.get(first.id) and repository.get(second.id)
        await controller.handle(fake_update(callback=latest_buttons[0][0].callback_data))
        assert repository.get(first.id) is not None
        assert repository.get(second.id) is None

    asyncio.run(scenario())


def test_config_demo_without_credentials_and_token_redacted(monkeypatch, tmp_path):
    from phronesisfy.domain import ValidationError
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_USER_ID", raising=False)
    monkeypatch.setenv("PHRONESISFY_DB", str(tmp_path / "personal.db"))
    settings = Settings.from_env()
    assert settings.telegram_user_id is None
    with pytest.raises(ValidationError, match="Configure"):
        Settings.from_env(require_telegram=True)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("TELEGRAM_USER_ID", "10")
    settings = Settings.from_env(require_telegram=True)
    assert "secret-token" not in repr(settings)


@pytest.mark.parametrize("key,value", [("TELEGRAM_USER_ID", "-1"), ("TELEGRAM_USER_ID", "abc"), ("PHRONESISFY_TIMEZONE", "Invalid/Timezone"), ("PHRONESISFY_INITIAL_BALANCE", "1.250")])
def test_invalid_configuration_rejected(monkeypatch, key, value):
    from phronesisfy.domain import ValidationError
    monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError):
        Settings.from_env()


def test_long_polling_reconnects_with_backoff_and_persists_offset(repository):
    from phronesisfy.bot import poll
    from telegram.error import NetworkError

    update = fake_update("/entrada 10 outros | Teste", update_id=41)
    bot = SimpleNamespace(delete_webhook=AsyncMock(), get_updates=AsyncMock(side_effect=[
        NetworkError("offline"), NetworkError("offline"), [update], asyncio.CancelledError(),
    ]))
    context = AsyncMock()
    context.__aenter__.return_value = bot
    with patch("phronesisfy.bot.Bot", return_value=context), patch("phronesisfy.bot.asyncio.sleep", new_callable=AsyncMock) as sleep:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(poll(Settings(repository.path, telegram_user_id=10, telegram_bot_token="fake"), repository))
    assert [call.args[0] for call in sleep.await_args_list] == [1, 2]
    bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=False)
    assert repository.get_offset() == 42
    assert repository.balance() == 11000
    assert bot.get_updates.await_args_list[-1].kwargs["offset"] == 42


def test_real_telegram_update_and_bot_after_dashboard_closes(repository):
    """Objetos oficiais e hooks reply_text reais; somente transporte é simulado."""
    from telegram import Bot, Update
    from phronesisfy.bot import TelegramController
    from phronesisfy.tui import FinanceApp

    bot = Bot("123456:fake-token")
    controller = TelegramController(repository, Settings(repository.path, telegram_user_id=10))
    payload = {"update_id": 501, "message": {
        "message_id": 1, "date": 1791849600,
        "from": {"id": 10, "is_bot": False, "first_name": "Teste"},
        "chat": {"id": 10, "type": "private", "first_name": "Teste"},
        "text": "/entrada 10 outros @2026-10-13 | Transporte simulado",
    }}
    update = Update.de_json(payload, bot)

    async def scenario():
        async with FinanceApp(repository).run_test(size=(100, 30)):
            pass
        with patch("telegram.Bot.send_message", new_callable=AsyncMock) as send:
            await controller.handle(update)
            assert "Registrado no computador" in send.call_args.kwargs["text"]
            assert send.call_args.kwargs["chat_id"] == 10
        assert repository.balance() == 11000

    asyncio.run(scenario())
