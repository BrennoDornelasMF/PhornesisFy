# Instalação e uso passo a passo no Ubuntu

## 1. Abra o projeto

No Orca, use o terminal do checkout que contém esta versão do código. Em um
terminal comum, para o diretório original:

```bash
cd ~/Code/PhronesisFy
```

Se estiver num worktree do Orca, o caminho será diferente. Para serviço systemd,
use um checkout estável; não aponte para um worktree que poderá ser removido.

## 2. Prepare o ambiente

```bash
python3 --version
sudo apt update
sudo apt install python3 python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python -m pip check
phronesisfy --help
```

Requer Python >=3.12. Ambiente validado: Ubuntu 24.04, Python 3.12.3. Pacotes
Ubuntu só são necessários se ainda não estiverem instalados. Não modifique o
Python global com pip/sudo; cada novo terminal precisa ativar `.venv`.

## 3. Veja a interface com dados fictícios

```bash
phronesisfy dashboard --demo
```

É seguro experimentar antes de configurar o Telegram: a demo usa outro banco,
sem rede. Ajuste filtros com Tab/Enter/setas. Use `m` para o campo mês,
`Ctrl+←`/`Ctrl+→` para navegar meses, `h` para histórico e `q` para sair.
Mínimo 80 × 24; recomendado 120 × 35. Se estiver digitando num campo, pressione
Tab para sair dele antes de usar atalhos de letras.

A demo é persistente e criada só uma vez. Para uma demo independente:

```bash
XDG_DATA_HOME="$HOME/.local/share/phronesisfy-experimento" phronesisfy dashboard --demo
```

Isso não mexe no banco pessoal padrão. Quando retornar aos dados reais, omita
`--demo` e a variável temporária. Não use tokens reais em demonstrações.

## 4. Crie seu bot

No aplicativo Telegram:

1. Abra o perfil oficial [@BotFather](https://t.me/BotFather).
2. Envie `/newbot`.
3. Escolha o nome e um username terminado em `bot`.
4. Guarde o token em `.env`, nunca no código ou numa issue/commit.
5. Abra a conversa privada com o bot criado e envie `/start` depois de iniciar
   o processo local.

Token identifica o bot; ID numérico identifica seu usuário. Para descobrir o
ID, pode usar `@userinfobot`, um terceiro que não precisa receber dados
financeiros, ou uma ferramenta local usando a Bot API oficial. O campo correto
é `message.from.id` numa atualização enviada por você — não username nem ID de
grupo. Não compartilhe o token para solicitar ajuda. Se ele vazar, revogue no
BotFather e atualize `.env`.

## 5. Configure o banco e o saldo inicial

```bash
cp .env.example .env
chmod 600 .env
```

Abra `.env` no editor do Orca ou `nano .env`:

```dotenv
TELEGRAM_BOT_TOKEN=SEU_TOKEN
TELEGRAM_USER_ID=SEU_ID_NUMERICO
PHRONESISFY_TIMEZONE=America/Recife
PHRONESISFY_INITIAL_BALANCE=1250,50
# Opcional; mesma configuração nos dois processos:
# PHRONESISFY_DB=/home/SEU_USUARIO/.local/share/phronesisfy/finance.db
```

Troque os placeholders pelos valores reais. Não inclua `export` nas linhas se
for utilizar o mesmo arquivo no systemd. Use fuso IANA, como America/Recife.
O arquivo é configuração shell confiável: não carregue `.env` de terceiros.

```bash
set -a
source .env
set +a
phronesisfy init
```

Pense no saldo inicial antes do primeiro `init`, dashboard ou bot pessoal: todos
inicializam o banco se ele não existir. Ele é gravado uma única vez, aceita zero
ou negativo e não conta como receita mensal. Alterar a variável depois não
reescreve o banco. Para começar outro histórico, feche ambos os processos,
faça backup e escolha um caminho novo em PHRONESISFY_DB.

## 6. Inicie os dois processos

Terminal A:

```bash
source .venv/bin/activate
set -a
source .env
set +a
phronesisfy bot
```

Terminal B, no mesmo projeto:

```bash
source .venv/bin/activate
set -a
source .env
set +a
phronesisfy dashboard
```

Fechar a TUI não interrompe o bot; fechar o terminal do bot normalmente o
interrompe. Ctrl+C encerra o bot. Mantenha apenas uma instância do token,
mesmo que use bancos diferentes. O lock impede duplicidade no mesmo banco;
a API Telegram acusa conflito entre consumidores do mesmo bot. O programa
remove webhook ao iniciar long polling, preservando atualizações pendentes.

## 7. Faça a primeira movimentação

Na conversa privada do bot:

```text
/entrada 2500,00 salario | Salário mensal
/saida 35,90 alimentacao | Almoço
/saldo
/resumo
/ultimas
```

Se o saldo inicial for R$ 1.250,50 e o banco não tiver outros registros, após
esses lançamentos o saldo será **R$ 3.714,60**. O resultado do mês será
**R$ 2.464,10**, sem contar o saldo inicial. Na TUI, os registros devem aparecer
até a próxima consulta de 1 segundo. Se não aparecerem, confira o mês/filtros e
o caminho do banco nos dois processos.

Categorias de receita: salario, freelance, outros. Despesa: alimentacao,
transporte, moradia, saude, educacao, lazer, outros. Acentos aceitos.

Data opcional antes da barra:

```text
/saida 20,00 lazer @2026-10-01 | Cinema
```

Datas futuras são aceitas como movimentações já registradas e entram no saldo
acumulado; o MVP não distingue agendamento de movimentação efetiva. Descrição
é obrigatória e deve ficar numa linha com até 200 caracteres. Valores positivos,
sem milhar: `1250,50` ou `1250.50`. Mensagem inválida não é salva.

## 8. Corrija um lançamento

1. Envie `/ultimas` e identifique o ID.
2. Envie `/excluir ID`, por exemplo `/excluir 12`.
3. Confira os detalhes e toque em **Confirmar exclusão** dentro de 5 minutos.
4. Confira o saldo/resumo atualizado.
5. Se necessário, envie um novo lançamento correto.

`/cancelar` ou o botão Cancelar encerra a pendência. Pedir outra exclusão
substitui a anterior. Um botão antigo não opera sobre a nova solicitação.
Editar a mensagem original no Telegram não edita o banco. Não há desfazer da
exclusão; registre novamente ou recupere um backup em banco separado.

Se uma confirmação de registro não chegar por falha de rede, consulte
`/ultimas` antes de mandar outra mensagem: a gravação pode já ter ocorrido.
Reprocessamento do mesmo update não duplica; duas mensagens iguais diferentes
são dois lançamentos.

## 9. Backup e restauração

Para consultar o caminho efetivo, execute `phronesisfy init` (não altera banco
existente). Por padrão, `~/.local/share/phronesisfy/finance.db`. Pode haver
arquivos `finance.db-wal`, `finance.db-shm` e `finance.db.bot.lock`.

Com as mesmas variáveis carregadas:

```bash
mkdir -p "$HOME/Backups"
phronesisfy backup "$HOME/Backups/phronesisfy-2026-10-13.db"
```

Escolha um nome ainda não existente. O backup pode ocorrer com bot/TUI ativos,
pois usa a API SQLite. Não copie somente o arquivo principal enquanto o banco
estiver em uso. Proteja a cópia: ela contém dados financeiros, saldo inicial e
marcadores de reprocessamento.

Para restaurar sem sobrescrever o original:

1. Pare bot e dashboard, inclusive serviço se estiver usando.
2. Copie o backup para um **caminho novo**, sem arquivos WAL/SHM antigos.
3. Atualize PHRONESISFY_DB no `.env` para esse caminho.
4. Recarregue o ambiente em ambos os terminais e inicie novamente.
5. Confira `/saldo`, `/ultimas` e resumo antes de continuar registrando.

Exemplo:

```bash
cp "$HOME/Backups/phronesisfy-2026-10-13.db" "$HOME/.local/share/phronesisfy/finance-restaurado.db"
chmod 600 "$HOME/.local/share/phronesisfy/finance-restaurado.db"
```

Restaurar um backup antigo recua histórico, confirmações e offset ao momento da
cópia. Updates ainda disponíveis poderão ser reprocessados; operações posteriores
ao backup precisam ser conciliadas. Não há sincronização com o histórico todo
do Telegram nem recuperação garantida de mensagens com mais de 24 horas.

## 10. Opcional: serviço de usuário systemd

Esta seção é manual; a aplicação não instala nem ativa serviços. Execute como
seu usuário, sem `sudo systemctl`. Prepare `.env`, ambiente virtual e banco
com `phronesisfy init` antes de habilitar o serviço.

```bash
mkdir -p ~/.config/systemd/user
```

Crie `~/.config/systemd/user/phronesisfy-bot.service`:

```ini
[Unit]
Description=PhronesisFy Telegram bot local

[Service]
Type=simple
WorkingDirectory=%h/Code/PhronesisFy
EnvironmentFile=%h/Code/PhronesisFy/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=%h/Code/PhronesisFy/.venv/bin/phronesisfy bot
Restart=on-failure
RestartSec=10
UMask=0077

[Install]
WantedBy=default.target
```

Adapte os três caminhos se o checkout estiver em outro local. O systemd não
herda as variáveis do seu terminal; `EnvironmentFile` é necessário. Pare uma
instância manual do bot antes de iniciar o serviço.

```bash
systemctl --user daemon-reload
systemctl --user enable --now phronesisfy-bot.service
systemctl --user status phronesisfy-bot.service
journalctl --user -u phronesisfy-bot.service -n 30
```

Para parar ou desativar:

```bash
systemctl --user stop phronesisfy-bot.service
systemctl --user disable phronesisfy-bot.service
```

Após alterar `.env`, use `systemctl --user restart phronesisfy-bot.service`.
Serviço de usuário normalmente depende da sessão do usuário. Permanência após
logout exige configurar linger explicitamente (`loginctl enable-linger`);
isso não é feito pelo projeto e pode exigir permissão administrativa. Nenhum
serviço processa mensagens com o computador desligado ou sem internet.

## 11. Confira a instalação e conheça os limites

```bash
python -m pytest -q
python -m pip check
```

A suíte valida domínio, autorização, confirmação, concorrência, persistência,
duplicatas, backup, reconexão simulada e TUI headless. Não substitui a validação
com seu bot real. Faça o roteiro: iniciar TUI/bot → receita → despesa → saldo →
exclusão confirmada → reiniciar → conferir persistência → fechar TUI → registrar
outra mensagem → reabrir TUI.

Dúvidas frequentes e limites estão no [README](../README.md). Pesquisas em
[REFERENCIAS.md](REFERENCIAS.md), decisões em [ARQUITETURA.md](ARQUITETURA.md) e
etapas/validações em [PROGRESSO.md](PROGRESSO.md).
