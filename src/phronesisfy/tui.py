"""Dashboard consultivo inspirado nos painéis do btop."""
from datetime import datetime
import sqlite3
from zoneinfo import ZoneInfo

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Input, Select, Static

from .domain import CATEGORIES, LABELS, ValidationError, format_brl, validate_month
from .repository import Repository


class CategoryPanel(VerticalScroll):
    """Barras roláveis também pelo teclado em terminais compactos."""

    def compose(self) -> ComposeResult:
        yield Static(id='categories-content')

    def update(self, content):
        self.query_one('#categories-content', Static).update(content)


class FinanceApp(App):
    TITLE = 'PhronesisFy'
    SUB_TITLE = 'Finanças pessoais · SQLite local'
    CSS = """
    Screen { background: #0b1220; color: #dde6f3; }
    Header { background: #142238; }
    Footer { background: #142238; }
    #content { padding: 0 1; }
    #filters { height: 3; }
    #month { width: 18; }
    #kind { width: 24; }
    #category { width: 1fr; }
    #cards { grid-size: 4; grid-gutter: 0 1; height: 4; }
    .card { border: round #3c91b6; padding: 0 1; background: #111e31; }
    #balance { border: round #65c7a0; }
    #categories { border: round #a794ce; height: 8; padding: 0 1; overflow-y: auto; }
    #categories-content { height: auto; }
    #history { border: round #3c91b6; height: 1fr; min-height: 5; }
    #status { height: 2; color: #a8b8cf; }
    #small { display: none; padding: 1; border: round #e0b76c; }
    Screen.compact #cards { grid-size: 2; height: 6; }
    Screen.compact #categories { height: 6; }
    Screen.too-small #content { display: none; }
    Screen.too-small #small { display: block; }
    """
    BINDINGS = [('q', 'quit', 'Sair'), ('r', 'refresh', 'Atualizar'), ('m', 'month', 'Mês'),
                ('h', 'history', 'Histórico'), ('ctrl+left', 'previous_month', 'Mês anterior'),
                ('ctrl+right', 'next_month', 'Próximo mês')]

    def __init__(self, repository: Repository, timezone='America/Recife', demo=False):
        super().__init__()
        self.repository = repository
        self.timezone = timezone
        self.demo = demo
        if demo:
            self.sub_title = 'DEMONSTRAÇÃO · dados fictícios em banco separado'
        self.month = datetime.now(ZoneInfo(timezone)).strftime('%Y-%m')
        self._snapshot = None
        self._dashboard_ready = False
        self._last_update = ''

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static('Terminal pequeno demais. Aumente para pelo menos 80 colunas × 24 linhas. Ctrl+C para sair.', id='small')
        with Vertical(id='content'):
            with Horizontal(id='filters'):
                yield Input(self.month, placeholder='AAAA-MM', id='month')
                yield Select([('Todos os tipos', 'all'), ('Receitas', 'receita'), ('Despesas', 'despesa')], value='all', allow_blank=False, id='kind')
                categories = sorted(set(CATEGORIES['receita'] + CATEGORIES['despesa']))
                yield Select([('Todas as categorias', 'all')] + [(LABELS.get(c, c), c) for c in categories], value='all', allow_blank=False, id='category')
            with Grid(id='cards'):
                yield Static(id='balance', classes='card')
                yield Static(id='income', classes='card')
                yield Static(id='expense', classes='card')
                yield Static(id='result', classes='card')
            yield CategoryPanel(id='categories')
            yield DataTable(id='history', cursor_type='row', zebra_stripes=True)
            yield Static(id='status')
        yield Footer()

    def on_mount(self):
        self.theme = 'textual-dark'
        table = self.query_one('#history', DataTable)
        table.add_columns('ID', 'Data', 'Tipo', 'Categoria', 'Descrição', 'Valor (BRL)')
        table.border_title = 'Histórico · setas / PgUp / PgDn · Tab alterna foco'
        self.query_one('#categories', CategoryPanel).border_title = 'Despesas por categoria · mês selecionado'
        self._dashboard_ready = True
        self._resize_layout(self.size.width, self.size.height)
        self.refresh_dashboard()
        table.focus()
        self.set_interval(1, self.refresh_dashboard)

    def _resize_layout(self, width, height):
        self.screen.set_class(width < 110, 'compact')
        self.screen.set_class(width < 80 or height < 24, 'too-small')

    def on_resize(self, event):
        self._resize_layout(event.size.width, event.size.height)

    def on_input_changed(self, event: Input.Changed):
        if self._dashboard_ready and event.input.id == 'month':
            self.refresh_dashboard()

    def on_select_changed(self, event: Select.Changed):
        if self._dashboard_ready:
            self.refresh_dashboard()

    def refresh_dashboard(self):
        if not self._dashboard_ready:
            return
        month = self.query_one('#month', Input).value
        kind = self.query_one('#kind', Select).value
        category = self.query_one('#category', Select).value
        status = self.query_one('#status', Static)
        try:
            validate_month(month)
            snapshot = self.repository.dashboard(month, None if kind == 'all' else kind, None if category == 'all' else category)
        except ValidationError:
            status.update('Mês inválido. Use AAAA-MM; os painéis mantêm o último mês válido.')
            return
        except sqlite3.Error:
            status.update('Banco temporariamente indisponível. Tentando novamente a cada segundo.')
            return
        self.month = month
        self._last_update = datetime.now(ZoneInfo(self.timezone)).strftime('%H:%M:%S')
        balance, summary, categories, rows = snapshot
        status.update(f"{'DEMONSTRAÇÃO · ' if self.demo else ''}{len(rows)} movimentações no filtro · consulta {self._last_update} · auto 1s\nSaldo: todas as datas. Indicadores e barras: mês. Registro: Telegram.")
        marker = (month, kind, category, snapshot)
        if marker == self._snapshot:
            return
        self._snapshot = marker
        for widget_id, title, value, color in (
            ('balance', 'SALDO ATUAL · TOTAL', balance, '#79d9b4'),
            ('income', 'RECEITAS · MÊS', summary.income_cents, '#79d9b4'),
            ('expense', 'DESPESAS · MÊS', summary.expense_cents, '#f2a78a'),
            ('result', 'RESULTADO · MÊS', summary.result_cents, '#c9b6ef')):
            card = self.query_one('#' + widget_id, Static)
            card.border_title = title
            card.update(Text(format_brl(value), style=color))
        chart = Text()
        maximum = max(categories.values(), default=1)
        for name, amount in sorted(categories.items(), key=lambda item: (-item[1], item[0])):
            # Gráfico visual usa inteiros; nenhum cálculo monetário em float.
            width = max(1, amount * 22 // maximum)
            chart.append(f'{LABELS.get(name, name):<12} ', style='#c9b6ef')
            chart.append('█' * width + ' ' * (22 - width), style='#8cb8ea')
            chart.append(f' {format_brl(amount)}\n')
        if not categories:
            chart.append('Nenhuma despesa neste mês. Registre pelo Telegram: /saida 35,90 alimentacao | Almoço')
        self.query_one('#categories', CategoryPanel).update(chart)
        table = self.query_one('#history', DataTable)
        selected = None
        old_row = table.cursor_row
        if table.row_count:
            selected = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
        scroll_x, scroll_y = table.scroll_x, table.scroll_y
        table.clear()
        for transaction in rows:
            # Text evita interpretar descrições do usuário como markup Rich.
            table.add_row(str(transaction.id), transaction.date.strftime('%d/%m/%Y'),
                          transaction.kind, LABELS.get(transaction.category, transaction.category),
                          Text(transaction.description), format_brl(transaction.amount_cents), key=str(transaction.id))
        if rows:
            new_row = next((i for i, t in enumerate(rows) if str(t.id) == selected), min(old_row, len(rows) - 1))
            table.move_cursor(row=new_row, column=0, animate=False, scroll=False)
        else:
            status.update(f'Sem movimentações para {month} e estes filtros. Use Tab para ajustar filtros ou registre pelo Telegram.\nSaldo atual inclui todas as datas; resumo e gráfico consideram o mês selecionado.')
        self.call_after_refresh(table.scroll_to, x=scroll_x, y=scroll_y, animate=False, force=True)

    def action_refresh(self):
        self._snapshot = None
        self.refresh_dashboard()

    def action_month(self):
        self.query_one('#month', Input).focus()

    def action_history(self):
        self.query_one('#history', DataTable).focus()

    def _shift_month(self, delta):
        try:
            year, month = map(int, validate_month(self.query_one('#month', Input).value).split('-'))
            total = year * 12 + month - 1 + delta
            new_year, new_month = divmod(total, 12)
            if 1 <= new_year <= 9999:
                self.query_one('#month', Input).value = f'{new_year:04d}-{new_month + 1:02d}'
        except ValidationError:
            self.notify('Use um mês válido: AAAA-MM.')

    def action_previous_month(self):
        self._shift_month(-1)

    def action_next_month(self):
        self._shift_month(1)
