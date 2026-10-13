"""Configuração por ambiente. Nunca imprime token ou mensagens financeiras."""
from dataclasses import dataclass, field
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .domain import ValidationError, parse_initial_balance


@dataclass(frozen=True)
class Settings:
    db_path: Path
    timezone: str = "America/Recife"
    initial_balance_cents: int = 0
    telegram_user_id: int | None = None
    telegram_bot_token: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls, require_telegram: bool = False) -> "Settings":
        timezone = os.environ.get("PHRONESISFY_TIMEZONE", "America/Recife")
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError("PHRONESISFY_TIMEZONE deve ser um fuso IANA válido.") from exc
        data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        db_path = Path(os.environ.get("PHRONESISFY_DB", str(data_home / "phronesisfy/finance.db"))).expanduser().absolute()
        token = os.environ.get("TELEGRAM_BOT_TOKEN") or None
        user = os.environ.get("TELEGRAM_USER_ID", "")
        if user and (not user.isascii() or not user.isdigit() or int(user) <= 0):
            raise ValidationError("TELEGRAM_USER_ID deve ser um número inteiro positivo.")
        if require_telegram and (not token or not user):
            raise ValidationError("Configure TELEGRAM_BOT_TOKEN e TELEGRAM_USER_ID antes de iniciar o bot.")
        return cls(db_path, timezone, parse_initial_balance(os.environ.get("PHRONESISFY_INITIAL_BALANCE", "0")), int(user) if user else None, token)
