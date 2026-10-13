# Registro de implementação

## 13/10/2026 — etapa 0: reinício

Inspeção confirmou apenas `.git`, sem instruções AGENTS.md locais. Registradas
em commit as exclusões do protótipo JavaFX já solicitadas pelo usuário. Histórico
e remoto preservados; nenhum push feito.

## Etapa 1: domínio, configuração e SQLite

Python 3.12.3; Textual 8.2.8, python-telegram-bot 22.8 e pytest 9.1.1 instalados
em ambiente virtual. `pip check`: sem conflitos. Validação monetária estrita,
centavos inteiros, categorias fixas e aliases, datas opcionais, saldo inicial
persistente, migração v1, WAL e transações curtas. Deduplicação permanece em
tabela separada mesmo após exclusão. Backup via API SQLite.

Agente independente escreveu testes: 46 passaram. Cobertura de concorrência,
reprocessamento, saldo e filtros. Falha encontrada pelo agente: strip removia
controles nas extremidades da descrição antes da validação. Corrigido e testado.
Pesquisa de referências e restrições registrada em REFERENCIAS.md.
