"""Entradas separadas para bot e dashboard, demonstração e backup."""
import argparse
import asyncio
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import fcntl
import logging
import os
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from .config import Settings
from .domain import Entry, ValidationError
from .repository import Repository


@contextmanager
def bot_lock(repository: Repository):
    """Uma instância do bot por banco; TUI não utiliza esse lock."""
    descriptor = os.open(str(repository.path) + '.bot.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValidationError('Já existe um bot ativo usando este banco. Fechar o dashboard não o encerra.') from exc
        yield
    finally:
        os.close(descriptor)


def demo_repository(settings: Settings) -> Repository:
    # Caminho fixo separado: não respeita PHRONESISFY_DB pessoal.
    data_home = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))).expanduser().absolute()
    path = data_home / 'phronesisfy/demo.db'
    if path == settings.db_path:
        raise ValidationError('O banco pessoal não pode usar o caminho reservado demo.db.')
    repository = Repository(path, initial_balance_cents=125000)
    repository.initialize()
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    samples = [
        ('receita', 350000, 'salario', 'Salário fictício', 1),
        ('receita', 85000, 'freelance', 'Projeto fictício', 7),
        ('despesa', 110000, 'moradia', 'Aluguel fictício', 2),
        ('despesa', 24890, 'alimentacao', 'Mercado fictício', 3),
        ('despesa', 3590, 'alimentacao', 'Almoço fictício', 9),
        ('despesa', 12000, 'transporte', 'Transporte fictício', 4),
        ('despesa', 18000, 'saude', 'Consulta fictícia', 5),
        ('despesa', 9900, 'educacao', 'Curso fictício', 6),
        ('despesa', 6500, 'lazer', 'Cinema fictício', 8),
        ('despesa', 2500, 'outros', 'Outro gasto fictício', 10),
    ]
    # Todas as amostras e marcador são gravados na mesma transação, mesmo em duas TUIs.
    with repository.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute("SELECT 1 FROM settings WHERE key='demo_seeded'").fetchone():
            created = datetime.now(ZoneInfo(settings.timezone)).isoformat()
            for kind, cents, category, description, day in samples:
                db.execute('INSERT INTO transactions(kind,amount_cents,category,description,date,created_at) VALUES (?,?,?,?,?,?)',
                           (kind, cents, category, description, date(today.year, today.month, min(day, today.day)).isoformat(), created))
            previous = today.replace(day=1) - timedelta(days=1)
            db.execute('INSERT INTO transactions(kind,amount_cents,category,description,date,created_at) VALUES (?,?,?,?,?,?)',
                       ('despesa', 10000, 'lazer', 'Passeio fictício no mês anterior', previous.isoformat(), created))
            db.execute("INSERT INTO settings VALUES ('demo_seeded','1')")
    return repository


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='PhronesisFy — finanças locais no terminal e Telegram')
    sub = parser.add_subparsers(dest='command', required=True)
    dashboard = sub.add_parser('dashboard', help='Consultar finanças no terminal')
    dashboard.add_argument('--demo', action='store_true', help='Dados fictícios em banco separado; não exige Telegram')
    sub.add_parser('bot', help='Executar bot Telegram em long polling')
    sub.add_parser('init', help='Inicializar banco pessoal e saldo inicial')
    backup = sub.add_parser('backup', help='Backup consistente do banco pessoal, mesmo em uso')
    backup.add_argument('destination', type=Path, help='Novo arquivo para backup')
    args = parser.parse_args(argv)
    # Novos arquivos de dados, WAL e lock não são legíveis por outros usuários.
    os.umask(0o077)
    try:
        settings = Settings.from_env(require_telegram=args.command == 'bot')
        if args.command == 'dashboard' and args.demo:
            repository = demo_repository(settings)
        else:
            repository = Repository(settings.db_path, settings.initial_balance_cents)
            repository.initialize()
        if args.command == 'dashboard':
            from .tui import FinanceApp
            FinanceApp(repository, settings.timezone, demo=args.demo).run()
        elif args.command == 'bot':
            from .bot import LOGGER, poll
            # Bibliotecas HTTP podem incluir o token na URL: apenas nosso logger imprime.
            logging.basicConfig(level=logging.CRITICAL)
            LOGGER.setLevel(logging.INFO)
            LOGGER.propagate = False
            if not LOGGER.handlers:
                LOGGER.addHandler(logging.StreamHandler())
            with bot_lock(repository):
                print('Bot iniciado. Ctrl+C encerra; o dashboard é outro processo.')
                asyncio.run(poll(settings, repository))
        elif args.command == 'init':
            print(f'Banco inicializado: {repository.path}')
            print('Saldo inicial persistido; mudanças posteriores na variável não alteram o banco.')
        elif args.command == 'backup':
            repository.backup(args.destination)
            print(f'Backup concluído: {args.destination.expanduser().absolute()}')
    except ValidationError as exc:
        parser.exit(2, f'Configuração ou entrada inválida: {exc}\n')
    except (OSError, sqlite3.Error):
        parser.exit(2, 'Não foi possível acessar os arquivos ou banco. Confira caminho, permissões e espaço livre.\n')
    except KeyboardInterrupt:
        print('\nEncerrado.')
    return 0
