# Arquitetura e decisões

Dois processos independentes: bot Telegram → validação → SQLite ← dashboard
Textual. Sem servidor HTTP. Python 3.12+, dinheiro em centavos inteiros,
America/Recife por padrão. Dependências diretas fixadas após consulta ao PyPI.

- `domain.py`: valores, categorias, comandos estruturados e formatação.
- `repository.py`: conexões curtas, WAL, busy_timeout, migrações versionadas.
- `config.py`: variáveis de ambiente e configuração sem credenciais na TUI.
- `bot.py`: autorização, comandos, confirmações e polling/reconexão.
- `tui.py`: filtros, indicadores e histórico com atualização em um segundo.
- `cli.py`: comandos de inicialização, demonstração e backup consistente.

Etapas: (1) núcleo e persistência, (2) fluxo Telegram/dashboard, (3) segurança,
confirmação e reconexão, (4) validação e documentação. Testes independentes por
agentes; integração e commits sob responsabilidade do desenvolvedor principal.

Decisões: descrição obrigatória; data opcional `@AAAA-MM-DD` antes de `|`;
categorias armazenadas sem acentos, com aliases acentuados aceitos. Saldo inicial
é gravado só na inicialização. Filtros afetam histórico; mês afeta também resumo
e gráfico. Saldo atual sempre considera todas as datas, inclusive futuras.
