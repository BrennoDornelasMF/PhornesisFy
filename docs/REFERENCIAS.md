# Referências e decisões para o MVP

Pesquisa em fontes oficiais realizada em 13/10/2026. As lições abaixo são propostas para o PhronesisFy, não funcionalidades copiadas nem dependências desses produtos.

## Aplicações relacionadas

| Referência | O que resolve | Lição aplicada | Diferença para nosso escopo |
| --- | --- | --- | --- |
| [hledger](https://hledger.org/) | Finanças em arquivos de texto, relatórios e interface de terminal `hledger ui`. | Histórico consultável, filtros e navegação por teclado devem ser centrais. | Possui um modelo contábil mais amplo; não precisamos introduzir partidas dobradas nem importar bancos no MVP. |
| [Ledger](https://ledger-cli.org/) | Contabilidade de partidas dobradas pela linha de comando; apresenta saldos e registros. | Dados estruturados e cálculos explícitos ajudam a conferir os resultados. | Sua entrada por arquivo textual não atende diretamente ao fluxo de registro pelo Telegram. |
| [Actual Budget](https://actualbudget.org/) | Gerenciamento financeiro local, categorias, relatórios e orçamento por envelopes, com sincronização opcional. | Separar armazenamento local da experiência de consulta e tornar categorias fáceis de entender. | O MVP não terá envelopes, sincronização, servidor nem integração bancária. |
| [btop](https://github.com/aristocratos/btop) | Monitor de recursos com painéis, temas, gráficos e navegação responsiva. | Fundo escuro, bordas, títulos claros, barras e legenda de teclas. | É uma referência visual, não um sistema financeiro nem uma biblioteca a incorporar. |

A documentação do btop também destaca suporte do terminal a UTF-8, cores e caracteres de borda. Por isso, valores e rótulos textuais devem continuar compreensíveis quando cores ou gráficos não forem ideais. Barras simples evitam depender de símbolos Braille especiais.

## Compatibilidade de dependências

Metadados publicados no PyPI consultados diretamente durante a pesquisa:

| Pacote | Versão observada | Python requerido | Fonte |
| --- | --- | --- | --- |
| Textual | 8.2.8 | >=3.9, <4.0 | [Metadados oficiais](https://pypi.org/pypi/textual/json) |
| python-telegram-bot | 22.8 | >=3.10 | [Metadados oficiais](https://pypi.org/pypi/python-telegram-bot/json) |
| pytest | 9.1.1 | >=3.10 | [Metadados oficiais](https://pypi.org/pypi/pytest/json) |

Python 3.12 satisfaz esses requisitos declarados. A confirmação prática de instalação e execução pertence aos testes do projeto; compatibilidade declarada não substitui validação. Versões ficam fixadas no projeto para tornar a primeira entrega reproduzível.

Fontes de uso: [Textual — primeiros passos](https://textual.textualize.io/getting_started/), [python-telegram-bot — documentação estável](https://docs.python-telegram-bot.org/en/stable/). A documentação estável pode mudar depois desta data.

## Telegram: comportamento e limites

Segundo a [Bot API oficial](https://core.telegram.org/bots/api#getting-updates):

- Long polling (`getUpdates`) e webhook são mecanismos mutuamente exclusivos.
- Atualizações pendentes permanecem nos servidores por **no máximo 24 horas**. Deixar o computador desligado por mais tempo pode perder comandos; não existe sincronização instantânea com um computador desligado.
- `update_id` identifica a atualização. O banco precisa impedir reprocessamento, inclusive depois de excluir uma movimentação; apenas uma restrição na tabela de movimentações não basta se a linha for apagada.
- Um `offset` maior que o ID confirma a atualização para o Telegram. Esse mecanismo de entrega não substitui a idempotência transacional local.
- O parâmetro `timeout` positivo habilita long polling e reduz solicitações desnecessárias.

O modo local mantém o banco no computador, mas as mensagens passam pela infraestrutura do Telegram. Não devemos apresentar isso como comunicação inteiramente local.

A [documentação de `Application.run_polling`](https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html#telegram.ext.Application.run_polling) informa que a inicialização usa `bootstrap_retries=0` por padrão e diferencia essa fase do polling normal. Reconexão durante operação e falha antes de iniciar são cenários diferentes; ambos precisam de espera controlada. Não descartar mensagens pendentes automaticamente na inicialização.

Autorizar pela combinação de ID numérico do usuário e conversa privada em todos os caminhos, incluindo botões de confirmação. Uma confirmação deve carregar uma referência específica à operação e ser validada contra a pendência armazenada, sem depender apenas do texto exibido. Os IDs de usuário e chat são campos distintos da API.

## SQLite e processos independentes

O [modo WAL do SQLite](https://www.sqlite.org/wal.html) permite leitura e escrita concorrentes, embora continue existindo apenas um escritor por vez. É adequado ao bot e dashboard executados no mesmo computador. Não armazenar esse banco em um sistema de arquivos de rede.

Decisões práticas: transações curtas; tempo de espera para bloqueios; nenhuma chamada à rede dentro de uma transação; cálculos monetários em centavos inteiros; migrações versionadas. Para backup com o banco em uso, utilizar o mecanismo de backup do SQLite, pois copiar apenas o arquivo principal pode ignorar dados ainda presentes no WAL.

## Consequência para a primeira entrega

O fluxo mais simples é Telegram → autorização → validação → serviço financeiro → SQLite. A TUI consulta esse mesmo banco periodicamente, sem servidor HTTP. Saldo acumulado e resultado mensal são consultas diferentes. Filtros do histórico não devem mudar a definição dos indicadores do mês selecionado.

As referências não justificam ampliar o escopo: uma conta, BRL, categorias fixas, registro estruturado, exclusão confirmada e modo demonstrativo separado são suficientes para validar a primeira versão.
