"""Barras acessíveis por teclado mesmo no menor layout suportado."""
import asyncio
from datetime import date
from textual.widgets import Static
from phronesisfy.domain import CATEGORIES, Entry
from phronesisfy.repository import Repository
from phronesisfy.tui import FinanceApp, CategoryPanel


def test_category_chart_scrolls_with_keyboard(tmp_path):
    repository = Repository(tmp_path / 'finance.db')
    repository.initialize()
    for category in CATEGORIES['despesa']:
        repository.add(Entry('despesa', 100, category, 'Demonstração', date(2026, 10, 1)))

    async def scenario():
        app = FinanceApp(repository)
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one('#month').value = '2026-10'
            await pilot.pause()
            chart = app.query_one('#categories', CategoryPanel)
            chart.focus()
            await pilot.press('pagedown')
            await pilot.pause()
            assert app.focused is chart
            assert chart.scroll_y > 0
    asyncio.run(scenario())
