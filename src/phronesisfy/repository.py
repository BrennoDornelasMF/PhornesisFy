"""SQLite: transações curtas, migrações e deduplicação durável."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
import sqlite3

from .domain import Entry, Summary, Transaction, ValidationError, MAX_AMOUNT_CENTS, validate_entry, validate_month

SCHEMA_VERSION = 1
MIGRATIONS = {1: (
    "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL CHECK(kind IN ('receita','despesa')),
        amount_cents INTEGER NOT NULL CHECK(amount_cents > 0 AND amount_cents <= 99999999999),
        category TEXT NOT NULL, description TEXT NOT NULL,
        date TEXT NOT NULL, created_at TEXT NOT NULL,
        telegram_update_id INTEGER UNIQUE)""",
    "CREATE INDEX transactions_date ON transactions(date DESC, id DESC)",
    "CREATE TABLE processed_updates (update_id INTEGER PRIMARY KEY, transaction_id INTEGER NOT NULL)",
    """CREATE TABLE pending_deletions (
        user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, transaction_id INTEGER NOT NULL,
        nonce TEXT NOT NULL, expires_at INTEGER NOT NULL, PRIMARY KEY(user_id, chat_id))""",
)}


class Repository:
    def __init__(self, path: Path | str, initial_balance_cents: int = 0):
        self.path = Path(path).expanduser().absolute()
        if type(initial_balance_cents) is not int or abs(initial_balance_cents) > MAX_AMOUNT_CENTS:
            raise ValidationError("Saldo inicial inválido em centavos.")
        self._initial = initial_balance_cents

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise ValidationError("Banco de versão mais nova que o aplicativo. Atualize o programa.")
            for next_version in range(version + 1, SCHEMA_VERSION + 1):
                for sql in MIGRATIONS[next_version]:
                    db.execute(sql)
                db.execute(f"PRAGMA user_version={next_version}")
            db.execute("INSERT OR IGNORE INTO settings VALUES ('initial_balance', ?)", (str(self._initial),))
        self.path.chmod(0o600)

    @staticmethod
    def _transaction(row: sqlite3.Row | None) -> Transaction | None:
        if row is None:
            return None
        return Transaction(row['kind'], row['amount_cents'], row['category'], row['description'],
                           date.fromisoformat(row['date']), row['id'], datetime.fromisoformat(row['created_at']), row['telegram_update_id'])

    @property
    def initial_balance_cents(self) -> int:
        with self.connection() as db:
            return int(db.execute("SELECT value FROM settings WHERE key='initial_balance'").fetchone()[0])

    def add(self, entry: Entry, telegram_update_id: int | None = None) -> tuple[Transaction | None, bool]:
        entry = validate_entry(entry)
        if telegram_update_id is not None and (type(telegram_update_id) is not int or telegram_update_id < 0):
            raise ValidationError("Identificador de atualização inválido.")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if telegram_update_id is not None:
                old = db.execute("SELECT transaction_id FROM processed_updates WHERE update_id=?", (telegram_update_id,)).fetchone()
                if old:
                    return self._transaction(db.execute("SELECT * FROM transactions WHERE id=?", (old[0],)).fetchone()), False
            cursor = db.execute("""INSERT INTO transactions(kind,amount_cents,category,description,date,created_at,telegram_update_id)
                VALUES (?,?,?,?,?,?,?)""", (entry.kind, entry.amount_cents, entry.category, entry.description,
                entry.date.isoformat(), datetime.now(timezone.utc).isoformat(), telegram_update_id))
            if telegram_update_id is not None:
                db.execute("INSERT INTO processed_updates VALUES (?,?)", (telegram_update_id, cursor.lastrowid))
            result = self._transaction(db.execute("SELECT * FROM transactions WHERE id=?", (cursor.lastrowid,)).fetchone())
        return result, True

    def get(self, transaction_id: int) -> Transaction | None:
        with self.connection() as db:
            return self._transaction(db.execute("SELECT * FROM transactions WHERE id=?", (transaction_id,)).fetchone())

    @staticmethod
    def _balance(db: sqlite3.Connection) -> int:
        initial = int(db.execute("SELECT value FROM settings WHERE key='initial_balance'").fetchone()[0])
        # Soma em Python usa inteiros arbitrários e evita overflow do SUM SQLite.
        return initial + sum(row[0] if row[1] == 'receita' else -row[0]
                             for row in db.execute("SELECT amount_cents,kind FROM transactions"))

    def balance(self) -> int:
        with self.connection() as db:
            db.execute("BEGIN")
            return self._balance(db)

    @staticmethod
    def _where(month=None, kind=None, category=None):
        clauses, params = [], []
        if month is not None:
            validate_month(month)
            clauses.append("substr(date,1,7)=?")
            params.append(month)
        if kind is not None:
            if kind not in ('receita', 'despesa'):
                raise ValidationError("Tipo de filtro inválido.")
            clauses.append("kind=?")
            params.append(kind)
        if category is not None:
            clauses.append("category=?")
            params.append(category)
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), params

    def list_transactions(self, month=None, kind=None, category=None, limit=100) -> list[Transaction]:
        where, params = self._where(month, kind, category)
        with self.connection() as db:
            rows = db.execute("SELECT * FROM transactions" + where + " ORDER BY date DESC,id DESC LIMIT ?", (*params, limit))
            return [self._transaction(row) for row in rows]

    def summary(self, month: str) -> Summary:
        rows = self.list_transactions(month=month, limit=-1)
        return Summary(sum(t.amount_cents for t in rows if t.kind == 'receita'),
                       sum(t.amount_cents for t in rows if t.kind == 'despesa'))

    def dashboard(self, month: str, kind=None, category=None):
        # Todas as consultas usam o mesmo snapshot, mesmo com escrita concorrente.
        validate_month(month)
        with self.connection() as db:
            db.execute("BEGIN")
            balance = self._balance(db)
            month_rows = list(db.execute("SELECT * FROM transactions WHERE substr(date,1,7)=?", (month,)))
            summary = Summary(sum(r['amount_cents'] for r in month_rows if r['kind'] == 'receita'),
                              sum(r['amount_cents'] for r in month_rows if r['kind'] == 'despesa'))
            categories = {}
            for row in month_rows:
                if row['kind'] == 'despesa':
                    categories[row['category']] = categories.get(row['category'], 0) + row['amount_cents']
            where, params = self._where(month, kind, category)
            rows = [self._transaction(r) for r in db.execute("SELECT * FROM transactions" + where + " ORDER BY date DESC,id DESC", params)]
            return balance, summary, categories, rows

    def delete(self, transaction_id: int) -> bool:
        with self.connection() as db:
            return db.execute("DELETE FROM transactions WHERE id=?", (transaction_id,)).rowcount > 0

    def set_pending(self, user_id: int, chat_id: int, transaction_id: int, nonce: str, expires_at: int):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO pending_deletions VALUES (?,?,?,?,?)", (user_id, chat_id, transaction_id, nonce, expires_at))

    def cancel_pending(self, user_id: int, chat_id: int):
        with self.connection() as db:
            db.execute("DELETE FROM pending_deletions WHERE user_id=? AND chat_id=?", (user_id, chat_id))

    def cancel_matching_pending(self, user_id: int, chat_id: int, transaction_id: int, nonce: str) -> bool:
        with self.connection() as db:
            return db.execute("DELETE FROM pending_deletions WHERE user_id=? AND chat_id=? AND transaction_id=? AND nonce=?",
                              (user_id, chat_id, transaction_id, nonce)).rowcount > 0

    def confirm_delete(self, user_id: int, chat_id: int, transaction_id: int, nonce: str, now: int) -> bool:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            pending = db.execute("SELECT * FROM pending_deletions WHERE user_id=? AND chat_id=?", (user_id, chat_id)).fetchone()
            if not pending or pending['nonce'] != nonce or pending['transaction_id'] != transaction_id or pending['expires_at'] <= now:
                return False
            db.execute("DELETE FROM pending_deletions WHERE user_id=? AND chat_id=?", (user_id, chat_id))
            return db.execute("DELETE FROM transactions WHERE id=?", (transaction_id,)).rowcount > 0

    def get_offset(self) -> int:
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key='telegram_offset'").fetchone()
            return int(row[0]) if row else 0

    def set_offset(self, value: int):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES ('telegram_offset',?)", (str(value),))

    def backup(self, destination: Path | str):
        destination = Path(destination).expanduser().absolute()
        if destination == self.path or destination.exists():
            raise ValidationError("Backup deve usar um caminho novo, diferente do banco ativo.")
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connection() as db:
            target = sqlite3.connect(destination)
            try:
                db.backup(target)
            finally:
                target.close()
        destination.chmod(0o600)
