# PhronesisFy

Controle financeiro pessoal para Ubuntu: **dashboard interativo no terminal** e
**registro estruturado pelo Telegram**, com uma conta, um usuário autorizado e
valores em reais. O banco fica no computador. Interface escura inspirada nos
painéis do btop, com bordas, barras e atalhos de teclado.

```text
Telegram → bot Python (long polling) → validação → SQLite local
                                                     ↑
                                        dashboard Textual (1s)
```

Bot e dashboard são processos independentes. Não há servidor HTTP, portas a
abrir no roteador ou hospedagem em nuvem.

## Instalação rápida no Ubuntu

Python 3.12 ou superior. Ubuntu 24.04 já disponibiliza Python 3.12. Os comandos
abaixo devem ser executados no diretório do projeto:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python -m pip check
```

Somente a instalação opcional de pacotes Ubuntu usa `sudo`. Não execute o
aplicativo ou o pip do ambiente virtual como root.

Veja o passo a passo completo em [INSTALACAO-E-USO.md](docs/INSTALACAO-E-USO.md).

## Experimente sem Telegram

```bash
source .venv/bin/activate
phronesisfy dashboard --demo
```

Cria dados fictícios em `~/.local/share/phronesisfy/demo.db`, separados do banco
pessoal. Não pede token e não conecta ao Telegram. As amostras são inseridas
somente uma vez; para gerar outra demonstração, com o dashboard fechado,
renomeie o banco demo e seus arquivos auxiliares ou use outro `XDG_DATA_HOME`.
O mês dos dados é o mês da primeira criação, não necessariamente o mês atual.
Nunca configure o banco pessoal com o caminho reservado `demo.db`.

## Configurar o Telegram

1. No Telegram, converse com o **[@BotFather](https://t.me/BotFather)**, envie
   `/newbot`, escolha nome e username e copie o token fornecido.
2. Descubra seu **ID numérico**, não o username. Uma opção é enviar mensagem ao
   `@userinfobot` (serviço de terceiro; use apenas para obter o ID), ou consultar
   `from.id` de uma mensagem sua pelo método oficial `getUpdates`. Não publique
   resposta bruta, URL com token ou histórico financeiro.
3. Crie a configuração local:

```bash
cp .env.example .env
chmod 600 .env
```

Edite `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=TOKEN_FORNECIDO_PELO_BOTFATHER
TELEGRAM_USER_ID=123456789
PHRONESISFY_TIMEZONE=America/Recife
PHRONESISFY_INITIAL_BALANCE=0,00
```

O arquivo `.env` **não é carregado automaticamente**. Carregue suas variáveis
no shell antes de executar os processos:

```bash
set -a
source .env
set +a
phronesisfy init
```

`PHRONESISFY_INITIAL_BALANCE` aceita zero ou valor negativo, sem separadores de
milhar. É gravado apenas na criação do banco e não entra nas receitas do mês.
Alterar a variável depois não modifica o saldo inicial persistido.

## Executar

Terminal 1 — deixe aberto enquanto quiser receber comandos:

```bash
source .venv/bin/activate
set -a
source .env
set +a
phronesisfy bot
```

Terminal 2 — dashboard:

```bash
source .venv/bin/activate
set -a
source .env
set +a
phronesisfy dashboard
```

Fechar o dashboard com `q` não encerra o bot. `Ctrl+C` no terminal do bot o
encerra. Para manter o bot independente de um terminal, há instruções opcionais
para um serviço de usuário systemd no guia. Nada é ativado automaticamente.

## Comandos e exemplos

```text
/start
/ajuda
/entrada 2500,00 salario | Salário mensal
/saida 35.90 alimentacao | Almoço
/saida 20 lazer @2026-10-01 | Cinema
/saldo
/resumo
/ultimas
/excluir 12
/cancelar
```

Sintaxe: `/entrada VALOR CATEGORIA [@AAAA-MM-DD] | DESCRIÇÃO`, ou `/saida`.
Descrição obrigatória, 1 a 200 caracteres, sem quebras de linha/controles.
Data padrão: hoje no fuso configurado. Datas passadas e futuras são permitidas;
**saldo atual inclui todas as movimentações salvas, inclusive futuras**.

Valores: `35,90`, `35.90`, `35` e `35,9`. Não use `R$`, sinais, zero, negativos,
notação científica ou milhar (`1.250,50`, `1.250`): use `1250,50`.
Limite por movimentação: R$ 999.999.999,99.

- Receitas: `salario`, `freelance`, `outros`.
- Despesas: `alimentacao`, `transporte`, `moradia`, `saude`, `educacao`, `lazer`,
  `outros`.
- Aliases com acentos, como `salário` e `alimentação`, também são aceitos.

A resposta de registro contém ID, tipo, valor, categoria, descrição, data e
saldo atualizado, somente após salvar. Mensagens inválidas não geram registros.
Mensagens editadas são ignoradas: exclua o lançamento incorreto e registre um
novo. Cada mensagem nova tem seu próprio update ID e é um novo lançamento,
mesmo se o texto for igual; reprocessar o mesmo update não duplica a operação.

`/excluir ID` mostra o lançamento e um botão de confirmação válido por 5
minutos. A confirmação é vinculada ao usuário, conversa, ID e nonce. Uma nova
solicitação substitui a anterior; botões antigos não excluem nem cancelam a
solicitação atual. `/cancelar` cancela a pendência. Os dados da movimentação
excluída são removidos, mas update ID e ID do lançamento ficam em uma tabela
separada para impedir recriação por reprocessamento.

## Dashboard

- **Saldo atual:** saldo inicial + todas as receitas − todas as despesas.
- **Receitas/despesas/resultado do mês:** apenas o mês selecionado; resultado =
  receitas − despesas, sem saldo inicial.
- Barras de despesas por categoria: mês selecionado.
- Histórico: ID, data, tipo, categoria, descrição e valor; filtrado por mês,
  tipo e categoria. Filtros de tipo/categoria não alteram indicadores e barras.
- Consulta automática a cada segundo, preservando filtro, foco, linha pelo ID
  e rolagem. Não muda sozinho o mês à meia-noite ou na virada do mês.

Atalhos: `Tab`/`Shift+Tab` alternam foco; `m` foca mês; `h` foca histórico; `r`
atualiza; `q` sai. `Ctrl+←` e `Ctrl+→` mudam o mês. No histórico use setas e
`PgUp`/`PgDn`; nos seletores use Enter e setas. Enquanto digita num campo,
letras são texto; saia do campo com Tab antes de usar `q`, `m`, `h` ou `r`.

Mínimo: **80 colunas × 24 linhas**, com layout mais confortável em 120 × 35 ou
maior. Terminais menores recebem um aviso. Colunas largas usam rolagem
horizontal. O painel de categorias recebe foco com Tab e rola com setas/PgUp/PgDn. Valores e tipos têm rótulos explícitos, não dependem só de cores.

## Banco e backup

Banco pessoal padrão: `~/.local/share/phronesisfy/finance.db`.
`XDG_DATA_HOME` muda a pasta base; `PHRONESISFY_DB` permite outro caminho.
Use armazenamento local, não pasta de rede nem banco compartilhado por bots
com tokens diferentes. Variáveis são lidas ao iniciar cada processo; ambos
precisam usar o mesmo caminho pessoal. `.env`, bancos e logs são ignorados pelo
Git; não acrescente dados pessoais com `git add -f`.

Backup consistente com os processos ativos:

```bash
phronesisfy backup "$HOME/Backups/phronesisfy-2026-10-13.db"
```

O destino deve ser um arquivo novo. O comando usa a API de backup SQLite,
incluindo dados do WAL. Copiar só `finance.db` durante uso pode perder dados
recentes. Para restaurar, encerre bot e dashboard e aponte `PHRONESISFY_DB` para
a cópia restaurada, usando um caminho novo; consulte detalhes no guia.

Migrações utilizam `PRAGMA user_version`. Saldo inicial, offset e prevenção de
reprocessamento fazem parte do backup. Datas de criação têm fuso explícito;
valores monetários são inteiros em centavos. Transações curtas, WAL e timeout
de bloqueio permitem leitores e escritor no mesmo computador.

## Segurança e limites de funcionamento

Somente o ID autorizado em conversa privada pode consultar ou alterar dados,
inclusive nas confirmações. Comandos de terceiros são ignorados; callbacks
recebem somente um aviso genérico. Tokens não aparecem em representações da
configuração nem nos logs da aplicação. Logs HTTP verbosos não são habilitados.
O computador e sua conta local continuam responsáveis pela proteção do banco;
este MVP não fornece criptografia do SQLite.

O bot precisa estar ativo e o computador ligado e conectado. Mensagens passam
pelo Telegram; o banco fica no computador. Mensagens enviadas enquanto o bot
está offline só podem ser processadas depois se ainda estiverem disponíveis:
a Bot API mantém atualizações por **no máximo 24 horas**. Não existe
sincronização instantânea com computador desligado. [Fonte oficial](https://core.telegram.org/bots/api#getting-updates).

Falhas de rede recebem espera progressiva de 1 a 60 segundos, inclusive na
inicialização; limites do Telegram respeitam `retry_after`. Não há garantia de
entrega da resposta: uma operação pode ter sido salva mesmo se a confirmação
falhar na rede. Antes de reenviar como nova mensagem, consulte `/ultimas` e
`/saldo`. A deduplicação protege reprocessamento do mesmo update, não duas
mensagens distintas.

Fora do MVP: integração bancária, investimentos, cartões, parcelas, múltiplas
contas/usuários, IA, nuvem, edição e orçamento por envelopes.

## Testes e desenvolvimento

```bash
source .venv/bin/activate
python -m pytest -q
python -m pip check
```

Testes usam bancos temporários, bot simulado e TUI headless. Não usam token ou
rede Telegram. A validação real requer configurar o bot e enviar receita,
despesa, consulta e exclusão enquanto o dashboard está aberto.

Estrutura: `src/phronesisfy/{domain,repository,config,bot,tui,cli}.py` e `tests/`.
Veja [arquitetura](docs/ARQUITETURA.md), [pesquisa de referências](docs/REFERENCIAS.md),
[registro de implementação](docs/PROGRESSO.md) e [instalação/uso](docs/INSTALACAO-E-USO.md).
Dependências diretas fixadas no pyproject.toml e transitivas em requirements.lock.

## Problemas comuns

| Sintoma | Como resolver |
| --- | --- |
| `phronesisfy: command not found` | Ative `.venv` e instale o projeto com `pip install --no-deps -e .`. |
| `No module named venv`/erro ensurepip | Instale `python3-venv` antes de criar o ambiente. |
| Bot pede configuração | Carregue `.env` no shell; confira token e ID numérico. |
| Bot não responde | Confira usuário autorizado, conversa privada, internet e processo ativo. |
| Outro bot ativo/conflito | Encerre a outra instância, inclusive serviços systemd; use apenas um consumidor do token. |
| Dashboard não mostra dados | Confira o caminho, filtro mensal/tipo/categoria e se iniciou com `--demo`. |
| Banco indisponível | Confira espaço, permissões e outras ferramentas segurando transações; use disco local. |
| Interface sem cores | Confira se `NO_COLOR` está definido; para esta execução use `env -u NO_COLOR phronesisfy dashboard`. |
| Terminal pequeno ou símbolos estranhos | Aumente a janela, use terminal UTF-8 e fonte monoespaçada. |
| Valor/categoria rejeitados | Use valores sem milhar e as categorias de `/ajuda`. |
