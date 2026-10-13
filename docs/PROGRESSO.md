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

## Etapa 2: fluxo completo local

Bot com comandos estruturados e autorização centralizada em todas as mensagens e
callbacks. Registro confirma somente após commit SQLite. Exclusão tem nonce,
vínculo usuário/chat/ID, validade de 5 minutos, cancelamento e proteção contra
botões antigos. Long polling explícito via Bot da biblioteca mantida, offset
persistido após processamento e espera progressiva. Lock de processo evita dois
bots no mesmo banco. Dashboard independente com consultas a cada segundo,
indicadores distintos, filtros e seleção/scroll preservados. CLI com demo
isolada, init e backup.

Validação de agente identificou colisão `_ready` com método interno do Textual:
renomeado para `_dashboard_ready`. Fluxo testado com Telegram simulado e TUI
headless. Dependências transitivas congeladas em requirements.lock.

## Etapa 3: resiliência e validação ampliada

Testes independentes cobrem bootstrap/polling com falhas de rede, espera
progressiva até 60s, RetryAfter em inteiro/timedelta, retomada de offset e falha
na resposta após commit sem duplicar lançamento. Conflict e InvalidToken são
fatais (Conflict não herda NetworkError na versão usada). Lock liberado ao
encerrar, demo isolada/reabertura e backup dos marcadores validados.

Teste usa objetos reais telegram.Update/Message com somente transporte mockado;
confirmado registro após encerrar a TUI. Layout mínimo 80x24 e tamanhos maiores
validados, fluxo comando → SQLite → TUI visível em 1,2s, filtros/foco/ID/scroll
preservados. Painel de categorias ganhou rolagem por teclado após validação em
layout compacto. Demonstração tem identificação permanente no cabeçalho.

Execução real da CLI no PTY: demo abriu e saiu com q, sem token. init/backup
executados com banco de teste em /tmp; bot sem credenciais falha claramente
antes de iniciar. Não foram usados banco pessoal ou conta Telegram reais.

## Etapa 4: documentação e resultado final

README em português e guia INSTALACAO-E-USO entregues: instalação no Ubuntu com
venv, BotFather e ID autorizado, configuração por ambiente, inicialização,
comandos/data/categorias, distinção saldo/resultado mensal, demo, backup seguro,
restauração, limitações e troubleshooting. Serviço systemd de usuário descrito
como opção manual; nenhum serviço, configuração global ou credencial alterados.

Resultado final: `PTB_TIMEDELTA=true .venv/bin/python -m pytest -q` — **97 passed**;
`pip check` sem conflitos; compileall e git diff --check aprovados. PTB_TIMEDELTA
ativa antecipadamente o tipo timedelta recomendado pela biblioteca e evita
avisos de depreciação; também foram testados ambos os tipos (inteiro/timedelta).
Sem essa variável, a suíte passa, mas PTB pode emitir avisos de retry_after.

### Critérios de aceite e evidência

| Critério | Verificação |
| --- | --- |
| Dashboard inicia no Ubuntu | CLI demo em PTY; TUI headless 80x24,100x30,120x40 |
| Receita/despesa via comandos | Controller com updates simulados e objetos reais PTB, transporte mockado |
| Registro aparece automaticamente | Controller → banco → TUI em 1,2s nos testes |
| Saldo/resumo/exclusão consistentes | Testes de valores inteiros, mês e saldo inicial |
| Dados persistem | Reabertura de repository e backup/restauração testados |
| Inválidos/terceiros rejeitados | Testes mensagens, tipos, grupos e callbacks |
| Update não duplica | Reprocessamento, concorrência e replay após exclusão |
| Exclusão exige confirmação | ID/usuário/chat/nonce/prazo e botões antigos testados |
| Bot independe da TUI | Controller salva após encerrar o app headless |
| Demo sem token e isolada | CLI e testes de reabertura/caminho reservado |
| Rede falha sem loop intenso | Transporte mockado; backoff, bootstrap e RetryAfter |

Pendente: comunicação com Telegram real, token/ID do usuário e observação da
interface no terminal pessoal. Nenhuma mensagem enviada a terceiros; nenhum
push ao remoto. A validação local não foi apresentada como teste de bot real.
