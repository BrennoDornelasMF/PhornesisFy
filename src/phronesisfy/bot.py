"""Comandos estruturados e long polling sem servidor ou portas abertas."""
import asyncio
from datetime import datetime
import logging
import re
import secrets
import sqlite3
import time
from zoneinfo import ZoneInfo

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, Conflict, Forbidden, InvalidToken, NetworkError, RetryAfter

from .config import Settings
from .domain import CATEGORIES, LABELS, ValidationError, format_brl, parse_entry
from .repository import Repository

LOGGER = logging.getLogger(__name__)
HELP = """PhronesisFy — finanças locais em BRL
/entrada 2500,00 salario | Salário mensal
/saida 35,90 alimentacao | Almoço
Data opcional: /saida 20 lazer @2026-10-01 | Cinema
/saldo — saldo acumulado, incluindo saldo inicial
/resumo — receitas, despesas e resultado do mês atual
/ultimas — últimas dez movimentações com IDs
/excluir ID — pedir confirmação (válida por 5 minutos)
/cancelar — cancelar exclusão pendente
/ajuda — esta mensagem

Receitas: salario, freelance, outros.
Despesas: alimentacao, transporte, moradia, saude, educacao, lazer, outros.
Acentos também são aceitos. Descrição obrigatória, até 200 caracteres.
Use valores positivos, sem milhar: 1250,50 ou 1250.50.
O computador e o bot precisam estar ligados e conectados."""


def is_authorized(update: Update, settings: Settings) -> bool:
    return bool(settings.telegram_user_id and update.effective_user and update.effective_chat
                and update.effective_user.id == settings.telegram_user_id
                and update.effective_chat.type == 'private')


def transaction_text(transaction) -> str:
    return (f"ID: {transaction.id}\nTipo: {transaction.kind}\nValor: {format_brl(transaction.amount_cents)}\n"
            f"Categoria: {LABELS.get(transaction.category, transaction.category)}\n"
            f"Descrição: {transaction.description}\nData: {transaction.date:%d/%m/%Y}")


class TelegramController:
    def __init__(self, repository: Repository, settings: Settings):
        self.repository = repository
        self.settings = settings

    async def handle(self, update: Update, context=None) -> None:
        if not is_authorized(update, self.settings):
            # Silêncio: nenhum dado financeiro ou instrução para terceiros.
            if update.callback_query:
                await update.callback_query.answer("Operação não autorizada.", show_alert=True)
            return
        if update.callback_query:
            await self._confirm(update)
            return
        # Mensagens editadas não geram novos lançamentos.
        if not update.message or not update.message.text:
            return
        message = update.message
        command = message.text.split(maxsplit=1)[0].split('@', 1)[0].lower() if message.text.strip() else ''
        args = message.text.split(maxsplit=1)[1].strip() if len(message.text.split(maxsplit=1)) == 2 else ''
        today = datetime.now(ZoneInfo(self.settings.timezone)).date()
        try:
            if command in ('/start', '/ajuda'):
                response = HELP
            elif command in ('/entrada', '/saida'):
                entry = parse_entry(message.text, 'receita' if command == '/entrada' else 'despesa', today)
                transaction, inserted = self.repository.add(entry, update.update_id)
                if not inserted:
                    response = "Esta atualização já foi processada. Nenhum novo lançamento foi criado. Consulte /ultimas e /saldo."
                else:
                    response = "Registrado no computador.\n" + transaction_text(transaction) + f"\nSaldo atual: {format_brl(self.repository.balance())}"
            elif command == '/saldo':
                response = f"Saldo atual: {format_brl(self.repository.balance())}\nSaldo inicial + todas as receitas − todas as despesas."
            elif command == '/resumo':
                month = today.strftime('%Y-%m')
                summary = self.repository.summary(month)
                response = (f"Resumo de {today:%m/%Y}\nReceitas: {format_brl(summary.income_cents)}\n"
                            f"Despesas: {format_brl(summary.expense_cents)}\nResultado do mês: {format_brl(summary.result_cents)}\n"
                            f"Saldo atual (todas as datas): {format_brl(self.repository.balance())}")
            elif command == '/ultimas':
                transactions = self.repository.list_transactions(limit=10)
                response = '\n\n'.join(transaction_text(t) for t in transactions) if transactions else "Nenhuma movimentação. Comece com /entrada 2500,00 salario | Salário mensal"
            elif command == '/excluir':
                if not re.fullmatch(r'[0-9]{1,18}', args) or int(args) <= 0:
                    raise ValidationError("Use /excluir ID. Exemplo: /excluir 12. Consulte IDs com /ultimas.")
                transaction = self.repository.get(int(args))
                if transaction is None:
                    raise ValidationError("ID não encontrado. Consulte /ultimas.")
                nonce = secrets.token_hex(12)
                self.repository.set_pending(update.effective_user.id, update.effective_chat.id, transaction.id, nonce, int(time.time()) + 300)
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('Confirmar exclusão', callback_data=f'delete:{transaction.id}:{nonce}')],
                                                 [InlineKeyboardButton('Cancelar', callback_data=f'cancel:{transaction.id}:{nonce}')]])
                await message.reply_text("Confirme a exclusão deste lançamento (5 minutos):\n" + transaction_text(transaction), reply_markup=keyboard)
                return
            elif command == '/cancelar':
                self.repository.cancel_pending(update.effective_user.id, update.effective_chat.id)
                response = 'Operação pendente cancelada.'
            else:
                response = "Comando desconhecido. Use /ajuda. Exemplo: /saida 35,90 alimentacao | Almoço"
            await message.reply_text(response)
        except ValidationError as exc:
            await message.reply_text(f"Não registrado: {exc}\nConsulte /ajuda para exemplos.")

    async def _confirm(self, update: Update) -> None:
        query = update.callback_query
        match = re.fullmatch(r'(delete|cancel):([0-9]{1,18}):([a-f0-9]{24})', query.data or '')
        if not match:
            await query.answer('Confirmação inválida.', show_alert=True)
            return
        action, transaction_id, nonce = match.groups()
        if action == 'cancel':
            # Não deixe um botão antigo cancelar uma solicitação mais recente.
            valid = self.repository.cancel_matching_pending(update.effective_user.id, update.effective_chat.id, int(transaction_id), nonce)
            await query.answer('Cancelado.' if valid else 'Solicitação antiga ou já encerrada.')
            if valid:
                await query.edit_message_text('Exclusão cancelada.')
            return
        deleted = self.repository.confirm_delete(update.effective_user.id, update.effective_chat.id, int(transaction_id), nonce, int(time.time()))
        if deleted:
            await query.answer('Excluído.')
            await query.edit_message_text(f"Lançamento {transaction_id} excluído.\nSaldo atual: {format_brl(self.repository.balance())}")
        else:
            await query.answer('Solicitação expirada, antiga ou já encerrada. Use /excluir ID novamente.', show_alert=True)


async def poll(settings: Settings, repository: Repository) -> None:
    """Offset durável, reconexão no bootstrap e no polling, sem logs sensíveis."""
    controller = TelegramController(repository, settings)
    delay = 1
    while True:
        try:
            async with Bot(settings.telegram_bot_token) as bot:
                # Sem apagar mensagens pendentes; getUpdates exige ausência de webhook.
                await bot.delete_webhook(drop_pending_updates=False)
                offset = repository.get_offset()
                while True:
                    try:
                        updates = await bot.get_updates(offset=offset, timeout=30, read_timeout=40,
                                                        allowed_updates=['message', 'callback_query'])
                        for update in updates:
                            try:
                                await controller.handle(update)
                            except (BadRequest, Forbidden):
                                # A escrita pode ter ocorrido. Não exponha o erro HTTP (URL pode conter token).
                                LOGGER.warning('Resposta não entregue pelo Telegram; consulte /ultimas ao reconectar.')
                            repository.set_offset(update.update_id + 1)
                            offset = update.update_id + 1
                        delay = 1
                    except RetryAfter as exc:
                        seconds = exc.retry_after.total_seconds() if hasattr(exc.retry_after, 'total_seconds') else exc.retry_after
                        await asyncio.sleep(max(1, seconds))
                    except (NetworkError, sqlite3.OperationalError):
                        LOGGER.warning('Conexão ou banco indisponível; nova tentativa em %s segundos.', delay)
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, 60)
        except (InvalidToken, Conflict):
            raise ValidationError('Token inválido ou outro processo usa este bot. Confira a configuração e execute apenas uma instância.') from None
        except RetryAfter as exc:
            seconds = exc.retry_after.total_seconds() if hasattr(exc.retry_after, 'total_seconds') else exc.retry_after
            await asyncio.sleep(max(1, seconds))
        except NetworkError:
            LOGGER.warning('Telegram indisponível na inicialização; nova tentativa em %s segundos.', delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
