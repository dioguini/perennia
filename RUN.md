# Como instalar e correr a Perennia

Este guia leva-te do zero à aplicação a correr. Tudo funciona offline.

**Se vens da versão antiga (VeloLocal), não tens de fazer nada à mão.** Na primeira vez que
abres a Perennia, ela **renomeia** a pasta de dados antiga (`VeloLocal` / `velolocal`) para
`Perennia` / `perennia` (uma só operação, na mesma pasta-mãe, sem copiar nada), a base `velolocal.db`
passa a `perennia.db`, e os caminhos e o formato das sessões antigas que estavam guardados na base
são atualizados. Fica tudo na mesma. Se as duas pastas existirem, a nova ganha e a antiga fica
intacta (nada se apaga). Os `.fit` novos chamam-se `perennia_<data>_<nome>.fit`. Daqui para a frente,
**o nome VeloLocal só existe num ficheiro do código** (`perennia/legacy.py`, que faz esta migração).

---

## 1. O que precisas

**Python 3.11 ou superior.** Mais nada — as três bibliotecas instalam-se com
um comando e são todas de código aberto e multiplataforma.

Verifica o que tens:

```bash
python3 --version      # Linux, macOS, Raspberry Pi
python --version       # Windows
```

Se não tiveres Python, instala-o:
- **Windows**: https://www.python.org/downloads/ — na primeira janela do
  instalador, liga a opção **"Add Python to PATH"**, senão os comandos
  seguintes não funcionam.
- **macOS**: `brew install python` (ou o instalador do python.org)
- **Debian / Ubuntu / Raspberry Pi OS**: `sudo apt install python3 python3-pip python3-venv`
- **Fedora**: `sudo dnf install python3 python3-pip`
- **Arch**: `sudo pacman -S python python-pip`

---

## 2. Instalar

Abre um terminal na pasta do projeto (a que tem o `main.py`) e corre:

### Linux, macOS, Raspberry Pi

```bash
cd perennia
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
cd perennia
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Se o PowerShell recusar o `Activate.ps1`, corre uma vez:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

> O ambiente virtual (`.venv`) mantém estas bibliotecas separadas do resto do
> sistema. Tens de o ativar sempre que abres um terminal novo — é a linha
> `source .venv/bin/activate` ou `.\.venv\Scripts\Activate.ps1`.

---

## 3. Verificar que funciona, antes de ligar qualquer coisa

```bash
python main.py --self-test
```

Deve imprimir algo como:

```
  rota: Serra de Teste — 5.99 km, 1 subida(s)
  sessão: 5.99 km em 14.5 min, 243 W médios, TSS 24
  .fit: 24821 bytes, 869 registos — CRC ok
núcleo OK
```

Isto importa um GPX, deteta a subida, corre uma sessão inteira com um
ciclista simulado, grava na base de dados e escreve um `.fit` válido — sem
abrir janela e sem hardware. Se isto passar, o núcleo está bom nesta máquina.

Para correr a bateria de testes completa (560 testes, ~60 s):

```bash
python -m unittest discover -s tests -t .
```

---

## 4. Abrir a aplicação

```bash
python main.py
```

Outras opções:

```bash
python main.py --fullscreen
python main.py --window                 # em janela, mesmo que da última vez não fosse
python main.py --width 1920 --height 1080
python main.py --data-dir ./dados       # base de dados nesta pasta
PERENNIA_FPS=1 python main.py               # mostra os fotogramas por segundo
```

**Resolução.** Não precisas destas opções: em **Definições → Resolução**,
Enter percorre as janelas que cabem no teu monitor (1280×720, 1366×768,
1600×900, 1920×1080, 2560×1440, 3840×2160) e o ecrã inteiro. **F11** alterna
o ecrã inteiro em qualquer altura, também a meio de uma sessão, e podes
arrastar os cantos da janela. A aplicação abre sempre como a fechaste. O
mínimo é 1024×640, porque abaixo disso o HUD não cabe. O ecrã inteiro usa a
resolução do monitor.

**Suavização (antialiasing).** A janela abre com antialiasing 4×: a estrada,
as linhas dos gráficos e o contorno do perfil saem sem serrilhado. Se a
placa gráfica não aceitar 4×, a aplicação tenta 2× e depois sem, sozinha.
Num computador lento ou num Raspberry Pi podes baixar para 2× ou desligar em
**Definições → Suavização**; a mudança aplica-se ao reabrir a aplicação.

### Abrir como uma app, sem o PyCharm

O PyCharm serve para **programar**; para **usar** a Perennia não precisas dele. Há dois caminhos
e os **dados são os mesmos** nos dois (a mesma base de dados, os mesmos `.fit`), por isso podes
trocar à vontade.

**Caminho 1 — o mais rápido (usa o teu projeto, tal como está):**

| Sistema | Como |
|---|---|
| **Windows** | duplo clique em **`Perennia.bat`**. Usa o ambiente virtual do projeto (`.venv`, o que o PyCharm criou, ou o da secção 2) e abre **sem a janela preta**. |
| **macOS / Linux / Raspberry Pi** | `./perennia.sh` (no terminal, ou duplo clique se o gestor de ficheiros deixar). |

Depois de um `git pull` a versão nova já é a que abre: não há nada para reconstruir. Se a
aplicação fechar com um erro, fica em **`perennia-erro.log`** na pasta dos dados (secção 8); para
veres as mensagens em direto, abre um terminal e corre `python main.py`.

**Um ícone no Ambiente de trabalho (Windows):** duplo clique em **`criar_atalho_windows.bat`**.
Aparece o atalho **Perennia**, com o ícone da aplicação. Botão direito no atalho → *Fixar na barra
de tarefas* (ou *Fixar no Iniciar*) e já a abres como qualquer outra app. Se já fizeste o build
(caminho 2), o atalho aponta para o `Perennia.exe`; senão, para o ambiente do projeto.

**Caminho 2 — uma app a sério (`Perennia.exe`, sem precisar de Python):**

1. Duplo clique em **`build_windows.bat`** (uns minutos da primeira vez; é o da secção 7). Corre o
   autoteste e empacota. No fim tens **`dist\Perennia\Perennia.exe`**, já com o ícone.
2. Duplo clique em **`criar_atalho_windows.bat`** outra vez: o atalho passa a apontar para ele.
   (Ou arrasta o `Perennia.exe` para o Ambiente de trabalho com *Alt* carregado, para criar um atalho.)
3. Para teres uma versão nova da app depois de um `git pull`, voltas a correr o `build_windows.bat`.
   A pasta `dist` não vai para o git. Os dados ficam, que estão em `%APPDATA%\Perennia`.

No Mac e no Linux o empacotamento é o `./build.sh` (sai `dist/Perennia-mac.zip`, com a
`Perennia.app` lá dentro: arrasta-a para a pasta *Aplicações*). O GitHub também a pode gerar sozinho
(secção 7, «Alternativa: o GitHub faz tudo»).

**Linux com ícone no menu de aplicações:** cria o ficheiro `~/.local/share/applications/perennia.desktop`
com (troca `/caminho/para` pela pasta do projeto):

```ini
[Desktop Entry]
Type=Application
Name=Perennia
Exec=/caminho/para/perennia/perennia.sh
Icon=/caminho/para/perennia/perennia/assets/app_icon.png
Terminal=false
Categories=Sports;
```

O ícone da aplicação está em `perennia/assets/app_icon.png` (janela) e `packaging/perennia.ico` (o `.exe`);
`python tools/make_app_icon.py` volta a desenhá-los.

### Primeira vez, passo a passo

1. **Definições** (no topo, ou F8) → separador Atleta: mete o teu nome, ano de nascimento, peso e FTP.
   No nome, escreve diretamente com o teclado (Backspace apaga). As setas
   ←/→ ajustam os valores (no peso, 0,1 kg por toque; Shift+←/→ dá 1 kg);
   Enter alterna unidades, idioma e pausa automática.
2. **Dispositivos** (no topo, ou F4) → a janela tem um bloco por ligação: **Bluetooth**
   (`Procurar Bluetooth` encontra o trainer, a cinta e a máquina de remo) e **ANT+** (`Procurar
   ANT+` usa a antena USB). Os aparelhos encontrados ficam **por baixo** da sua ligação, recuados;
   os ligados levam o **✓** e o que estão a mandar agora («150 W · 88 rpm»); Enter liga ou desliga.
   Se ainda não quiseres hardware, o bloco **SEM HARDWARE** tem o Trainer, a Banda cardíaca, o
   Remo e a Passadeira simulados e podes experimentar a aplicação toda. No fim da janela, **Dispositivos
   ligados** é só uma lista informativa (sem ações) com a ligação e os valores de cada aparelho.
3. **Ciclismo** → separador Treinar → **Sessão de treino**: abre uma
   janela (grande) com os modos da sessão — **Livre**, **Carregar
   treino**, **Do computador**, **Challenge** e **Testes**. Tudo pode ser
   uma sessão de treino; muda só o modo, e escolhe-se na mesma janela (Esc
   volta ao passo anterior).
   - **Carregar treino** mostra a lista de treinos ali mesmo; a ficha do
     treino tem, em baixo à direita, **Configurar sessão de treino** (Enter).
   - **Livre** passa logo à preparação da sessão.
4. Na **janela da sessão** escolhes tudo de uma vez: **Aparelhos** (Enter
   abre o emparelhamento), **Rota (.gpx)** (Enter abre a lista das tuas
   rotas numa janela) ou **Carregar um .gpx novo** (procura na pasta `gpx/` ao lado do `main.py`, em Transferências
   e em Documentos), **Segmentos do Strava** dessa rota, **Modo de sessão**
   (sozinho ou comparação), ERG (nos treinos ERG) e **Auto lap**. A sessão
   livre precisa de uma rota; num treino a rota é opcional. **Por agora, as sessões de treino
   não desenham o mundo 3D**: o fundo é da cor do tema (a sessão livre, com rota, continua a ter
   a estrada). A qualidade do 3D está em Definições → Ecrã e idioma.
   O mundo é construído antes de arrancar — vês a barra "A preparar a rota".
5. Pedala.

**Strava sem internet.** Se, ao procurar os segmentos, a aplicação não
conseguir ligar-se ao Strava, aparece o aviso **«Não foi possível ligar ao
Strava»** com duas escolhas: **Prosseguir sem Strava** (a sessão corre igual,
sem os segmentos) ou **Cancelar a sessão**.

### Teclas durante a sessão

As teclas são **as mesmas em todos os desportos** — ciclismo, corrida, natação, remo e ginásio:

| Tecla | O que faz |
|---|---|
| **L** | marca uma **volta** (como nos Garmin) |
| **P** ou clique em **❚❚ Pausa** | **pausa** — abre o aviso **PAUSA** ao centro — e retoma |
| **Esc** | também pausa (abre o **PAUSA**) e **não termina** por acidente; com o PAUSA aberto, Esc retoma |
| **F10** ou clique em **■ Terminar** | pergunta «Terminar a sessão?»; Sim grava o `.fit` e vai para o resumo, Não volta |
| **D** (na pergunta de terminar) | **Terminar sem guardar**: apaga a sessão, sem `.fit` nem histórico |
| **N** | **saltar bloco**: o passo do treino (ciclismo, corrida, remo) ou o exercício/bloco (ginásio) |
| **Espaço** | **começar sem contagem**, durante a contagem dos 15 s (no ginásio, durante a sessão, é o Lap) |
| **+ / −** | ciclismo e remo: mais / menos **resistência** · corrida: **velocidade** · natação: + / − piscina |
| **↑ / ↓** | corrida: **declive** · ciclismo: resistência (ou intensidade, em ERG) · ginásio: linha anterior / seguinte |
| **T** | corrida: escrever o total que o visor da passadeira mostra |
| **V** | remo: outra página de campos |
| **F4** | **Dispositivos** — a sessão **fica em pausa** enquanto estiver aberto |
| **F8** | **Definições** (só algumas; ver abaixo) — a sessão **fica em pausa** |
| **F11** | ecrã inteiro |

**O aviso PAUSA.** Quando a sessão está em pausa (à mão ou por teres aberto um menu), aparece ao centro
um aviso com a palavra **PAUSA** e dois botões:

- **Retomar sessão** (clique, **P**, **Esc**, **Enter** ou **Espaço**): o tempo volta a correr;
- **Terminar treino** (clique, **F10** ou **D**): pergunta «Terminar a sessão?» (Sim · Não · Terminar
  sem guardar). Se escolheres **Não**, voltas ao PAUSA.

A **pausa automática** do ciclismo (parares de pedalar) continua a ser só um aviso no topo, que
desaparece quando pedalas; o aviso ao centro é para a pausa **à mão** e para a dos menus.

**Dispositivos e Definições durante uma sessão.** Podes abri-los a qualquer altura (F4, F8 ou os
botões da barra do topo): abrem **por cima** da sessão e **põem-na em pausa** — o tempo, o treino e o
`.fit` ficam parados. Ao fechar, a sessão **não arranca sozinha**: vês o aviso PAUSA e retomas tu.
Nas **Definições** só aparece o que se pode mexer sem estragar a sessão:

| Separador | O que tem durante a sessão |
|---|---|
| **Geral** | só os **passos seguintes** no treino |
| **Desportos** | só o separador **do desporto em que estás** (a natação não tem) |
| **Ecrã e idioma** | só **Tema, Unidades e Idioma** |
| **Atalhos de teclado** | tudo |
| **Configurações sonoras** | tudo (os bips são os mesmos para todos os desportos) |

Não aparecem o **Atleta**, as **Ligações Externas**, a resolução, a suavização… (isso muda-se fora da
sessão). **Guardar** (Ctrl+S) grava; **Esc** com alterações por guardar pergunta primeiro. Os atalhos e
os bips novos valem já ao voltar; as métricas e a disposição do ecrã, e o tema, valem por inteiro na
sessão seguinte. **Backups** e **Desligar** continuam a cinzento até terminares a sessão.

Todas as sessões (ciclismo, corrida, natação, remo, ginásio) começam com uma
**contagem de 15 s** ao centro do ecrã; a sessão só arranca no fim, ou antes se carregares em
**Espaço** (começar sem contagem). **Esc**
durante a contagem cancela (nada fica gravado). Nos **treinos estruturados**
(um treino da lista, um teste, um plano de voltas) não há auto lap para
escolher: **cada bloco feito fecha uma volta**, sozinho.

**Atalhos únicos.** As teclas destas tabelas são as de origem: em **Definições → Atalhos de
teclado** mudas qualquer uma (Enter na linha e carrega na tecla nova). **Marcar volta, Pausa / retomar,
Terminar, Começar sem contagem e Saltar bloco são uma só definição para todos os desportos**
(grupo «Sessões de treino (todos os desportos)»): mudas uma vez e vale em todos. Só ficam à parte as
que fazem sentido num desporto: a **resistência** (ciclismo e remo), a **velocidade e o declive** da
corrida e o escrever o total do visor, e a **página de campos** do remo. Se já tinhas mudado a
tecla de um desporto (por exemplo a volta do remo), essa passa para a definição única, sozinha. A
aplicação avisa se a tecla já é de outro atalho no mesmo contexto ou se é de
navegação (setas, Enter, Esc, Tab…, que são fixas; **J** e **K** também não, porque mudam de linha no
ginásio — só com Ctrl ou Alt). **Guardar** fixa,
**Cancelar** desfaz, e **Repor as teclas de origem** volta tudo atrás.

O **tempo total** fica em grande, ao centro, no topo das sessões de ciclismo, remo, corrida e natação.
Por baixo aparece o tempo da volta. **O ginásio já não tem esse relógio**: a contagem da série (por
tempo) e a do descanso vão para a métrica **Série / descanso** (ver «A sessão de força»).

**Volta automática.** Antes de começar qualquer treino há a opção **Volta
automática**, desligada por omissão. Enter alterna entre desligada, por
tempo e por distância; ←/→ escolhem o valor:

- por tempo: de 1 min a 30 min;
- por distância, conforme o desporto: ciclismo 1–10 km, remo 250 m–2 km,
  corrida 400 m–5 km (inclui a milha), natação 50–400 m.

A tecla L continua a marcar voltas à mão.

**O relógio só conta enquanto pedalas.** Ao entrar na sessão aparece
"Começa a pedalar para arrancar": o trainer já tem a resistência certa, mas
o tempo só começa à primeira pedalada.

**Pausa automática.** Se parares de pedalar, ao fim de 3 segundos a sessão
pausa sozinha ("PAUSA AUTOMÁTICA — pedala para continuar"); volta a pedalar e
continua. A exceção é uma descida: se deixares de pedalar a rolar, continuas a
descer até a bicicleta abrandar, como na estrada. Podes desligar a pausa
automática nas Definições.

Parar de pedalar conta mesmo quando os pedais continuam a emitir. A Assioma
parada repete a última mensagem, com a última potência e a última cadência.
Ao fim de 3 s sem pedaladas novas, a aplicação passa a contar potência e
cadência a zero, como manda a norma ANT+, e 3 s depois pausa. Se te
esqueceres do botão e fores à casa de banho, os pedais adormecem e a
aplicação continua à espera deles, sem limite de tempo. Quando voltares e
pedalares, acordam, são encontrados outra vez e a sessão continua. O tempo em pausa aparece no resumo, e não conta
para o tempo da sessão nem para as classificações.

**Pausa manual.** P, ou o botão **❚❚ Pausa**, pausa até carregares outra vez
— pedalar não a desfaz, para poderes ajustar a bicicleta sem a sessão
arrancar sozinha.

### O ecrã inicial

Treze cartões, **todos do mesmo tamanho** e com ícones discretos: na primeira fila os cinco desportos
(**Ciclismo**, **Remo**, **Corrida**, **Natação** e **Ginásio**), a
**Saúde** e o **Treinador**; na segunda, **Rotas**, **Segmentos**, **Estatísticas
gerais**, **Inventário de artigos**, **Exercícios** e **Longevidade**. O Calendário deixou
de ser um cartão: **está no próprio ecrã inicial** (ver abaixo), e os
**Backups e Sincronização** estão na barra do topo. Um título que não caiba numa linha parte-se em
duas (a letra nunca fica abaixo de 12 px). O título fica sempre por baixo do ícone, com a
letra a ajustar-se à largura do cartão. Escolhe-se com as setas e Enter, ou
com o rato.

Por baixo dos cartões: à esquerda, a sequência de treino, a forma e as
**próximas atividades** planeadas (só para teres noção do que aí vem; um
clique abre o dia); ao centro da página, **o calendário do mês**, grande
(com os treinos feitos e planeados). ↓ a partir da segunda fila de cartões
entra no calendário: setas mudam o dia, PgUp/PgDn o mês, T volta a hoje,
↑ na primeira semana regressa aos cartões. **Enter (ou um clique) num dia
abre-o**, numa janela: o que fizeste e o que estava planeado, a **nota do dia** (em baixo, na
própria janela), o botão **Diário de saúde** (abre a Saúde nesse dia) e **+ Planear treino**
(ver «Calendário»). O título do ecrã inicial já não tem mensagem por baixo.

**A barra do topo** (um pouco mais alta) está sempre visível, em todos os
ecrãs:

- À esquerda, os teus aparelhos com o estado: verde ligado, vermelho
  perdido, cinzento desligado.
- A **pesquisa** (Ctrl+F) fica sempre aqui, ao lado da data e da hora, com
  uma lupa: filtra a lista do separador onde estás enquanto escreves.
- À direita, a **data e a hora** («sáb 31/10/2026 · 09:05») e quatro botões:
  **Dispositivos** (F4), **Backups**, **Definições** (F8) e **Desligar**
  (Ctrl+Q). Backups fica a cinzento durante uma sessão.
- **Dispositivos** abre uma janela por cima do ecrã onde estás, também a
  meio de uma sessão — e, numa sessão, **a sessão fica em pausa** até voltares (aparece o aviso
  PAUSA). Aí ligas ou desligas cada aparelho. Quando um aparelho se desliga aparece o aviso
  "⚠ … desligou-se", e quando volta, "… voltou".
- **Definições** também abre durante uma sessão (a sessão fica em pausa), mas só com os separadores
  e as opções que se podem mexer sem a estragar (ver «Teclas durante a sessão»). **Desligar** fica
  a cinzento: termina a sessão primeiro.
- **Desligar** pergunta sempre "Sair da Perennia?". A resposta já
  escolhida é "Não", para um Enter distraído não fechar a aplicação.
- **As mensagens** («Guardado», um erro, onde ficou um ficheiro…) aparecem
  sempre no mesmo sítio — ao centro, na linha do título — a **bold**, em
  letra amarela sobre um fundo escuro, para se verem em qualquer tema.
  Duram uns segundos; as compridas passam a duas ou três linhas.

**As Definições estão em separadores**: Atleta, **Geral**, **Desportos**,
Ecrã e idioma, Ligações Externas, **Atalhos de
teclado** e **Configurações sonoras** (a Sincronização mudou-se para o menu **Backups e
Sincronização**). Tab e Shift+Tab mudam de separador; também podes clicar.

- **Atleta**: os limiares de todos os desportos — a FTP do ciclismo, a
  LTHR, a **FTP do remo**, o **ritmo de limiar da corrida** (min/km) e a
  **CSS da natação** (min/100 m) — cada um com a descrição do que é e para
  que serve. As zonas saem daí. Também aqui: se **as atividades importadas
  contam** para a forma.
- **Geral**: sensação de declive, n.º de passos seguintes, pausa
  automática, ligação preferida e ligar ao abrir. O feedback no fim de
  cada sessão é **sempre pedido** (já não se desliga).
- **Desportos**: um separador por **Ciclismo, Remo, Corrida e Ginásio**
  (PgUp/PgDn muda; a natação não tem opções aqui — só precisa do construtor
  de treinos e das estatísticas), cada um com secções (Ctrl+←/→ muda):
  **Métricas de sessão disponíveis** (liga e desliga as que o ecrã da
  sessão pode mostrar), **Disposição do ecrã de sessão** e, no ciclismo, no
  remo e na corrida, **Sessões Não ERG** — os limites do teu aparelho
  quando é manual: **níveis do rolo**, **n.º de resistências** (remo),
  **velocidade e inclinação máximas** (passadeira). O construtor de
  treinos respeita estes limites. O ginásio não tem Sessões Não ERG.
- **Disposição do ecrã de sessão**: **Escolher as métricas do ecrã** (o editor mostra «12 de 16
  métricas» e tem os botões **− Métrica** e **+ Métrica**, ou as teclas **[** e **]** — é por aqui que
  se muda o número de métricas; a linha «Número de métricas no ecrã» já não existe) e **Disposição
  dos painéis**, que abre sempre o ecrã **do desporto em que estás** (o ginásio abre o do ginásio).
  O ecrã da sessão desenha as métricas sozinho: a grelha ajusta-se (8 → 4 × 2, 12 → 4 × 3…); no
  remo, mais de 12 passam a mais páginas (V muda); no ginásio, o ecrã tem os painéis estado,
  métricas, séries e lista, que se arrumam como os do ciclismo. Esse editor e a **Disposição dos
  painéis** só têm o separador do desporto de onde vieste.

**Atalhos de teclado** mostra todas as teclas da aplicação, por grupo (em
qualquer ecrã, **sessões de treino de todos os desportos**, ciclismo, remo, corrida e natação,
construtores, listas e calendário). **Ctrl+S** guarda em qualquer ecrã que
tenha alguma coisa para guardar. Os atalhos de volta, pausa, terminar, começar sem contagem e
saltar bloco são **um só para todos os desportos**; a resistência, a velocidade e o declive têm o
seu (ver «Teclas durante a sessão»).

**Durante uma sessão** as Definições têm só cinco separadores: **Geral** (os passos seguintes),
**Desportos** (só o desporto da sessão), **Ecrã e idioma** (tema, unidades e idioma), **Atalhos de
teclado** e **Configurações sonoras**.

**As regras de todos os ecrãs:**

- **Sem barras de deslocamento.** Quando as linhas não cabem na altura,
  continuam numa coluna ao lado, até ocupar a largura do ecrã. Só uma lista
  enorme (o inventário de exercícios da Longevidade, por exemplo) passa a
  ter páginas — o número da página aparece por baixo («1/3 ↑↓»).
- **Os botões de ação** (Guardar, Apagar, Exportar, + Novo…) ficam **todos
  em baixo, à direita** — em todos os ecrãs; o principal é o da ponta,
  realçado. **← Voltar** fica em baixo, à esquerda. ↑↓ chegam aos botões
  como a qualquer linha.
- **Pesquisa em todos os separadores**, na barra do topo (sempre no mesmo
  sítio, com uma lupa): clica na caixa ou carrega **Ctrl+F** (ou **/**) e escreve — a lista filtra-se
  enquanto escreves (sem acentos nem maiúsculas a atrapalhar). Esc limpa o
  texto; outro Esc sai da pesquisa.
- **Escolhas com lista e pesquisa.** Enter numa opção de escolha (tema,
  ligação, desporto…) abre uma **lista com pesquisa**: escreve para filtrar,
  ↑↓ e Enter escolhe. As setas ←/→ ficam para os números (e ainda passam à
  opção seguinte, para quem prefere).
- **Seletor de datas em todos os campos de data** (inventário, análises,
  sincronização, testes…): Enter abre o mês em grelha — ←/→ dia, ↑/↓
  semana, PgUp/PgDn mês, H hoje; também podes escrever a data (AAAA-MM-DD ou
  DD/MM/AAAA) ou clicar num dia.
- **Nos construtores de treinos** (de qualquer desporto), voltar atrás com
  alterações por guardar abre a pergunta **Sair sem gravar · Cancelar ·
  Guardar**: sair sem gravar volta ao menu, Cancelar (ou Esc) volta à edição,
  Guardar grava e sai.
- **Não há «arquivar».** As opções de arquivar exercícios e de desativar
  testes saíram; o que estivesse escondido assim voltou a aparecer.

### Temas

Em **Definições → Ecrã e idioma → Tema**, ←/→ mudam o tema e **o novo aspeto
vê-se logo**. Só fica com **Guardar**; **Cancelar** (ou sair sem guardar)
volta ao tema que estava. São quatro, todos sem preto:

- **Perennia** (o de origem): fundo claro, faixa do topo azul-marinho e
  ações em azul.
- **Sálvia**: claro, com verde.
- **Areia**: claro e quente, com cobre.
- **Ardósia**: cinzento-azulado médio, para salas com pouca luz.

As cores das zonas (verde-água, verde,
amarelo, laranja, vermelho, roxo) são as mesmas do intervals.icu em todos
os temas.

Por baixo fica a **sequência**: dias seguidos e semanas seguidas a treinar
(conta até hoje, ou até ontem se hoje ainda não pedalaste), os melhores de
sempre e as sessões desta semana. Conta o ciclismo e a força.

Ao lado fica a **forma**: fitness, fadiga e forma de hoje, com uma frase a
dizer em que fase estás (ver *Fitness, fadiga e forma*, abaixo).

Em todos os menus há **← Voltar** em baixo, à esquerda, para voltar atrás com
o rato. O Esc também volta.

### O ecrã da sessão

- **Em cima:** o relógio e a distância. À direita, a **resistência**
  (− / +), Pausa e Terminar. Por baixo, **6 caixas numeradas**, cada uma
  com 1 a 7 métricas e um ícone por métrica. Com até 4 métricas, o valor
  aparece em grande por baixo do nome; com mais, nome e valor ficam na
  mesma linha.
- **Ao meio, à esquerda:** as barras das **zonas de potência e de FC**. A
  barra tem as zonas todas, com as cores, e enche até ao valor atual; por
  cima aparece a zona (por exemplo "Z3 · Tempo"), o intervalo dela em
  watts e em W/kg ("188–225 W · 2.6–3.1 W/kg") e o valor atual. Num treino
  aparece também o **plano**: o passo atual (quanto falta e o alvo em W e
  % da FTP), os passos seguintes e uma barra com o progresso do passo.
- **Ao meio, à direita:** a classificação e, por baixo, as **voltas**, sempre
  visíveis. A volta em curso aparece ao vivo (tempo, distância, potência
  média, zona de potência, cadência média, FC média), seguida das últimas
  voltas fechadas. Ao carregar em **L** o painel pisca e a volta passa para
  a lista.
- **Ao centro:** a subida em curso e a fuga.
- **Em baixo:** à esquerda, o **tempo em cada zona** de potência e de FC,
  em barras que vão enchendo ao longo da sessão. Ao centro, o perfil dos
  **próximos 2 km**. Por baixo, o perfil da **rota completa** de lado a
  lado, com a **linha da potência** (amarela) e a **linha da FC** (vermelha)
  por cima da parte já feita, para veres se foste regular.

**Mudar a resistência a meio.** **+** / **−** (ou ↑ / ↓, ou os botões no
ecrã). Sem treino em ERG, muda a sensação de declive em passos de 10 % (de 0
a 150 %). Num treino em ERG, muda a intensidade do alvo em passos de 5 %:
se estás fraco, −5 % baixa todos os alvos do treino.

**Terminar pergunta primeiro.** F10 ou **■ Terminar** abrem "Terminar a
sessão?". Enquanto a pergunta está no ecrã, a sessão fica parada. **Sim**
(ou Enter) grava e vai para o resumo. **Não** (ou Esc, ou N) volta à
sessão em pausa, e a sessão continua mal voltes a pedalar.

**As métricas no ecrã.** Em **Definições → Desportos → Disposição do ecrã
de sessão** escolhes o que aparece e onde. Em **Definições → Desportos →
Métricas de sessão disponíveis** desligas as que nunca usas, e elas deixam
de aparecer no editor.

**Métricas.** Além das que já havia: **potência/peso** (W/kg, média de 3 s)
e a média, **torque** e **torque médio**, **intervalo da zona** (de potência
e de FC), **zona de potência média**, **velocidade média** e **cadência
média**.

**Zonas.** Zona de potência Z1 Recuperação a Z7 Neuromuscular, em % da FTP;
zona de FC Z1 a Z5, em % do limiar cardíaco. Sem limiar cardíaco (LTHR) nas
Definições, estima-se a partir da FC máxima ou da idade, mas defini-lo é mais
certo. **Potência E/D** dá os watts de cada perna.

A sessão **nunca termina sozinha**: pausada, continua aberta. Se chegares ao fim da rota, ela dá a
volta e continuas: cada volta completa fica marcada (aparece "Volta N
completa" com o tempo, e fica gravada na base de dados), as subidas voltam a
contar, e na classificação da rota entra a tua volta mais rápida. Se um
treino acabar, a aplicação avisa e continuas em modo livre. Só o botão de
parar termina — e o que estava feito até aí fica no `.fit`, seja a meio de
uma volta ou a meio de um treino.

### Objetivos: de cada treino e de cada bloco

Cada treino tem um **objetivo geral** escrito: o que deve treinar. Cada
bloco tem um nome (Aquecimento, Principal, Esforço, Recuperação,
Arrefecimento), um **objetivo** e o **alvo**: FTP e watts no ciclismo,
watts e ritmo /500 m no remo, ritmo e RPE na corrida e na natação, e RPE
nos blocos leves. No ginásio, cada exercício é um bloco: séries ×
repetições, carga, RPE e descanso.

- Os treinos que vêm com a aplicação têm o objetivo escrito à mão.
- Nos teus, enquanto não escreveres nada, o objetivo é sugerido pela
  estrutura do treino (por exemplo, «Resistência aeróbia: consolidar a
  base…»), e aparece a nota de que é uma sugestão.
- Escreve-se em **«Objetivos do treino e dos blocos»**, no resumo de cada
  treino. No construtor também há as linhas **Objetivo do treino** e
  **Objetivo do bloco**.

**O resumo antes de começar.** Ao escolher um treino na Lista de treinos
(ciclismo, remo, corrida, natação ou ginásio) aparece o cartão do treino,
no estilo do intervals.icu:

- o nome do treino, a duração e a carga;
- a intensidade em palavras e o esforço percebido previsto;
- o objetivo;
- o gráfico dos blocos: a altura é a intensidade, a largura é o tempo, a
  cor é a zona, e a linha tracejada marca o limiar;
- a lista dos blocos, com as repetições agrupadas («5 × Esforço»), o
  objetivo e o alvo de cada um.

Daí carregas em **Configurar sessão de treino** (em baixo à direita, ou
Enter), que abre a janela da sessão.

**Durante a sessão** aparecem o objetivo e o alvo do bloco em curso:

- **Ciclismo:** no aviso de cada bloco novo e, se houver espaço, por baixo
  do título do plano.
- **Remo, corrida e natação:** na zona do passo.
- **Ginásio:** como «Objetivo:», por baixo das séries.

### Análise de uma sessão (todos os desportos)

No **Histórico** de cada desporto (e no calendário), escolher uma sessão
abre a análise em quatro separadores (Tab muda):

1. **Geral** — o **tipo de sessão** (sessão livre e a rota, treino e o tipo
   do treino — por exemplo «Treino: Sweet spot 3×12 · Potência · ERG» —,
   teste, Challenge), a data, os números da sessão, as voltas e o `.fit`.
2. **Feedback** — o ecrã do feedback ali mesmo (ver abaixo): RPE, dores,
   sensação, objetivo cumprido e comentário. Sair com alterações por guardar
   pergunta.
3. **Análise do treino** — num treino por blocos, uma linha por bloco: o
   alvo, o feito (média), a FC, o tempo dentro do alvo e o resultado
   (**✓ cumprido** com 75 % do tempo no alvo, **~ em parte**, **✗ não
   cumprido**, **✗ não acabado** ou **— não feito**). A margem é a do bloco
   (alvo exato ou ± %); nos blocos leves (aquecimento, descanso, retorno à
   calma) há mais folga. Os blocos seguem as voltas de cada bloco (assim os
   blocos por distância também batem certo). No ginásio: séries,
   repetições, volume e cumprimento de cada exercício, com **Análise
   detalhada** (em baixo, à direita). Numa sessão livre não há blocos para
   comparar.
4. **Infográficos** — **Gráfico com os blocos**: as linhas da sessão
   (potência, FC, cadência; velocidade na corrida; voga no remo), cada uma a
   ligar e desligar com ←/→, e por baixo os **blocos do treino** com as
   cores das zonas e a linha do **alvo**. No ciclismo também **Relatório**,
   **Curva de potência**, **Zonas** e **Picos** (**[** e **]**, ou um clique,
   mudam de vista).

### Feedback no fim de cada sessão

**A avaliação do treino é agora do Treinador** (ver «O Treinador», mais abaixo): o painel da
direita chama-se **Treinador** e começa pela leitura dele — a forma com que entraste na sessão,
se foi um dia pesado para a tua carga habitual, o que acrescentou à longevidade e **o que fazer a
seguir** (descansar, baixar ou subir alvos, repetir, seguir o plano, e o próximo treino do
calendário). Por baixo continua a análise que já existia (execução, objetivo, sensações).

Quando uma sessão termina, por cima do resumo aparece **«Como correu esta
sessão?»**:

- À esquerda, **«Prescrito e realizado»**: os blocos do treino (a cor é a
  zona), com a potência (ou o ritmo) e a FC por cima. A FC usa o eixo da
  direita.
- À direita, as perguntas. Tudo é opcional:
  - **Esforço percebido (RPE)**, de 1 a 10;
  - **Dores**, de 0 a 10;
  - **Sensação geral**, de Péssima a Ótima;
  - **O objetivo foi cumprido?**: Sim, Em parte ou Não;
  - **Comentário**, em texto livre.
- **↑↓** muda de pergunta e **←/→** muda o valor. Nas linhas do RPE e das
  dores podes escrever o número, e **Backspace** limpa a resposta. Guardas
  com **Ctrl+S** ou com **Guardar e analisar**. **Agora não** (Esc) fecha
  sem guardar.

**A análise** é feita no computador, sem rede nem IA, e muda enquanto
respondes. Cruza o objetivo do treino com o que disseste:

- **Sessão:** duração, potência ou ritmo (e % da FTP), FC e carga.
- **Execução:** a percentagem do tempo dentro do alvo de cada bloco e a
  parte da duração prevista que fizeste.
- **Objetivo:** o objetivo do treino comparado com o RPE previsto e o que
  sentiste, com a tua resposta ao «objetivo cumprido?» e com a execução.
  Daí sai se a sessão foi **proveitosa**: sim, em parte ou não, e porquê.
- **Sensações:** as dores (com o cuidado que pedem) e o teu comentário.

Em cima fica a frase-resumo, num chip verde, amarelo ou vermelho. Por
exemplo: «Proveitosa · Sessão de recuperação cumprida dentro do
prescrito».

Tudo fica guardado para o futuro agente treinador. O feedback pode ser
dado ou corrigido mais tarde, na primeira linha do resumo ou do detalhe da
sessão, no Histórico. É sempre pedido.

### Ecrã da sessão, por desporto (arrastar as métricas)

Em **Definições → Desportos → Disposição do ecrã de sessão**, escolhe o
desporto. Aparece uma miniatura do ecrã da sessão e, por baixo, todas as
métricas que esse desporto conhece. As que já estão no ecrã aparecem
realçadas. O tempo total fica sempre ao centro, em cima.

| Desporto | O que se arruma |
|---|---|
| Ciclismo | as 6 caixas do HUD, com 1 a 7 métricas cada |
| Remo | 2 páginas de 12 quadrados (separadores Página 1 e Página 2) |
| Corrida, Natação | 8 quadrados |
| Ginásio | 4 quadrados no painel da sessão (FC, zona, séries, volume, tempo…) |

**Com o rato:**

- arrasta uma métrica da paleta para um lugar;
- arrasta um lugar para outro para trocar. No ciclismo, isto muda a métrica
  de caixa ou de ordem;
- no ciclismo, arrasta o título de uma caixa para outra para trocar as
  caixas inteiras.

**Com o teclado:**

- as setas escolhem o lugar;
- **Enter** abre a lista das métricas;
- **,** e **.** trocam pela métrica anterior ou seguinte;
- **Del** esvazia o lugar;
- **R** duas vezes repõe o ecrã de origem.

Fica com **Guardar** (em baixo, à direita); **Cancelar** volta ao gravado.

### Disposição do ecrã da sessão (arrastar painéis)

Em **Definições → Desportos → Disposição do ecrã de sessão** (ou no botão
**Disposição do ecrã**, em cima à direita, no editor das métricas) decides
**onde fica cada painel** — um separador por desporto (ciclismo, remo,
corrida, natação). Em cima está o ecrã da sessão em ponto pequeno, numa
grelha de 24 × 16; o tempo total e os botões ficam sempre em cima.

| Desporto | Painéis |
|---|---|
| Ciclismo | caixas de métricas, zonas de potência e FC, plano do treino, classificação, voltas, tempo em cada zona, perfil dos próximos 2 km, rota completa |
| Remo | quadrados de métricas, estado e plano, voltas, classificação, gráfico ao vivo (potência e voga), tempo em cada zona de FC |
| Corrida, Natação | quadrados de métricas, estado e plano, voltas, gráfico ao vivo (FC e velocidade), tempo em cada zona de FC |

- **Arrasta** um painel para o mudar de sítio; o **canto de baixo, à
  direita**, muda o tamanho. Um painel não pode pisar outro.
- Os painéis que não estão no ecrã ficam por baixo: **arrasta** um para o
  sítio que queres, ou **clica** nele (fica no primeiro lugar livre; com o
  ecrã cheio, fica com a parte de baixo do maior painel).
- Teclado: **,** e **.** escolhem o painel, as **setas** movem-no,
  **Shift+setas** mudam o tamanho, **Del** tira-o do ecrã, **Enter** põe o
  primeiro dos que estão fora.
- **Guardar** grava; **Cancelar** volta ao gravado; **Repor a de origem**.

No remo sem jogo não há classificação: as voltas ocupam também o lugar dela
(se estiver logo por baixo). No ciclismo, a placa das subidas, a fuga e os
avisos ficam sempre ao centro.

### Calendário

O calendário **está no ecrã inicial**, por baixo dos cartões (já não há um
menu à parte). Mostra o mês, de segunda a domingo, com as sessões feitas e
os treinos planeados de cada dia.

Teclas: ↓ a partir dos cartões entra no calendário; ←/→ dia, ↑/↓ semana,
**PgUp/PgDn** mês, **T** hoje, **D** (ou o botão por cima do calendário) abre o **seletor de
datas** para saltares para qualquer mês ou dia, **Enter** abre o dia; ↑ na primeira semana
volta aos cartões. Com o rato, as setas ‹ › do título mudam de mês e um clique num dia abre-o.

**Ao abrir um dia** (uma janela) vês o que fizeste, com o feedback, e o que estava
planeado. Em baixo, a **nota do dia** (o texto aparece na própria janela) e os botões:

- **Nota do dia** (ou **N**): um texto livre (como te sentiste, o tempo, a viagem…);
- **Diário de saúde**: vai para a Saúde, nesse dia (sono, HRV, peso…);
- O terceiro botão **depende do dia**:
  - **Hoje ou um dia futuro → «+ Planear treino»**: 1.º o **desporto**, 2.º **de onde vem o
    treino**: *importar um treino da lista* (com pesquisa), *importar um treino do computador*
    (.zwo, .fit, .mrc, .erg… — pergunta se fica na lista) ou *criar um treino no construtor*
    (fica na lista e já planeado nesse dia).
  - **Um dia que já passou → «Carregar treino»**: **não se planeia** um dia passado (nem o
    seletor de datas do botão Planear deixa escolhê-lo); vês as sessões feitas, o diário e, se
    o treino foi feito **noutro sítio**, carregas o ficheiro: *carregar um ficheiro de treino
    (.fit, .tcx)* (o Upload manual), *sincronizar a HRV* (HRV4Training), *sincronizar dados de
    saúde (.csv)* ou *sincronizar o GarminDB* — abrem o menu Backups e Sincronização no
    separador certo.

A ficha de qualquer treino (ciclismo, remo, corrida, natação e ginásio) tem também o botão
**Planear**: escolhes o dia no seletor de datas (só de hoje para a frente) e o treino entra no
calendário (sem duplicar).

Enter num treino planeado abre o resumo, para começares; **Del** tira-o do
plano. Um treino planeado fica **✓ feito** quando nesse dia há uma sessão
desse treino.

### Métricas de sessão e métricas de evolução

A Perennia separa dois tipos de métricas:

- **Métricas de sessão** — as que vês **durante** um treino (potência, FC,
  ritmo, cadência…). Escolhem-se em **Definições → Desportos → Métricas de
  sessão disponíveis**.
- **Métricas de evolução** — as que mostram **como estás a mudar** ao
  longo das semanas. Estão em **Estatísticas gerais → Métricas de
  evolução** (e em Corrida → Estatísticas → Métricas de evolução da
  corrida), em três separadores:

**Forma e fadiga** — o fitness (CTL), a fadiga (ATL), a forma (TSB) e o
ramp de 7 dias de hoje, todos os desportos juntos, e o gráfico.

**Corrida** (precisa de corridas com FC):

- **Fator de eficiência (EF)**: velocidade normalizada (m/min) ÷ FC média.
  Mais alto é melhor: corres mais depressa com o mesmo coração.
- **Desacoplamento ritmo:FC**: quanto a EF da 2.ª metade cai face à 1.ª,
  na última corrida longa. Abaixo de 5 % = base aeróbia sólida.
- **Durabilidade**: quanto a EF cai no último quarto dos treinos de 75 min
  ou mais.
- **Avisos de progressão da carga**: uma corrida mais de 10 % mais longa do
  que a mais longa dos 30 dias anteriores; o volume semanal a subir mais de
  10 % face à semana anterior.
- **Previsões de prova** (5 km, 10 km, meia, maratona) pela fórmula de
  **Riegel** a partir da melhor corrida (≥ 3 km) dos últimos 90 dias, e a
  maratona também pela fórmula de **Tanda**, que conta com o volume semanal
  das últimas 8 semanas (Riegel costuma ser otimista na maratona).
- **Zonas de ritmo** por três métodos: **80/20** (Fitzgerald), **Friel**
  (a partir do teu ritmo de limiar) e **Daniels** (a partir do VDOT da
  melhor corrida recente).

**Prontidão** — a HRV (média de 7 dias face ao normal de 60 dias, ± 0,5
desvio, como o HRV4Training), a FC em repouso (5 bpm acima da linha de base
é um sinal) e o sono (1 h abaixo do costume é um sinal): sem sinais,
**Pronto**; um, **Atenção**; dois ou mais, **Descansa**.

### Carga e prontidão

Em **Estatísticas gerais → Carga e prontidão**, todos os desportos juntos,
como no intervals.icu. Há três gráficos:

1. **Fitness e fadiga**, com a carga de cada dia em barras.
2. **Forma** (fitness − fadiga), com as faixas: fresco, neutro, ótimo e
   risco.
3. **Prontidão** dos teus check-ins (os pontos de recuperação do
   HRV4Training, na Saúde), com o **ramp**: quanto o fitness subiu numa
   semana.

Em cima ficam os números de hoje. ←/→ muda o período: 30, 60, 90, 180 ou
365 dias.

### Botões com ícone

**Todo o botão** — nos menus, nas janelas e nos diálogos — leva um **ícone ao lado da etiqueta**,
e **o mesmo ícone para a mesma ação**: **+** para acrescentar (o «+» da etiqueta é desenhado
pelo ícone), disquete para Guardar, caixote para Apagar / Remover / Terminar sem guardar, **×**
para Cancelar / Fechar, lápis para Editar, calendário para Planear, um ícone próprio para
Exportar e outro para Importar, ▶ para Começar / Retomar, ⏸ para Pausa, ■ para Terminar, ✓ para
Sim / OK / Aplicar e ← para Voltar. (Os ícones vêm de `perennia/assets/icons`, gerados por
`tools/make_icons.py`, e a regra de qual vai com cada etiqueta está em `perennia/gfx/icons.py`.)

### Os menus de cada desporto

Por baixo do título, o menu de cada desporto diz sempre **o nome do atleta, a FTP e a LTHR**
(`Daniel · FTP 250 W · LTHR 165 bpm`); o **Ginásio** não mostra nada.

Ciclismo, Remo, Corrida, Natação e Ginásio têm o mesmo menu, com quatro
separadores em cima: **Treinar**, **Lista de treinos**, **Histórico** e
**Estatísticas**. (O separador «Construtor de treinos» deixou de existir: o
construtor abre-se com **+ Novo treino**, em baixo na lista, e com **Editar**
na ficha de um treino.) O separador **Treinar** começa
sempre pela mesma ordem: **Sessão de treino** · **Desafios**
(a natação: **Desafios** · **Testes**):

- **Sessão de treino**: no ciclismo, no remo e na corrida abre **uma
  janela só**, grande, com os modos — **Livre**, **Carregar treino**,
  **Do computador**, **Challenge** e **Testes** — e depois a preparação
  (aparelhos, rota `.gpx` — não no remo —, opções e auto lap); na corrida
  com rota, a sessão diz a inclinação da estrada a pôr na passadeira. No
  ginásio, a mesma janela mostra as modalidades, o Challenge e os Testes.
  A natação não tem sessão de treino.
- **Challenge** e **Testes** já não estão na lista do separador Treinar:
  estão nesta janela (a natação, que não tem sessão, fica só com os
  **Desafios** e os **Testes**, sem Challenge).
- **Challenge**: ciclismo — fuga, desafio adaptativo e os jogos; remo — a
  Regata e os jogos; corrida — 5 km e 10 km contra o relógio, 1 hora o mais
  longe possível, escada de ritmo; natação — 400 m e 1500 m contra o relógio,
  30 min o mais longe possível, pirâmide; ginásio — treino surpresa de cada
  modalidade, EMOM 20 min, Tabata × 3 e pirâmides de passadeira e de remo.
  Cada prova da corrida e da natação guarda a tua tabela de melhores.
- **Desafios**: objetivos acumulados do desporto (ver «Desafios com
  objetivo à tua escolha»). Tab e Shift+Tab mudam de separador; o rato
também. Antes de cada treino aparece um ecrã de arranque, com a volta
automática e, na natação, o comprimento da piscina; na corrida, a velocidade
inicial.

### Construtor de treinos (arrastar blocos)

O construtor desenha o treino como um gráfico: cada bloco é uma barra, a
largura é a duração e a altura é o esforço. É **igual no ciclismo, no remo,
na corrida e na natação** (o ginásio tem o seu): a **Lista de treinos** mostra
os treinos da mesma maneira (duração, definição e tipo, descrição) e tem
**+ Novo treino** em baixo, à direita (Del apaga o escolhido). Enter num treino abre a
**ficha**, com letra maior e três ações: **Editar** (abre o construtor),
**Exportar** e **Configurar sessão de treino**. Os objetivos que a ficha mostra
**são os do próprio treino** — mudam-se no construtor, ao editar o treino (já não há
«Editar objetivos» nem objetivos «misturados»).

- **Em cima**, o **Tipo de treino** (uma lista: recuperação, resistência
  aeróbia, tempo, limiar, VO2máx, anaeróbio, trabalho, aquecimento de prova,
  prova, teste, técnica, força, mobilidade — ←/→ ou Enter; «Automático» sugere-o
  pelo esforço dos blocos), por baixo o **Nome do treino** e o **Objetivo do
  treino** (os três começam no mesmo sítio, à esquerda). O tipo também **etiqueta
  o .fit** (ver «Etiquetas e tipo de sessão»). No subtítulo, o que o treino
  **acrescentaria ao índice de longevidade** (muda ao mexer nos blocos). O objetivo — do
  treino e de cada bloco — escreve-se **numa janela** (Enter na linha, ou
  começa a escrever): Enter guarda, Esc cancela. Por baixo, a paleta e o
  gráfico; **por baixo do gráfico**, o bloco escolhido, com a descrição de
  cada opção à frente dela.
- **No meio de cada bloco**, em letra grande: a zona, o valor na vista
  escolhida (W, bpm, RPE, ritmo ou nível; numa **rampa, a média**), a
  duração e a **cadência alvo**. Num bloco estreito fica só o que cabe; num
  bloco baixo, por cima dele.

- **O bloco escolhido**, por baixo do gráfico, tem o título **«Bloco X de
  N»** e por baixo o **Tipo** (aquecimento, trabalho, descanso, retorno à
  calma). A lista fica sempre no mesmo sítio, numa coluna, seja qual for o
  bloco. Para apagar o bloco carrega em **Del** (está no rodapé; já não há
  a linha «Apagar bloco»), que pergunta numa janela; **Guardar** mostra
  «Treino guardado».
- **Os limites do teu aparelho** (Definições → Desportos → Sessões Não ERG)
  valem no construtor: o nível do rolo não passa do número de níveis, a
  resistência do remo do número de resistências, e a velocidade e a
  inclinação da passadeira dos máximos que puseste.
- **ERG ou Manual.** «+ Novo treino» pergunta primeiro o
  tipo, no ciclismo, no remo e na corrida (a natação é sempre manual):
  - **ERG** — o aparelho segue o treino sozinho (o rolo põe os watts, a
    máquina de remo muda a resistência). Precisa de um aparelho ligado que
    aceite comandos. No ciclismo é por **zonas de potência**.
  - **Manual** — a sessão mostra o que o treino pede e és tu que o pões no
    aparelho, ou o segues pela FC/RPE. No ciclismo: **FC**, **RPE** ou
    **Níveis do rolo** (primeiro defines em **Definições → Desportos →
    Ciclismo → Sessões Não ERG** quantos níveis tem o teu rolo). Na corrida: o
    ritmo, e por bloco a **velocidade** e a **inclinação** da passadeira. No
    remo: potência, ritmo, FC ou RPE, com a **resistência** e a **voga**.
  As listas de treinos mostram a definição e o tipo («Potência · ERG»).
- **A vista** muda com Tab, entre as do tipo do treino. O treino é guardado
  em % do limiar, por isso trocar de vista não o altera; só muda a forma de o
  ler. Os números (W, bpm, RPE, min/km, min/100 m, nível) saem das tuas
  Definições. A paleta, em cima, tem a cor, o nome e o intervalo de cada zona
  na vista escolhida.
- **Cada bloco** tem a **cadência alvo** (ciclismo) e o **alvo**: exato ou
  com margem (± 1 a 15 %, ←/→).
- **Com o rato:**
  - arrasta um bloco da paleta (Z1–Z6, Descanso, Rampa e, no fim, **Free
    ride** — sem alvo; no ciclismo o ERG fica desligado nesse bloco) para o
    gráfico; uma linha mostra onde vai entrar;
  - um clique na paleta põe o bloco a seguir ao selecionado;
  - arrastar a aresta direita muda a duração;
  - arrastar a aresta de cima muda a intensidade (numa rampa, cada lado é
    arrastado à parte);
  - arrastar o meio muda o bloco de lugar.
- **Com o teclado:** ←/→ escolhem o bloco, +/− mudam a duração, D duplica,
  Del apaga e Ctrl+S (ou o botão **Guardar**, em baixo à direita) guarda. Se
  voltares atrás com alterações por guardar, aparece **Sair sem gravar ·
  Cancelar · Guardar**.
- Por baixo do título aparecem a duração, a carga (TSS) e o IF estimados; a
  barra fina por baixo do gráfico é o tempo em cada zona, com as cores dos
  blocos. As mesmas cores identificam as zonas em todos os gráficos.

No ciclismo, o editor antigo, passo a passo, continua no separador do
construtor (tecla P), com a exportação para `.zwo`/`.mrc`/`.erg` (tecla E).

### Remo: mais métricas

O ecrã da sessão de remo tem agora **duas páginas de 12 quadrados**; a tecla
**V** muda de página. Há 34 métricas por onde escolher:

- ritmo atual, médio e melhor, e os últimos 500 m;
- voga e voga média;
- potência, média, máxima, % da FTP e W/kg;
- energia por remada e metros por remada;
- FC, FC média, FC máxima e zona;
- kcal e kcal/h, e carga (TSS);
- volta atual: tempo, distância, ritmo, e o ritmo da volta anterior;
- no treino estruturado, o alvo do passo e a diferença para ele;
- projeção dos 2 km e tempo final previsto.

Escolhe-as em **Remo → Treinar → Campos do ecrã de remo**, uma página por
separador.

### Corrida e natação

Ainda não há sensores de passadeira nem de piscina: os dados entram à mão.
O relógio só começa quando carregas em **Espaço**.

- **Corrida livre (passadeira):** ao meio do ecrã há dois cartões, **Velocidade** e **Inclinação**,
  cada um com os seus − e +. A velocidade muda de **0,1 em 0,1 km/h** (teclas **+** e **−**; com
  Shift de 0,5 em 0,5) e a inclinação de **0,5 em 0,5 %** (teclas **↑** e **↓**; é o «passo da
  inclinação» de Definições → Desportos → Corrida → Sessões Não ERG, e nunca passa da inclinação
  máxima). **Tudo o que escolheres fica registado ao segundo**: na análise do treino (Estatísticas →
  a sessão → Análise) aparece a linha **Inclinação (%)** junto à velocidade e à FC, e o `.fit` leva
  a inclinação (campo *grade*) em cada registo. Num treino por blocos, a passadeira segue o treino
  e os cartões não aparecem. Com **T** escreves a distância total que a passadeira mostra, e a
  aplicação acerta a distância por ela.
- **Sem contador no topo** (corrida e remo): o tempo total da sessão e o tempo da volta são
  **métricas** como as outras — **Tempo total** e **Tempo da volta** — e escolhem-se em
  *Escolher as métricas do ecrã*. O ecrã também já não repete o desporto por baixo do título
  nem a meio do ecrã, e o painel das **voltas** (à direita) tem letra maior.
- **Natação:** + conta um comprimento de piscina, − desfaz o último.
- **As duas:** L marca uma volta e P pausa. Esc pergunta se queres
  terminar, com a opção de terminar sem guardar.

Cada sessão grava um `.fit` (corrida em passadeira ou natação em piscina),
fica no histórico e entra nas estatísticas e na carga. Há treinos já feitos
(corrida fácil, intervalos 6 × 800 m, limiar, rodagem longa; na natação,
técnica e séries de CSS) e os testes de natação de 400 m, 200 m, 100 m e
30 minutos ficam em Saúde → Testes de aptidão e podes fazer os teus no construtor.

### Ginásio e as modalidades

O antigo menu **Força** passou a ser **Ginásio**, com as modalidades:

- Força
- Pliométricos
- Animal Flow
- Cardio
- HIIT
- Calisténicos
- Argolas de ginástica
- Elásticos
- Kettlebell
- Sandbag
- Mobilidade, Tendões e Isométrico
- Conditioning (voltas: passadeira, remo, bicicleta, exercícios)

(A modalidade **Longevidade** deixou de existir: o índice tem o seu menu. Os teus treinos e
sessões dessa modalidade passam sozinhos para a Força e o treino de origem passou a chamar-se
«Força e equilíbrio». O «Novo treino de ginásio» já não tem a Longevidade.)

Cada modalidade tem:

- **Treino livre.** Primeiro montas o plano (exercícios, séries,
  repetições, carga, descanso). Só depois carregas em **▶ Começar o
  treino**, e o tempo só conta a partir da primeira série. No fim do plano
  há **Guardar como treino da modalidade**, para o repetires mais tarde.
- **Treino surpresa.** A aplicação monta um treino com os exercícios da
  modalidade. Se já preencheste o inventário de artigos, usa só o
  equipamento que tens. Outro sorteio dá outro treino.
- **Os teus treinos** e o **histórico** da modalidade.

**«Sessão de treino» no Ginásio é uma janela só** (não há páginas): escolhes a **modalidade** e
a janela passa às opções dessa modalidade — **Treino livre**, **Treino surpresa**, **Carregar
treino** (a lista dessa modalidade), **Treino livre por blocos**, **Do computador**,
**Challenge** e **Testes**. Esc volta atrás (da lista ou das opções para as modalidades, e daí
fecha). **Do computador** lê um `.csv`, `.json`, `.txt` ou `.fit` (por exemplo, um treino de
força criado no TrainingPeaks) e pergunta se fica na lista; a **Lista de treinos** tem o mesmo
«Do computador». Num treino, **Configurar sessão de treino** abre uma janela só com os
**aparelhos** (a banda de FC) e o **auto lap**, que aparece **bloqueado** porque o ginásio faz
auto lap a cada bloco do treino.

**A sessão de força** tem os mesmos botões das outras, **em cima, à direita**:
**Lap**, **+ Série**, **Saltar**, **Pausa** e o **Terminar a vermelho** (como no ciclismo; em janelas
estreitas descem para a barra de baixo), o mesmo aviso **PAUSA** e o mesmo diálogo de terminar (Esc
pausa, F10 pergunta; Sim · Não · Terminar sem guardar) e as etiquetas do `.fit`. **Já não há
cronómetro no topo** nem campos de **RPE**: a sessão não os pede (o RPE da sessão inteira continua
no feedback do fim).

- **Começa sozinha**, como as outras sessões: passada a contagem de **15 s** (Definições) arranca
  logo o 1.º exercício — **já não há «Começar série 1»**. O botão é só o **Lap** (também Espaço e
  Enter): fecha a série (ou o exercício) e passa ao descanso; do descanso, passa à série seguinte.
- **O treino está numa lista, num só ecrã**: uma linha por exercício com o **alvo**, as
  **repetições e a carga à frente** (colunas «Repetições» e «Carga»: o que o plano pede, ou o que
  fizeste) e as séries feitas (`2/4`); **seguido do seu descanso** (assim o treino está todo
  descrito e é só segui-lo). ▶ é o exercício (ou o descanso, com a contagem) em curso, ✓ os feitos,
  – os saltados. **O descanso é a única linha por baixo de cada exercício** (já não há linhas à parte
  para as repetições, a carga e o RPE) e leva o **tempo na coluna das repetições** (`1:30`; no que
  está a decorrer conta para trás e passa a `+0:05` a vermelho se ultrapassares).
  As **repetições** (ou os segundos) do exercício em curso mudam-se **na própria linha dele**: ←/→
  ajustam, escrever um número substitui; a **carga** muda com **[** e **]**. **Enter num exercício**
  vai para ele e começa a série (a meio de uma série avisa).
- **Séries por tempo (a prancha de 40 s)**: o tempo da série **conta para trás**, como o descanso, com
  os mesmos bips nos últimos segundos; quando chega a zero a série **termina sozinha** e passa ao
  descanso (e daí ao exercício seguinte). O botão **Lap** termina-a antes, se quiseres.
- **A contagem decrescente** (da série por tempo e do descanso) aparece na métrica **Série /
  descanso**. Se essa métrica **não estiver no ecrã** (Definições → Desportos → Ginásio → Disposição),
  abre-se um **aviso ao centro** com a descrição — **DESCANSO** (e o exercício que vem a seguir) ou o
  nome do exercício e «Série 2 de 4» — e o número grande. Some-se quando pausas ou terminas.
- **Saltar** salta o exercício, mesmo **a meio de uma série** (a série não fica gravada); **N** salta o
  **bloco** inteiro (um superset, um circuito). No descanso, passa ao exercício seguinte.
- **Treino concluído**: quando a **última série acaba**, o tempo **pára de imediato** e abre-se
  sozinho o diálogo de terminar (como se tivesses carregado em «Terminar»). O mesmo nos treinos
  **por blocos** de ciclismo, corrida e remo: ao acabar o último bloco, o tempo pára e abre-se a
  janela de guardar ou não, com as possibilidades de sempre (Sim · Não · Terminar sem guardar).
  Se escolheres «Não», continuas a pedalar/correr/remar ou a fazer séries à vontade.
- **O botão «Começar treino»** (nos editores de treino livre, de treino surpresa «Ajustar antes de
  começar» e de plano de voltas do Conditioning) está **em baixo, à direita**; já não é uma linha do
  menu.

**Treino livre (Ginásio)** — «quero começar já com estes exercícios». Em **Sessão de treino →
modalidade → Treino livre** só **escolhes os exercícios** (**+ Adicionar exercício**; Del tira;
←/→ muda a ordem): **não há séries, repetições, carga nem RPE** marcados de antemão. Depois
**Começar treino** (também **Guardar como treino da modalidade**, que aí já leva o habitual 3 × 10).
Na sessão és tu que marcas as voltas: fazes o exercício, carregas **Lap** (Espaço ou outro botão):
o exercício acaba (**guarda-se só o tempo que levou**), começa o **descanso** (a contar para cima) e
**abre logo uma janela** — «Quantas repetições?» (e a carga, se quiseres). Escreves o número, **Enter**
fecha a janela e o descanso continua; outro **Lap** passa ao exercício seguinte. Os botões Pausa,
**+ Série** (repetir o exercício), Saltar e Terminar mantêm-se; o treino livre **não termina sozinho**.
**Mais tarde** — na análise da sessão (separador *Análise do treino* → **Editar séries**) — podes
acrescentar ou corrigir as repetições, a carga e o RPE que ficaram em falta: **só nas sessões de
treino livre**; as séries dos treinos planeados não se editam depois.

No **Conditioning**, o treino livre também começa pelo plano: escolhes as
voltas (força, passadeira, remo, cardio, descanso), por tempo ou à vontade, e só
depois arrancas. As voltas com tempo passam à seguinte sozinhas; as outras
passam com L ou com **▶ Volta do plano**.

**Para acrescentar uma modalidade nova**, basta um bloco
`register(Modality(...), [exercícios])` no ficheiro `perennia/core/gym.py`.
Aparece sozinha no menu, com surpresa, treinos, histórico e inventário de
exercícios.

### Construtor de treinos de força (por blocos)

No **Ginásio**, cada modalidade (Força e as outras, menos o Conditioning)
tem **+ Criar treino (construtor por blocos)**. A tecla **E** num treino
abre-o aqui, e no resumo do treino há **Editar no construtor por blocos**.
O construtor segue o «Strength Workout Builder» do TrainingPeaks.

**O cartão do treino**, em cima:

- o nome (clica e escreve);
- **Início** (hora de início);
- **Planear** (um dia dos próximos 14, que vai para o calendário ao
  guardar);
- **Guardar**, que mostra «Guardado ✓»;
- **▶ Começar**, que grava e começa a sessão.

**À esquerda, o resumo do treino** escreve-se à medida que prescreves:

- os blocos (A · Exercício único, B · Superset…);
- cada exercício com o rótulo (A, B1, B2…) e a prescrição. Por exemplo,
  «5/5/3 reps @ 100/105/110 kg · 120 s» ou «3 × 8 @ 60 kg»;
- as séries, a duração e o volume previstos;
- em baixo, as **Instruções do treino**.

**Ao centro, os blocos.** Cada bloco é um cartão com:

- a pega **⋮⋮** à esquerda, para arrastar;
- o **⋮** em cima à direita, com estas opções:
  - adicionar um exercício ao bloco;
  - converter em superset, circuito, aquecimento, retorno à calma ou
    exercício único;
  - mover para cima ou para baixo, duplicar ou remover o bloco.

Dentro do bloco, cada exercício tem:

- o rótulo, o nome, **Ver histórico** e o seu próprio **⋮**:
  - adicionar um parâmetro;
  - pré-visualizar o exercício;
  - escrever as notas do treinador;
  - desligar do bloco;
  - substituir ou remover o exercício;
- uma tabela com uma coluna por **parâmetro** (o **▾** de cada coluna
  muda-o, copia a série 1 para as outras ou tira-o) e uma linha por
  **série**. O «–» cinzento é uma célula por preencher; **× tira a série** e
  **+ Série** junta outra igual à de cima.

**Os parâmetros** são:

- repetições, carga (kg), **% da 1RM**, **RPE**, **RIR**, tempo,
  distância e descanso;
- RPE e RIR dizem o mesmo (RPE 8 ≈ 2 repetições em reserva), por isso só
  aparece um de cada vez; ao trocar de um para o outro, o valor é
  convertido;
- com **% da 1RM**, a carga sai da tua 1RM estimada (das últimas sessões
  desse exercício).

**Os tipos de bloco** são estes:

- **Exercício único:** as séries uma a seguir à outra.
- **Superset:** as séries alternam entre os exercícios (B1, B2, B1, B2…).
  O descanso do bloco vem no fim de cada volta. Na sessão podes mudar a
  ordem.
- **Circuito:** dá-se a volta a todos os exercícios, tantas vezes quantas
  as **voltas** (escreves o número na linha do bloco). O circuito faz-se
  inteiro.
- **Aquecimento** e **Retorno à calma:** funcionam como um superset, no
  início ou no fim.

**Arrastar com a pega:**

- para cima ou para baixo muda a ordem (aparece uma linha onde vai
  ficar);
- largar no meio de outro bloco **junta-os num superset** (o bloco fica
  contornado).

**Exercícios novos:** em **+ Adicionar bloco**, o inventário de exercícios
tem **+ Novo exercício**: nome, grupo muscular, medida (repetições ou
tempo), material e instruções. As instruções aparecem em **Pré-visualizar
o exercício**.

**Teclado:**

- as setas mudam a seleção;
- escrever números preenche a célula (escrever substitui o que lá está);
- **Backspace** apaga;
- **Enter** abre o que está escolhido, ou desce para a série seguinte;
- **M** abre o ⋮;
- **Alt+↑/↓** muda o bloco de sítio;
- **Ctrl+S** grava (ou o botão **Guardar**, em baixo à direita);
- **Esc** com alterações por guardar pergunta **Sair sem gravar · Cancelar ·
  Guardar**;
- a roda do rato desloca a lista.

**A sessão segue a estrutura:**

- a ordem das séries, alternada nos supersets e por voltas nos circuitos;
- o alvo de cada série (por exemplo, pirâmides com cargas diferentes);
- o descanso de cada série ou do bloco;
- o rótulo (B1 · Supino) no título.

O **Treino livre por blocos** monta-se no construtor e começa-se logo;
guardá-lo é opcional. O treino livre e o editor simples (lista) de antes
continuam lá.

### Análise pós-treino (força)

Abre-se ao tocar numa sessão no **Histórico** do Ginásio ou da modalidade,
na sessão de força no **Calendário**, ou na linha **Análise pós-treino** do
resumo do fim da sessão.

- **Em cima:** cumprimento (feito ÷ prescrito, a cores), volume feito e
  prescrito, séries, repetições, RPE médio, tempo em série e FC média.
- **À esquerda, um exercício por linha:** séries, repetições, carga máxima,
  volume, **1RM estimada** (com a diferença para a vez anterior) e o
  cumprimento:
  - verde: entre 80 e 120 % do prescrito;
  - amarelo: um pouco fora;
  - vermelho: muito fora.
- **À direita, o exercício escolhido:** cada série com o prescrito ao lado
  do feito (a verde se cumpriu, a amarelo se ficou aquém), o RPE, quanto
  durou e a FC, e um gráfico da carga prescrita e feita por série.

Teclas: ↑↓ escolhem o exercício, **Enter** abre o histórico dele, **F** o
feedback e **S** a lista das séries.

### Estatísticas por exercício (Ginásio)

Em **Ginásio → Estatísticas → Estatísticas por exercício**. Também se chega
por **Ver histórico** (no construtor e na análise) e por **Estatísticas do
ginásio → Por exercício**.

- **Separadores** (as métricas): carga máxima, carga média, 1RM estimada,
  volume, RPE médio, **tempo no exercício** (do início da 1.ª série ao fim
  da última) e repetições.
- **O exercício** muda-se com ←/→; Enter escolhe-o numa lista.
- **Em cima** ficam a última sessão, a melhor e a tendência: a diferença
  entre as primeiras e as últimas sessões, em %.
- **Por baixo**, uma tabela com as últimas sessões: séries (reps × kg),
  carga máxima, 1RM estimada, RPE e tempo.
- Um clique num ponto do gráfico mostra a sessão; outro clique (ou Enter)
  abre a análise pós-treino dela. Um clique numa linha da tabela também a
  abre.

### Inventário de artigos e de exercícios

**Inventário de artigos** (no ecrã inicial) é o teu
equipamento, arrumado em separadores por tipo: máquinas, pesos livres,
estações, peso do corpo, eletrónica e outros. Cada artigo tem
quantidade, peso, uma nota, a **data de compra** (com o seletor de datas) e
o **preço de compra**. O separador **Lista completa de artigos** mostra
todos juntos, com o **valor gasto** (a soma dos preços).

**Exercícios** tem um separador por modalidade. Cada exercício diz de que
equipamento precisa, e um exercício pode pertencer a várias modalidades.
Com **Só com o meu equipamento**, vês apenas os que consegues fazer com o
que tens. Os exercícios a que falta equipamento aparecem marcados. Podes
criar os teus exercícios, editá-los e arquivá-los.

### Estatísticas por separadores

Cada tipo de gráfico é um separador; muda-se com Tab ou com o rato. A
primeira linha, **Desporto**, escolhe o desporto com ←/→. No remo, na
corrida e na natação os separadores são Distância, Tempo, Carga, Ritmo médio
e Zonas de FC. O ciclismo e o ginásio mantêm os gráficos que já tinham.

### AdHoc Analysis (o centro exploratório das Estatísticas gerais)

É o **último separador das Estatísticas gerais** (Tab, ou o rato). Serve para duas coisas, sobre os
mesmos dados, sem escreveres uma linha de código:

1. **Construir um dataset e exportá-lo para .csv** (escolhes o nome do ficheiro e o separador).
2. **Montar um gráfico dinâmico**, ao estilo Power BI, com o que quiseres.

À esquerda estão os controlos; à direita, o gráfico (ou a pré-visualização do dataset). Em cada linha,
**Enter ou um clique abrem uma lista com pesquisa** (escreves para filtrar) e **←/→ passam à opção
seguinte**. Tudo o que escolhes **fica guardado** e volta quando reabres o separador.

| Linha | O que faz |
|---|---|
| **Modo** | *Gráfico dinâmico* ou *Dataset (campos e .csv)* |
| **Fonte dos dados** | **Sessões** (todos os desportos, uma linha por sessão; as importadas do Garmin/TrainingPeaks também; **nunca** o Strava), **Séries de força** (uma linha por série), **Diário** (saúde e alimentação), **Análises clínicas** (um marcador por linha), **Testes de longevidade** e **Pressão arterial** (uma medição por linha) |
| **Vista guardada** | abre uma vista que guardaste (fonte, campos, filtros e gráfico) |
| **Período** | tudo, 7/30/90 dias, último ano, este ano, ou *datas à escolha* (aparecem «de» e «até», com calendário) |
| **Filtros** | até 6 (muda-se em Avançado). Cada filtro é *campo · operador · valor*: as categorias dão-te a lista dos valores que existem, os números escrevem-se, as datas abrem o calendário |
| **Campos do dataset** | (modo dataset) marcas os campos que queres no .csv |
| **Eixo X** | qualquer campo: uma data (agrupada por dia, semana, mês ou ano — os períodos vazios contam como zero nas somas e contagens), uma categoria (maior primeiro, ou pela ordem natural; as que passam do limite ficam em «Outros») ou um número (vira um histograma com as classes que definires) |
| **Valor (eixo Y)** | um campo numérico, ou a *contagem de linhas* |
| **Agregação** | soma, média, mínimo, máximo, mediana ou contagem |
| **Legenda** | uma série por categoria (por exemplo, uma cor por desporto); as séries a mais ficam em «Outros» |
| **Tipo de gráfico** | colunas (lado a lado, se houver legenda), colunas empilhadas, linhas ou dispersão (dois números: um em X, outro em Y) |

Clica num ponto do gráfico para ver o valor. Por baixo do gráfico, uma linha diz quantas linhas
passaram nos filtros.

**Botões, em baixo à direita:**

- **Exportar .csv…** — abre uma janela com o **nome do ficheiro**, o **separador de valores**
  (`;` `,` Tab ou `|`), o separador decimal, o cabeçalho (nomes legíveis ou chaves técnicas) e o
  UTF-8 com BOM (o Excel abre bem os acentos). Em modo gráfico podes exportar o **dataset** ou os
  **números do gráfico**. Os valores por omissão estão em Definições → Avançado → Análise AdHoc. O
  ficheiro vai para a pasta `exports` dos dados (ou a que definires) e **nunca substitui** um que já
  exista (junta `-2`, `-3`…). Se escreveres pastas no nome (`../x`), só conta o nome do ficheiro: nunca sai da pasta de destino.
- **Guardar vista…** — dá um nome à vista. **Apagar vista** apaga a que está aberta.

O .csv defende-se de «injeção de fórmulas»: uma célula de texto que comece por `=`, `+`, `-` ou `@`
leva um `'` à frente, para o Excel não a executar.

**Pela linha de comandos** (sem abrir a janela), a mesma exportação:

```bash
python main.py --adhoc-exportar sessions --destino ~/Documentos --nome as-minhas-sessoes --separador ";"
python main.py --adhoc-exportar sessions --vista "Carga por semana"
```

As fontes são `sessions`, `sets`, `daily`, `labs`, `tests` e `bp` (pressão arterial). Sem `--vista` leva os campos por omissão
da fonte; com `--vista`, os campos, o período e os filtros dessa vista.

**Privacidade.** Nada daqui sai do computador, e o agente de IA nunca vê os dados da AdHoc: só vê o
que o ecrã mostra, e só se o pedires.

### Definições → Avançado (as opções afináveis)

Tudo o que antes estava «escrito no código» e faz sentido mudares está agora em **Definições →
Avançado**. Os números mudam com ←/→ (Shift: 10 passos) ou escrevendo o valor (só conta se estiver
dentro dos limites); as escolhas abrem uma lista (Enter ou clique); o texto escreve-se. Como o resto
das Definições, **só fica gravado com Guardar** (Ctrl+S). Cada linha diz quando o valor já não é o
de omissão. Não estão disponíveis durante uma sessão.

| Opção | Limites | Por omissão | Para quê |
|---|---|---|---|
| **Sessões e aparelhos** | | | |
| Contagem antes de começar (`session_countdown_s`) | 0 a 60 s | 15 s | segundos de contagem antes de qualquer sessão (0 = começa logo) |
| Pausa automática ao fim de (`auto_pause_after_s`) | 1 a 30 s | 3 s | segundos sem pedalar até a sessão pausar (se a pausa automática estiver ligada) |
| Aparelho sem dados ao fim de (`device_stale_after_s`) | 2 a 30 s | 5 s | segundos sem receber um valor até um sensor contar como perdido |
| Procura Bluetooth: duração (`ble_scan_s`) | 3 a 30 s | 8 s | quanto tempo a procura de aparelhos Bluetooth escuta (mais tempo encontra mais) |
| Procura ANT+: duração (`ant_scan_s`) | 3 a 60 s | 12 s | quanto tempo a procura de aparelhos ANT+ escuta (mais tempo encontra mais) |
| Duração dos avisos (`message_seconds`) | 2 a 20 s | 6 s | quanto tempo fica no topo a mensagem («Guardado», «Exportado»…) |
| Passadeira: velocidade máxima à partida (`treadmill_start_speed_max_kmh`) | 8 a 40 km/h | 25 km/h | o máximo que a lista de velocidades da passadeira oferece ao começar |
| Força: passo da carga (`strength_load_step_kg`) | 0.25 a 20 kg | 2.5 kg | quanto muda a carga de uma série com cada toque nas setas |
| Força: passo do RPE (`strength_rpe_step`) | 0.1 a 1 | 0.5 | quanto muda o RPE de uma série com cada toque nas setas |
| **Treinos e importação** | | | |
| Tolerância do alvo de potência (`workout_tolerance_pct`) | 1 a 25 % | 5 % | ± % do alvo que conta como «no alvo» durante um treino |
| Tolerância na revisão da sessão (`review_tolerance_pct`) | 1 a 25 % | 6 % | ± % do limiar, na revisão, quando o bloco não define outra |
| Exportar: potência do bloco «livre» (`export_freeride_pct`) | 20 a 100 % FTP | 50 % FTP | os formatos .erg/.mrc não têm blocos livres: pedala-se a esta % do FTP |
| Rotas GPX: distância entre pontos (`gpx_resample_step_m`) | 1 a 50 m | 5 m | as rotas importadas são reamostradas a esta distância (vale para as novas) |
| **Ligações externas** | | | |
| Strava: porta do retorno local (`strava_redirect_port`) | 1024 a 65535 | 8723 | a porta onde a Perennia espera o regresso do Strava (só nesta máquina) |
| Garmin: tempo máximo de uma sincronização (`garmin_sync_timeout_s`) | 60 a 21600 s | 3600 s | a sincronização é interrompida se demorar mais do que isto |
| **Análise AdHoc** | | | |
| CSV: separador de valores (`adhoc_csv_sep`) | ;, ,, Tab, | | ; (ponto e vírgula) | o que se propõe ao exportar (escolhe-se de novo em cada exportação) |
| CSV: separador decimal (`adhoc_csv_decimal`) | «.» ponto, «,» vírgula | «.» ponto | igual ao separador de valores não pode ser: usa-se o ponto |
| CSV: UTF-8 com BOM (`adhoc_csv_bom`) | ligado / desligado | ligado | o Excel abre bem os acentos |
| CSV: pasta das exportações (`adhoc_export_dir`) | texto | (vazio) | vazio = a pasta «exports» dentro da pasta de dados |
| Gráfico: categorias no eixo X (`adhoc_max_categories`) | 2 a 120 | 15 | as categorias a mais ficam agrupadas em «Outros» |
| Gráfico: séries na legenda (`adhoc_max_series`) | 1 a 7 | 6 | as séries a mais ficam agrupadas em «Outros» |
| Gráfico: pontos na dispersão (`adhoc_max_points`) | 10 a 2000 | 400 | acima disto desenha-se uma amostra |
| Gráfico: classes do histograma (`adhoc_bins`) | 2 a 40 | 10 | quando o eixo X é um número, agrupa-se em classes |
| Dataset: linhas da pré-visualização (`adhoc_preview_rows`) | 1 a 16 | 12 | (o .csv leva sempre todas as linhas) |
| Filtros por vista (`adhoc_max_filters`) | 1 a 10 | 6 |  |
| **Agente de IA e tokens** | | | |
| Caracteres por token (estimativa) (`agent_chars_per_token`) | 1.5 a 8 | 3.5 | serve só para estimar os tokens antes de enviar; em português e com JSON costuma ser ~3,5 |
| Máximo de tokens da resposta (`agent_max_output_tokens`) | 64 a 8192 | 1024 | o limite que se pede ao fornecedor para a resposta |
| Avisar acima de (tokens) (`agent_warn_tokens`) | 500 a 200000 | 8000 | um pedido maior do que isto mostra um aviso antes de enviar |
| Preço por milhão de tokens enviados (`agent_price_in_per_mtok`) | 0 a 1000 | 0 | 0 = não mostra o custo; vê o preço no site do fornecedor |
| Preço por milhão de tokens da resposta (`agent_price_out_per_mtok`) | 0 a 1000 | 0 |  |
| Moeda do custo (`agent_currency`) | texto | US$ |  |
| **Saúde e pressão arterial** | | | |
| Pressão arterial: média diária (`bp_daily_mode`) | média das médias dos períodos, média de todas as medições | média das médias dos períodos | «períodos»: manhã e noite pesam o mesmo, mesmo com números de medições diferentes |
| Pressão arterial: ignorar a 1.ª medição (`bp_discard_first`) | ligado / desligado | desligado | em cada período com 3 ou mais medições, a primeira não conta para a média (costuma sair mais alta) |
| Pressão alta: máxima a partir de (`bp_high_sys`) | 110 a 180 mmHg | 135 mmHg | limiar para medições em casa (135/85 é o valor habitual das recomendações) |
| Pressão alta: mínima a partir de (`bp_high_dia`) | 60 a 120 mmHg | 85 mmHg |  |
| Pressão baixa: máxima abaixo de (`bp_low_sys`) | 70 a 110 mmHg | 90 mmHg |  |
| Pressão baixa: mínima abaixo de (`bp_low_dia`) | 40 a 80 mmHg | 60 mmHg |  |
| Pressão muito alta: máxima a partir de (`bp_crisis_sys`) | 150 a 220 mmHg | 180 mmHg | acima disto a Perennia diz para repetires a medição e contactares um médico |
| Pressão muito alta: mínima a partir de (`bp_crisis_dia`) | 95 a 140 mmHg | 110 mmHg |  |
| Período «manhã» até às (`bp_morning_until_h`) | 6 a 14 h | 12 h | a hora da medição sugere o período (podes sempre escolher outro) |
| Período «tarde» até às (`bp_afternoon_until_h`) | 14 a 22 h | 19 h |  |
| Assistente de saúde: período recente (`health_window_days`) | 3 a 60 d | 14 d | os dias mais recentes, que se comparam com o período de base |
| Assistente de saúde: período de base (`health_baseline_days`) | 14 a 365 d | 90 d |  |
| Sono: mínimo desejável (`health_sleep_min_h`) | 4 a 10 h | 7 h |  |
| FC em repouso: subida que merece aviso (`health_rhr_rise_bpm`) | 1 a 20 bpm | 5 bpm | média recente acima da de base por este valor |
| HRV: descida que merece aviso (`health_hrv_drop_pct`) | 3 a 50 % | 15 % |  |
| Bebidas alcoólicas: máximo por semana (`health_alcohol_week_max`) | 0 a 30 | 7 |  |
| Peso: variação que merece aviso (`health_weight_change_pct`) | 0.5 a 10 % | 2 % | diferença entre a média recente e a de base |
| Assistente de saúde: dias mínimos de registo (`health_min_days`) | 1 a 14 d | 3 d | com menos dias do que isto no período, não tira conclusões sobre a métrica |
| Dias seguidos de treino que pedem descanso (`health_streak_rest_days`) | 3 a 30 d | 10 d |  |
| **Treinador e Assistente de saúde** | | | |
| Treinador: aconselhamento (`advisor_coach_mode`) | Regras da Perennia, LLM local, Agente online | Regras da Perennia (offline, já funciona) | as regras funcionam já, sem rede; o LLM local e o agente online ficam preparados (mostram o pedido e os tokens, sem enviar) |
| Assistente de saúde: aconselhamento (`advisor_health_mode`) | Regras da Perennia, LLM local, Agente online | Regras da Perennia (offline, já funciona) |  |
| Agente online: fornecedor (`advisor_online_provider`) | Claude, ChatGPT, Gemini, Outro | Claude (Anthropic) | a chave vem SEMPRE de uma variável de ambiente (ver RUN.md); nunca se escreve aqui |
| Agente online: modelo (`advisor_online_model`) | texto | (vazio) | o nome do modelo no fornecedor (vazio: o de omissão do fornecedor) |
| LLM local: endereço (`advisor_local_url`) | texto | http://127.0.0.1:11434 | onde o teu LLM local (Ollama, LM Studio, llama.cpp) escuta — só no teu computador |
| LLM local: modelo (`advisor_local_model`) | texto | (vazio) | por exemplo «qwen2.5:7b» ou «llama3.1:8b» |
| LLM local: janela de contexto (`advisor_local_context_tokens`) | 1024 a 262144 tokens | 8192 tokens | um pedido maior do que isto não cabe no modelo local: a Perennia avisa |
| Construtor: feedback do Treinador ao vivo (`coach_live_feedback`) | ligado / desligado | ligado | depois de pedires feedback uma vez, o veredicto atualiza-se enquanto editas |
| Subida máxima da forma (CTL) por semana (`coach_ramp_max_per_week`) | 1 a 12 | 5 | acima disto o Treinador diz que a semana é carga a mais |
| Forma (TSB) abaixo da qual se alivia (`coach_tired_tsb`) | -50 a 0 | -20 |  |
| Forma (TSB) abaixo da qual se descansa (`coach_overload_tsb`) | -70 a -5 | -30 |  |
| Forma (TSB) acima da qual se está fresco (`coach_fresh_tsb`) | -5 a 30 | 5 |  |
| Treino pesado: vezes a carga habitual (`coach_heavy_factor`) | 1.1 a 4 | 1.5 | a carga de um treino a dividir pela carga típica das tuas sessões recentes |
| Treino pesado demais: vezes a carga habitual (`coach_very_heavy_factor`) | 1.2 a 6 | 2.2 |  |
| Treinador: dias de histórico que conta (`coach_history_days`) | 14 a 180 d | 42 d |  |
| Evento: dias de afinação antes (`coach_taper_days`) | 2 a 21 d | 7 d |  |
| Evento: semanas que vão para o calendário (`coach_plan_weeks_max`) | 1 a 52 | 16 | o plano mais comprido do que isto só agenda as primeiras semanas |
| Disponibilidade por omissão: dia de semana (`coach_weekday_minutes`) | 0 a 300 min | 60 min |  |
| Disponibilidade por omissão: dia de fim de semana (`coach_weekend_minutes`) | 0 a 600 min | 180 min |  |
| Evento: hidratos por hora (`coach_carbs_g_per_h`) | 20 a 120 g | 60 g | para esforços até à duração «evento longo» |
| Evento longo: hidratos por hora (`coach_carbs_long_g_per_h`) | 30 a 120 g | 80 g |  |
| Evento longo a partir de (`coach_long_event_h`) | 1 a 8 h | 2.5 h |  |
| Evento: líquidos por hora (`coach_fluid_ml_per_h`) | 200 a 1200 ml | 600 ml |  |
| Longevidade: eixo fraco abaixo de (`coach_weak_axis_score`) | 10 a 90 | 50 | os eixos do índice de longevidade abaixo desta nota entram no caminho proposto |
| Longevidade: duração de cada fase (`coach_path_weeks`) | 2 a 12 | 4 |  |
| Evento: treino longo necessário (`coach_long_share_pct`) | 40 a 100 % | 75 % | a parte da duração do evento a que o teu treino mais longo deve chegar antes |
| Evento: partida «cedo» antes das (`coach_early_start_h`) | 5 a 11 h | 9 h | antes desta hora, a refeição que conta é o jantar da véspera |
| Treino: máximo em Z5 ou acima (`coach_z5_max_min`) | 5 a 90 min | 30 min | acima disto o Treinador avisa |
| Treino: máximo em Z4 (`coach_z4_max_min`) | 10 a 180 min | 60 min |  |
| Força: progressão exigente (repetições) (`coach_reps_week_soft_pct`) | 1 a 20 % | 6 % | subida por semana acima da qual o objetivo passa de «realista» a «exigente» |
| Força: progressão muito ambiciosa (repetições) (`coach_reps_week_hard_pct`) | 2 a 40 % | 12 % |  |
| Força: progressão exigente (kg) (`coach_load_week_soft_pct`) | 0.5 a 10 % | 2.5 % |  |
| Força: progressão muito ambiciosa (kg) (`coach_load_week_hard_pct`) | 1 a 20 % | 5 % |  |
| Força: ritmo muito denso (`coach_reps_per_min_dense`) | 10 a 80 rep/min | 30 rep/min | repetições por minuto (num evento com limite de tempo) que já pedem aviso |
| Força: ritmo acima do possível (`coach_reps_per_min_max`) | 15 a 120 rep/min | 45 rep/min |  |
| **Dados e backups** | | | |
| Backup: tamanho máximo ao repor (`backup_restore_max_mb`) | 64 a 1.04858e+06 MB | 4096 MB | um backup que, descomprimido, passe disto é recusado (defesa contra ficheiros feitos para encher o disco) |

Estas opções ficam na tabela `settings` da base local e vão nos backups com as **Definições**.
Nenhuma guarda segredos.

### Treinos que vêm com a aplicação

Em **Treinos** já estão 18 treinos estruturados, em % da FTP, por isso
servem a qualquer atleta. Todos têm aquecimento, retorno à calma e dicas de
texto no ecrã: recuperação ativa, resistência Z2 (60 e 90 min), tempo
3×15, sweet spot 3×12 e 2×20, limiar 2×20, escada de limiar 5-10-15,
over-unders 3×9, VO2máx 5×4, 30/30 e 40/20, pirâmide, anaeróbico 8×1,
sprints 8×15 s, força a baixa cadência, cadência e ativação pré-prova. A
descrição diz para que serve cada um. Um treino de origem que apagues não
volta.

Em **Definições → Passos seguintes no treino** escolhes quantos blocos
seguintes aparecem no plano (0 a 4; vem com 2).

### Estatísticas

Em cima há quatro linhas que se mudam com ←/→ (ou Enter):

- **Gráfico:** curva de potência, evolução, tempo em zona, tempo em zona por
  período, fitness/fadiga/forma, FTP estimada, perfil de potência, cadência,
  balanço E/D e **Decoupling**.
- **Métrica** (na evolução): distância, tempo, subida, carga (TSS),
  sessões, potência média, FC média e trabalho (kJ).
- **Agrupar por:** dia, semana, mês, trimestre, semestre ou ano.
- **Intervalo:** os últimos 4, 6, 8, 12, 16, 24, 36, 52 ou 104 desses
  grupos. Por exemplo, os últimos 12 meses, os últimos 4 anos ou os últimos
  16 dias.

Por baixo aparecem os totais do período e o **percentil** do período atual
em relação a todo o teu histórico. Por exemplo: "Esta semana: 145 km —
percentil 88 das tuas semanas · melhor 212 km". Os grupos sem sessões também
contam, porque treinar sempre um pouco pesa mais do que um pico isolado.

O **Decoupling** (ciclismo; Pa:HR) compara a **eficiência** — potência ÷ FC — da 1.ª metade de
cada sessão com a da 2.ª: `(EF₁ − EF₂) / EF₁ × 100`. Positivo = a FC subiu para a mesma potência
(deriva cardíaca). Só entram sessões **com FC e com pelo menos 40 minutos** (o cálculo precisa
de 20 min). Lê-se assim: **menos de 5 %** base aeróbia forte · **5–10 %** ainda a construir ·
**mais de 10 %** deriva a mais (fadiga, calor, desidratação ou base fraca). O gráfico mostra a
evolução ao longo do tempo.

A **curva de potência** é sempre do histórico todo. Tem os watts no eixo
vertical e, ao clicares num ponto (ou com ←/→ na linha "Ponto"), mostra a
duração, os watts, os W/kg e a **data** em que fizeste esse recorde. Nos
gráficos de barras, clicar numa barra mostra o valor.

O **perfil de potência** compara os teus melhores 5 s, 1 min, 5 min e o
limiar (95 % dos melhores 20 min) com a escala de Coggan em W/kg, para homens
ou mulheres (linha "Tabela"). Para cada duração dá a posição de 0 a 100 e o
nível, de "não treinado" a "classe mundial". Esta escala é uma referência de
treino, não um percentil de uma população medida.

### Fitness, fadiga e forma

São três números que as plataformas de treino usam (no TrainingPeaks chamam-se
CTL, ATL e TSB). **Calculam-se exatamente como no TrainingPeaks e no WKO
(modelo de Coggan):**

- **Fitness (CTL):** média exponencial da carga diária com constante de 42
  dias: CTL hoje = CTL ontem + (carga de hoje − CTL ontem) × (1 − e^(−1/42)).
  Sobe devagar com o treino consistente.
- **Fadiga (ATL):** o mesmo, com constante de 7 dias. Sobe e desce depressa.
- **Forma (TSB):** o fitness **de ontem** menos a fadiga **de ontem** — a
  forma com que entras no dia, antes do treino de hoje (como o
  TrainingPeaks).

Um treino de 100 TSS a partir do zero dá CTL 2,4 e ATL 13,3, e no dia
seguinte TSB −11 — os mesmos números do TrainingPeaks. As
**atividades importadas** (GarminDB, TrainingPeaks) contam com a TSS do
TrainingPeaks quando a têm, ou pela FC; uma atividade do mesmo dia e do
mesmo desporto que uma sessão da Perennia, com duração parecida (± 25 %), é
a mesma e não conta duas vezes.

A frase por baixo diz em que zona estás: acima de +25 "muito fresco: a perder
forma"; +5 a +25 "fresco: bom para competir ou testar"; −10 a +5 "zona
neutra"; −30 a −10 "a construir forma"; abaixo de −30 "carga muito alta".

A **carga** do ciclismo é a TSS (potência normalizada). A da **corrida** é
a **rTSS** (velocidade normalizada, com o declive, face ao teu ritmo de
limiar) e a da **natação** a **sTSS** (velocidade face à CSS, ao cubo),
como no TrainingPeaks. Na primeira vez que abres esta versão, as cargas das
corridas e natações já gravadas são recalculadas assim. A da força calcula-se pela frequência
cardíaca na mesma escala (uma hora no teu limiar = 100). Sem FC suficiente,
usa o RPE (RPE 10 durante uma hora = 100). Nas estatísticas do ciclismo o
gráfico conta só o ciclismo; nas da força, só a força; nas **Estatísticas
gerais**, os dois juntos.

### FTP estimada

Em **Estatísticas → FTP estimada** a aplicação estima a tua FTP com as
sessões dos últimos 90 dias, sem precisares de fazer um teste:

1. a melhor hora, se tiveres um esforço de 60 min (é a definição de FTP);
2. senão, 95 % dos melhores 20 min;
3. senão, o modelo de **potência crítica** (CP), com pelo menos três esforços
   entre 2 e 20 min. O CP fica quase sempre um pouco acima da FTP, por isso
   usa-se 97 %. Também mostra o W′ (a "bateria" acima do CP, em kJ).

O gráfico mostra a FTP estimada no fim de cada semana ou mês. Na linha
**Aplicar a FTP estimada** carregas em Enter e a FTP do teu perfil passa a
ser essa (fica no histórico de testes como "estimate").

### Tempo em zona por período

Em **Estatísticas → Tempo em zona por período** cada barra é uma semana (ou
mês, etc.), partida pelas zonas de potência ou de FC (troca na linha
"Métrica"). Mostra se o treino da semana foi sobretudo Z2 ou se foi tudo
intensidade.

### Construtor de treinos e exportação (ciclismo)

No menu do Ciclismo, **Construtor de treinos** lista todos os treinos (os
que vêm com a aplicação, os importados e os teus). Enter abre um para editar;
**+ Novo treino** começa um com aquecimento, um bloco e retorno à calma.

No editor:

- **+ Passo constante**, **+ Rampa** e **+ Passo livre** (sem alvo) juntam um
  passo e abrem-no.
- **+ Bloco de repetições**: por exemplo 5 × (3 min a 110 % + 2 min a 55 %).
  Os passos entram antes do retorno à calma.
- Num passo: tipo, duração (←/→ de 15 s, Shift de 1 min, ou escreve os
  minutos: "2,5" = 2:30), alvo em **% da FTP** ou em **watts**, alvo no
  início e no fim (rampas), cadência e texto que aparece no ecrã.
- ←/→ num passo da lista muda-o de lugar; Del apaga-o.
- Em cima vês a duração, a TSS e o IF estimados com a tua FTP.

**Exportar** grava para a pasta `exports/` (o caminho aparece no ecrã), num
destes formatos ou em todos:

| Formato | Para quê |
|---|---|
| `.zwo` | Zwift, TrainerRoad, MyWhoosh, TrainingPeaks Virtual |
| `.erg` | programas que querem watts (calculados com a tua FTP de agora) |
| `.mrc` | programas que querem % da FTP (aplicam a FTP deles) |
| `.fit` | treino estruturado para Garmin Edge, relógios Garmin e Wahoo |

No `.fit`, as rampas partem-se em degraus de 1 minuto (o formato não tem
rampas), e cada passo leva um intervalo de ±2,5 % à volta do alvo. Para o pôr
num Garmin Edge, copia-o para a pasta `Garmin/NewFiles` do aparelho ligado
por USB.

Na lista, **E** exporta o treino selecionado sem o abrir.

### Força

O cartão **Força** tem o seu menu:

- **Treinar:** escolhes um plano, **lês o plano inteiro** (exercícios, séries,
  repetições, carga, RPE alvo, descanso e o que fizeste da última vez) e só
  depois **▶ Começar o treino**. Sem plano não se treina.
- **Construtor de treinos:** cria e edita planos. Vêm três feitos: Força A e
  Força B (corpo inteiro) e Longevidade (força e equilíbrio). Há 47
  exercícios na lista, por grupo, e podes criar os teus.
- **Histórico:** as sessões, e dentro de cada uma as séries.
- **Estatísticas:** evolução por semana/mês (volume, treinos, séries,
  repetições, horas, carga, RPE médio, FC média), **progressão por
  exercício** (1RM estimada, carga máxima, volume), tempo em zona de FC e
  fitness/fadiga/forma só da força.
- **Dispositivos:** para ligar a FC.

**Durante o treino**, à esquerda há as ações e à direita o painel: a série ou
o descanso a contar, a FC grande com a zona, o tempo, o volume, e as séries
já feitas daquele exercício.

1. **Espaço** (ou Enter na primeira linha) começa a série.
2. **Espaço** outra vez termina-a. Fica registada com o que está nos campos
   (repetições e carga, que começam com o que o plano pede) e com a FC
   média dessa série. Começa o descanso, em contagem decrescente; fica
   vermelho quando passa do tempo.
3. **Durante o descanso, a linha do exercício corrige a série que acabou**: se saíram 5
   em vez de 6, ←/→ (Shift para passos maiores) ou
   escreve o número; a carga muda com **[** e **]**. A carga que puseres passa para a série seguinte.
4. **Espaço** começa a série seguinte. Quando um exercício acaba, passa ao
   seguinte; o painel diz qual vem.

Também podes: **+ Série extra**, **Saltar** (o exercício, mesmo a meio de uma série; **N** salta o
bloco), **Pausa** (P, que abre o aviso **PAUSA**). **Terminar o treino** (F10, ou a seta Voltar)
pergunta primeiro; Esc só pausa. No fim tens o resumo por exercício, com
a 1RM estimada, e o `.fit` fica na pasta `strength/`.

A **1RM estimada** usa a fórmula de Epley. Como a sessão já não pede o RPE, uma série conta como
feita até ao limite (6 repetições contam como 6); se uma série tem RPE registado (treinos antigos,
séries editadas depois, ou importadas), conta as repetições em reserva: 6 repetições a RPE 8 contam
como 8. Só vale até umas 12–15
repetições no total; acima disso não se calcula. O **volume** é carga ×
repetições; nos exercícios com o peso do corpo (elevações, flexões…) entra a
parte do teu peso que o exercício move.

**Frequência cardíaca na força.** Serve qualquer banda cardíaca (ANT+ ou
Bluetooth) ou um relógio que transmita a FC. O **Garmin Swim 2 transmite por
ANT+** (não por Bluetooth), por isso precisas da antena ANT+ USB:

1. No relógio, no widget da frequência cardíaca, mantém **UP** carregado.
2. **Opções de FC → Transmitir FC** (ou "Transmitir durante a atividade",
   que começa sozinho quando inicias uma atividade no relógio).
3. Na aplicação, **Dispositivos → Procurar ANT+**. O relógio aparece como
   monitor de frequência cardíaca; liga-o.

A transmissão gasta mais bateria do relógio. Com o widget a transmitir, o
relógio fica só nesse ecrã.

**O `.fit` da força** é uma atividade de "treino de força", com a FC a cada
segundo e uma série por exercício (repetições, carga e duração) e os
descansos, como os relógios Garmin gravam. O Garmin Connect deve mostrar a
família de cada exercício (supino, agachamento, remada…), não o nome exato
que lhe deste.

### Treino livre e Conditioning (força)

No menu da Força há dois modos sem plano, feitos de **voltas**:

- **Treino livre:** abres uma volta de **Força** (escolhes o exercício e
  registas repetições, carga e RPE), de **Descanso**, de **Passadeira** ou de
  **Cardio**. Abrir a volta seguinte fecha a anterior.
- **Conditioning:** o mesmo, com a passadeira à cabeça. Para a tua passadeira
  sem ligação: no fim de cada intervalo escreves o **total que o visor mostra**
  (km), a velocidade e a inclinação, e a aplicação calcula a distância dessa
  volta (total agora − total no fim da volta de passadeira anterior).

**Espaço** alterna entre trabalho e descanso: do trabalho abre um descanso;
do descanso volta ao último trabalho, com o mesmo exercício (ou a mesma
velocidade e inclinação na passadeira) já preenchido. Os campos corrigem a
volta aberta ou, se nenhuma estiver aberta, a última.

A FC vem do relógio a transmitir (Swim 2 por ANT+) ou da banda. Cada volta
guarda a FC média e máxima. As séries de força contam para as estatísticas
e para a 1RM estimada, como num treino com plano. O `.fit` leva uma volta por
volta (com a distância nas da passadeira), as séries e os descansos.

### Challenge (ciclismo)

No menu do ciclismo, **Challenge** junta:

- **Fuga** (a de sempre, ver abaixo).
- **Desafio adaptativo.** A aplicação gera blocos à medida das tuas
  capacidades, a partir da tua FTP e da tua curva de potência dos últimos 90
  dias: "Aguenta 10 s a 180 % da FTP (450 W)", "Descansa agora 20 s",
  "Aguenta 2 min a 117 %"… Começa com 4 min de aquecimento e acaba com 3 de
  retorno à calma. Cada esforço conta como cumprido se a média ficar a 95 %
  do alvo ou mais. Cumpres, o nível sobe 0,015; falhas, desce 0,03 (e o
  descanso seguinte alonga). **O nível fica guardado** e a sessão seguinte
  começa daí. O rolo põe os watts (ERG) e o desafio é aguentar a cadência.
  Cada jogo abre numa janela com o nome e **como se joga** em cima, e depois
  a duração, os bots, a rota `.gpx` (com os segmentos do Strava) e o auto
  lap.
- **Jogos**, contra bots gerados à volta das tuas capacidades, por isso um
  atleta de 150 W e um de 350 W têm o mesmo desafio:
  - **Zone Hero:** as zonas vão passando; manter a zona dá pontos, a
    sequência dá combos (até ×4), e os **anéis de sprint** (10 s a 150 %)
    dão +200.
  - **Power Ladder:** o alvo sobe 5 % da FTP a cada 30 s; sais quando a
    média de 10 s fica abaixo de 95 % do alvo. Ganha quem aguentar mais.
  - **Aquecimento:** progressivo; ganha o mais preciso.
  - **Eliminação:** corrida em pista de 250 m com **aspiração** (atrás de
    outro, a menos de 6 m, gastas menos); a cada duas voltas sai o último.
    Os bots atacam quando estão em risco e têm uma reserva acima da FTP que
    se gasta e recupera.
  - **Cabo de guerra:** contra um bot que puxa por ondas; a corda anda com a
    diferença entre a tua % da FTP e a dele.

**Nenhum alvo dura menos de 10 segundos**, para o rolo fazer a transição sem
solavancos. Escolhes a duração, o número de bots e a rota (a estrada é só
paisagem). Durante o jogo o painel do centro mostra a instrução, o estado e
uma barra; à direita fica a classificação ao vivo (ou, no desafio adaptativo,
os próximos blocos). Os resultados ficam guardados com recorde por jogo. Dos
34 jogos que me mostraste, estes são os que fazem sentido para um só atleta e
ficaram feitos agora; os de equipa precisam de outras pessoas.

### Testes de aptidão

Cada modalidade tem os seus **Testes** (na janela **Sessão de treino** →
**Testes**, ou — na natação — no separador Treinar; no ginásio, os de
longevidade; e na Saúde). Ao abrir um teste
vês os **blocos** dele num gráfico, como no construtor de treinos (o
aquecimento, o esforço — «livre», no máximo — e o retorno à calma), com o
alvo de cada bloco; um teste sem duração (repetições, medidas) mostra as
instruções:

| Modalidade | Testes que vêm com a aplicação |
|---|---|
| Ciclismo | FTP (20 min, rampa, 2 × 8), sprint de 5 s, 1 min máximo, 5 min máximo (dá o VO2máx estimado) |
| Remo | 2000 m, 500 m, distância em 30 min, distância em 1 min |
| Corrida | 5 km, Cooper 12 min (dá o VO2máx estimado), 1 km, 3 km |
| Longevidade | força de preensão (cada mão), flexões em 1 min e máximas, elevações máximas e em 1 min, suspensão na barra, sentar e levantar em 30 s, agachamentos em 1 min, equilíbrio numa perna de olhos fechados, sentar e levantar do chão (0–10), prancha, salto vertical, caminhada de 6 min |

Os de ciclismo correm no rolo como o teste de FTP, e os de remo na máquina
de remo; o resultado fica guardado sozinho no fim (o de 2000 m também
atualiza a FTP do remo). Os outros têm **cronómetro**: contagem decrescente
nos que têm duração (flexões em 1 min), cronómetro nos que medem tempo
(suspensão, prancha, equilíbrio), e depois escreves o resultado e as notas.
Também podes só **registar um resultado** de um teste feito fora da
aplicação — na **natação** é só isto (a prova faz-se na piscina; não há
«Fazer o teste»). Cada teste mostra o último, o melhor e a tendência.

**A página de um teste** tem em cima os blocos e, por baixo, as ações e a
**lista dos resultados** (data, valor e notas). **Enter num resultado abre
uma janela** onde o corriges (valor, data com o seletor, notas) ou o
**apagas** (com confirmação); **Registar um resultado** também abre essa
janela. **+ Novo
teste** cria os teus (nome, unidade, se é melhor mais alto ou mais baixo,
duração e instruções); os que vêm com a aplicação também se editam ou
desativam.

### Configurações sonoras (bips)

Em **Definições → Configurações sonoras** (também durante uma sessão, onde se aplicam já ao voltar)
escolhes os **bips** que avisam do fim (ou do princípio)
de um **bloco**, de uma **série** ou de um **descanso** — para perceberes que o tempo está a
acabar sem olhar para o ecrã. O bip é um tom gerado pela própria Perennia (sem ficheiros nem
dependências); se o computador não tiver som, toca o «beep» do terminal (o sino, que em muitos PC
é o altifalante da motherboard).

- **Bips** liga e desliga todos os avisos; **Bip longo no fim** é um bip mais comprido quando o
  tempo chega a zero.
- **Regras** — cada uma diz **quando**: os *primeiros* ou os *últimos* **N segundos**; **quantos
  bips por segundo** (0 = um só bip, no início da janela; 1 a 4 em cada segundo); e **onde**: em
  tudo, só nos blocos e nas séries, ou só nos descansos. Exemplos: *primeiros 10 s, um só bip*;
  *últimos 10 s, 1 bip por segundo*; *últimos 5 s, 2 bips por segundo*. Várias regras somam-se (se
  duas calharem no mesmo instante, toca um bip só). **+ Nova regra**, Enter edita, Del apaga,
  **Repor as de origem**, **Testar os bips** (toca um bloco de 15 s e um descanso de 12 s com as
  regras que estão no ecrã). As alterações gravam-se com **Guardar**.
- **De origem**: os **últimos 5 segundos, um bip por segundo**, mais o bip longo no fim.
- **Visível**: os últimos 5 segundos **vêem-se sempre**, mesmo com o som desligado: a caixa do tempo
  (em cima, ao centro) **pisca a vermelho** e mostra **5 · 4 · 3 · 2 · 1** (no ciclismo, o número
  aparece grande ao centro, no topo). **No ginásio** não há relógio no topo: a contagem vai para a
  métrica **Série / descanso**, que pisca; sem essa métrica no ecrã, o aviso ao centro mostra o número.
- Onde conta: nos **descansos** e nas **séries com tempo** do ginásio, e nos **blocos de tempo** dos
  treinos de ciclismo, corrida e remo (blocos por distância não têm contagem). A regra «só nos
  descansos» não se aplica ao ciclismo (os blocos de ciclismo não têm descanso à parte). As
  regras que mudares valem a partir da sessão seguinte.

### Terminar uma sessão (todos os desportos)

O **ciclismo é a base** e a corrida e o remo fazem agora **exatamente o mesmo**:

- **P** pausa e retoma. **Esc não termina**: pausa e abre o aviso **PAUSA** (com **Retomar
  sessão** e **Terminar treino**; P ou Esc retomam, F10 termina). **F10** (ou o botão de voltar)
  abre o diálogo **«Terminar a
  sessão?»** — o mesmo do ciclismo, com **Sim, terminar** · **Não, continuar** ·
  **Terminar sem guardar (D)**. Enquanto o diálogo está aberto a sessão fica parada. Se a
  sessão estava no PAUSA, «Não» volta a ele.
- No diálogo: **Enter, S ou Y** terminam · **Esc ou N** voltam (e retomam, se foi o
  diálogo que parou a sessão) · **D** termina sem guardar (nada de .fit nem estatísticas).
- **Sim, terminar** abre a **janela das etiquetas** (ver abaixo); **Enter, Enter** termina
  com as etiquetas sugeridas. A página de **resumo** é igual nos três desportos
  (título «Sessão concluída», onde ficou o .fit, o feedback, o **radar do que treinou** e o
  efeito no índice de longevidade).
- A sessão de ciclismo já não mostra a **distância** (em cima, à esquerda) nem o **tempo
  de sessão** (em cima, ao centro) no cabeçalho — estão nas métricas, se as quiseres.

**Simuladores** (Dispositivos): cada um dá **só os dados do seu aparelho**.
**SEM HARDWARE - Trainer** dá potência, cadência e velocidade, **sem FC**;
**SEM HARDWARE - Remo**, a remada; **SEM HARDWARE - Passadeira** (novo), a velocidade
e a distância da corrida (a inclinação que o treino ou a rota pedem fica registada na
passadeira); a FC vem **só** da **SEM HARDWARE - Banda cardíaca**.

### Etiquetas e tipo de sessão

Cada sessão (e o seu `.fit`) leva três géneros de etiquetas:

- **Tipo de sessão** — automático: `Perennia` (**sempre**) + onde foi, **pelo desporto**
  (`Indoor Cycling`, `Indoor Rowing`, `Indoor Running`, `Pool Swimming`, `Indoor Strength` no
  ginásio — vão sempre, mesmo que a janela não as mostre). Uma sessão **que segue um .gpx** também leva
  `Virtual Cycling` / `Virtual Running` e o `.fit` vai com o subtipo **virtual** (como o
  Zwift e o MyWhoosh). **Correr na passadeira não é virtual**, a não ser que sigas um
  .gpx; uma sessão sem rota é «indoor» à secura.
- **Tipo de treino** — o esforço: recuperação, resistência aeróbia, tempo, limiar,
  VO2máx, anaeróbio / sprint, trabalho, aquecimento de prova, prova, teste, técnica,
  força, mobilidade. Um treino traz o seu (escolhido no construtor); **numa sessão livre
  sugere-se pelo esforço** (IF ≈ potência normalizada / FTP, ou √(carga / 100 h) quando
  não há potência: < 0,55 recuperação · < 0,76 resistência · < 0,88 tempo · < 1,0
  limiar · < 1,15 VO2máx · mais, anaeróbio; muito variável e forte = trabalho / VO2máx).
  Os tipos servem também a análises e à IA, mais tarde.
- **Etiquetas livres** — as que escreveres.

Ao terminar, a **janela «Etiquetas da sessão»** mostra o tipo de treino (Enter muda, com
pesquisa), o tipo de sessão, as tuas etiquetas e a linha **No .fit** com tudo como vai ficar.
**+ Adicionar etiqueta** abre uma janela onde, **ao escreveres, aparecem as etiquetas que já
existem** (sem contar maiúsculas nem acentos — «pre» acha «Pré-prova»); escolhe uma ou
**Criar «…»** (também há o botão **+ Criar etiqueta nova**), e fica no catálogo para as
próximas. **Guardar e terminar** grava; **Voltar à sessão** (ou Esc) volta atrás.
No `.fit` as etiquetas vão no **nome do perfil desportivo** (mensagem `sport`, campo
`name`: `Limiar · Perennia · Indoor Cycling · Pré-prova`), onde o Garmin Connect, o Strava e
o TrainingPeaks as mostram. Ficam também na base (`session_tags`) e na análise da sessão
(linha **Etiquetas**).

### Longevidade (menu do ecrã inicial)

O cartão **Longevidade** tem o **índice de longevidade** e os **Testes de longevidade** (que
saíram da Saúde). O índice (0–100) existe para **1 dia, 1 semana, 1 mês, 3, 6 e 9 meses, 1,
2, 3, 5, 10, 15 e 20 anos**; cada linha diz se o período curto está acima ou abaixo do
seguinte (↑ ↓ =: a tendência) e, à direita, o **radar** mostra **onde o corpo tem estado mais
ou menos concentrado** no período escolhido.

A fórmula (`perennia/core/longevity.py`): nove **eixos** — aeróbio, limiar, VO2máx, anaeróbio,
força, potência, mobilidade, estabilidade (isométricos, tendões) e recuperação. Cada sessão
dá **minutos a cada eixo**: ciclismo pelo tempo em cada zona de potência, corrida, remo e
natação pelo tempo em cada zona de FC (Z1 recuperação · Z2–Z3 aeróbio · Z4 limiar · Z5 VO2máx
· Z6–Z7 anaeróbio), ginásio pelas séries de cada exercício e as suas modalidades. Para cada
eixo e período de `D` dias:

    R = minutos do eixo / (D / 7)                  (minutos por semana)
    S = 100 · (1 − e^(−R / T))                      (satura: o último minuto vale menos)
    S' = 0,75 · S + 0,25 · teste                    (se fizeste um teste desse eixo no período)
    índice = Σ peso · S' / Σ peso

`T` é a dose semanal que dá 63 % da nota (aeróbio 240 min, limiar 30, VO2máx 15, anaeróbio 6,
força 90, potência 20, mobilidade 60, estabilidade 40, recuperação 300) e os **pesos** são
maiores no VO2máx, na força e no aeróbio (1,5). **Tudo conta**: cada **treino**, os
**hábitos** (30 min de recuperação por dia com 7 h ou mais de sono e 15 por dia com HRV
registada) e os **resultados dos testes** (o último face ao teu melhor; com um só resultado
vale 60). Até haver `D` dias de histórico divide-se pelos dias que há (no mínimo 7).

- **Em cada sessão**: o resumo e a página da sessão (separador Geral) mostram o **radar do
  que treinou** (Z2 → 100 % aeróbio; VO2máx + Z2 → aeróbio e VO2máx; corrida + força →
  aeróbio e força) e a linha **Longevidade** com o que a sessão acrescentou ao índice
  (1 semana · 1 mês · 3 meses) e os eixos onde mais mexeu.
- **No construtor**: o subtítulo mostra, ao mexeres nos blocos, o que o treino
  acrescentaria ao índice se o fizesses hoje.

**A fórmula (separador «Fórmula»)**: mostra a fórmula escrita com os números em vigor e **deixa
editá-la** — o índice recalcula-se logo. **Enter num eixo** muda o **peso** e a **dose de
referência T** (minutos por semana); também se mudam a **mistura com os testes** (0,25 por
omissão) e os **hábitos** (os minutos de recuperação por dia com 7 h+ de sono e por dia com HRV).
**+ Novo parâmetro** acrescenta um eixo teu, de dois tipos: uma **métrica da Saúde** (a média no
período face ao alvo; «melhor mais alto» ou «mais baixo») ou **os minutos de um desporto** (por
semana, face a uma dose de referência), cada um com o seu **peso**; entra no índice e no radar
(até 16 eixos). **Repor a fórmula original** volta à de origem. A fórmula fica na base, na
definição `longevity_formula`, e viaja no backup («Definições»).

### GPX Conversor (construtor de treinos manuais: ciclismo e corrida)

Nos treinos **Manual** de ciclismo e de corrida, o construtor ganha o separador **GPX
Conversor**, que abre uma janela: escolhes um **percurso** (uma rota que já tens, ou
carregas um .gpx novo), a **fórmula** e a precisão, e os **blocos** do treino são gerados
a partir do perfil (nível do rolo, ou inclinação e velocidade da passadeira). O que fazem:

1. **Média móvel da altitude** (20 · 50 · 100 · 200 m): alisa o «tremor» do GPS (com 50 m a
   altitude é a média dos 50 m à volta de cada ponto) para não haver subidas falsas.
2. **Troço mínimo** (100 · 200 · 500 · 1000 m): o percurso parte-se em troços e cada um fica
   com a sua inclinação média. **Troços mais curtos seguem o terreno com mais fidelidade e
   mandam-te mexer no aparelho mais vezes** (mais oscilações manuais); troços seguidos com
   a mesma regulação juntam-se num só.
3. **Fórmula** — passadeira: **Inclinação direta** (inclinação = a do troço; descidas a 0 %) ·
   **Com calibração de 1 %** (menos 1 %, a compensação habitual da falta de ar) ·
   **Esforço constante** (a inclinação e uma velocidade que mantém o esforço, pelo custo
   energético de Minetti: abranda a subir). Rolo: **Linear** (nível = % da FTP plana + ganho
   por 1 % de inclinação) · **Física** (a força para manter a mesma velocidade, elevada a
   0,4 para o nível não saturar).
4. **Velocidade (corrida)** — a minha sugestão é **«Esforço constante»**: a passadeira
   ajusta a velocidade a cada subida e descida e tu só tens de aguentar o mesmo esforço;
   com **«Constante»** corres sempre à mesma velocidade, e com **«Livre»** decides tu (os
   blocos passam a ser por distância e acabam quando a fizeres). A velocidade nunca passa
   do **máximo da passadeira** (Definições → Desportos).

A inclinação respeita o **máximo** da passadeira e o novo **Passo da inclinação** (0,1 · 0,5
· 1 %: de quanto em quanto a tua passadeira sobe), que está em **Definições → Desportos**
(corrida) ao lado da **velocidade máxima** e da **inclinação máxima**; o construtor
arredonda a esse passo (←/→ e valores escritos).

### Exercícios: grupos musculares, disciplinas e listas

A lista de **Exercícios** (ecrã inicial) tem agora:

- Uma tab por modalidade, com **novas**: **Mobilidade**, **Tendões** e **Isométrico**.
  A tab **Longevidade** saiu (a Longevidade é um menu).
- A tab **Grupos Musculares**: os **grupos** (pernas, anca, peito, costas, ombros, braços,
  core, corpo inteiro, mobilidade) e os seus **subgrupos** (quadríceps, isquiotibiais,
  dorsais…). **+ Novo grupo**; Enter abre um grupo, onde mudas o nome, juntas **+ Novo
  subgrupo**, mudas o nome (Enter) ou apagas um subgrupo (Del) e podes apagar o grupo (os
  exercícios passam a «corpo inteiro»).
- Em cada exercício (Enter), **Grupo muscular** e **Subgrupo muscular** são **listas**
  (Enter abre a lista com pesquisa; o subgrupo é um dos do grupo), e **Modalidades** e
  **Material** abrem listas com pesquisa onde marcas o que quiseres (já não são setas).
- **+ Nova disciplina** (botão em baixo, em todas as tabs): dás-lhe um nome e ela **ganha
  logo o seu separador** (e passa a estar entre as modalidades do ginásio). Numa
  disciplina tua, **Apagar esta disciplina** tira o separador (os exercícios só dela e os
  treinos passam para a Força).

### Saúde

O cartão **Saúde** tem:

- **Diário** (de hoje, de ontem, ou qualquer dia com ←/→ na linha "Dia"):
  sono, energia, humor, stress, dores, como te sentiste no treino, peso,
  cintura, tensão, FC em repouso, HRV, passos, o que almoçaste e jantaste,
  a confeção, "comi doces ao almoço?", "comi doces ao jantar?", "comi fora?",
  proteína, álcool, cafés, água e hora de deitar. Cada métrica tem uma
  **nota** (tecla **N**) e o dia tem uma nota livre.
- **Métricas do diário:** cria as tuas com **+ Nova métrica** (em baixo, à direita, como os
  outros botões de adicionar; sim/não, número, escala 1–5, texto, escolha ou hora), liga e
  desliga (**A**) e ordena (←/→). Dá para chegares às
  tuas ~50 e passar delas.
- **Tendências:** o gráfico de qualquer métrica nos últimos 14 a 365 dias.
- **A Saúde está em separadores**: **Análises**, **Diários**, **Tendências**,
  **Métricas**, **Pressão arterial**, **Assistente de saúde** e **os que criares** (ver abaixo).
  (Os **Testes de longevidade** passaram para o menu **Longevidade**.)
- **Análises:** a lista das **colheitas** (uma por data, com o laboratório e o número de
  resultados; **+ Nova análise** em baixo, à direita). **Enter numa colheita** abre-a: todos
  os resultados, por área, cada um com o **valor atual, a tendência e os 3 valores
  anteriores**, e o **comentário do médico** dessa análise (Enter numa linha escreve-o);
  **Comentário geral do médico** é um botão **em baixo**, dentro da colheita (já não está no
  topo da lista). Botões: Catálogo e Editar esta colheita; **Colheitas** volta à lista.
- **Análises clínicas:** uma por data, com laboratório, notas e a caixa do
  **comentário do médico**; os resultados aparecem agrupados por área e exame
  (Hematologia · Hemograma, Bioquímica · Ferro…), com ▲/▼ quando estão fora.
  **Importar do Excel** lê o teu ficheiro (folhas `readings` e
  `ref_parameter`): cria o **catálogo de parâmetros** com a unidade e o
  intervalo de referência tirado do texto do laboratório para um homem da tua
  idade (ex.: Ferritina 50–300 de ">15 anos (homem)"). Valores como
  `4,1 [55,2]` (absoluto e %) e `< 1,1` são entendidos. Voltar a importar
  atualiza os resultados e mantém as notas e o comentário do médico. No
  catálogo podes corrigir à mão um intervalo (fica marcado ✎ e não volta a
  ser mudado pelas importações) — útil para os que o texto não deixa
  calcular, como a HbA1c NGSP e a eTFG. **Evolução de um marcador** mostra o
  mesmo marcador ao longo das análises.
- **Importar dados:** CSV do HRV4Training, JSON do export do Garmin, o
  Excel das análises, o **GarminDB**, ou qualquer CSV com uma coluna de data.
  Do HRV4Training entram a FC e a rMSSD da manhã, os pontos de recuperação,
  AVNN/SDNN/pNN50/LF/HF, as horas de sono, de deitar e de acordar, as tuas
  respostas (qualidade do sono, energia, dores, fadiga, motivação, viagem,
  doença, álcool), o treino (tipo, RPE, duração), o peso e as etiquetas
  personalizadas, e a temperatura das notas (`BodyTemperature:35.6;`). As
  datas do export vêm em ano-dia-mês e às vezes com o ano cortado (`026-…`):
  a Perennia percebe as duas coisas. As colunas reconhecidas (data, rMSSD,
  FC, pontos de recuperação, passos, sono, stress…) vão para as métricas
  certas e ficam marcadas com a origem; as outras ignoram-se, ou criam
  métricas novas se ligares essa opção. Põe os ficheiros na pasta `imports/`
  (dentro da pasta dos dados) ou em Transferências.

### Pressão arterial (várias medições por dia, por período)

Separador **Pressão arterial** da Saúde. Cada medição é um registo: **dia, período, hora, máxima,
mínima, pulsação e nota**. Fazes as que quiseres por dia.

- **+ Medição** abre a janela. O período vem sugerido pela hora (manhã / tarde / noite) e
  escolhe-se numa lista. **«Guardar e mais uma»** grava e deixa a janela pronta para a seguinte
  do mesmo período — é assim que fazes **3 medições de manhã** de seguida. **«Guardar e sair»**
  fecha.
- **Cada período tem a sua média** (3 medições de manhã → um valor da manhã; 3 à noite → um
  valor da noite) e **o dia tem a média diária**. A lista mostra, por dia, a média diária e as
  dos períodos com o número de medições: `126/82 · Manhã 130/84 (3) · Noite 122/80 (3)`.
- **Enter num dia** abre as medições desse dia, por período; Enter numa medição edita-a ou
  apaga-a. **Outro dia…** abre o calendário.
- **Períodos** (botão): muda os nomes ou cria os teus (até 6), por exemplo «Antes do treino».
  Se tirares um período, as medições dele não se perdem: ficam «Sem período».
- **Média diária:** por omissão é a **média das médias dos períodos** (manhã e noite pesam o
  mesmo); podes mudar para a média de todas as medições. Também podes mandar **ignorar a 1.ª
  medição** de cada período com 3 ou mais. Ambas em Definições → Avançado → Saúde e pressão
  arterial (ao guardar, as médias são refeitas).
- **Classificação** (baixa / normal / alta / muito alta) pelos limiares das opções (135/85 por
  omissão, o valor habitual para medições em casa). Não é um diagnóstico.
- No **Diário**, as duas linhas antigas da tensão passaram a **uma linha «Pressão arterial»**
  que mostra a média do dia e abre as medições. A média diária continua a alimentar as
  **Tendências** (métricas «Tensão arterial (máxima)» e «(mínima)»), a longevidade e a AdHoc.
- Os valores que já tinhas no diário passaram, sozinhos, a medições «Sem período».
- **Exportar:** AdHoc Analysis → fonte **Pressão arterial** (uma medição por linha, com a média
  do período e a do dia ao lado), ou `python main.py --adhoc-exportar bp`.

### Separadores da Saúde criados por ti

Como as disciplinas do ginásio: o botão **+ Separador** (em cima, à direita, em quase todos os
separadores da Saúde) pede um nome e cria um separador novo (Fisioterapia, Dentista,
Suplementos…). **Todo o separador tem a componente Notas**: **+ Nota** (data, título e texto);
Enter numa nota edita-a ou apaga-a. **Mudar o nome** e **Apagar separador** (apaga também as
notas, com confirmação) estão em baixo. O módulo próprio de cada separador fica para depois; a
base (separador, notas, backup, e o que o Assistente de saúde lê) já existe.

### O Assistente de saúde

Separador **Assistente de saúde** da Saúde. Conhece as **análises**, a **pressão arterial**, o
**diário** (sono, FC em repouso, HRV, peso, cintura, hábitos), **as notas dos teus separadores**
e **sinais do treino** (carga, forma, FC das sessões). Mostra uma linha por componente, com o
que acha; **Enter abre** cada uma:

| Componente | O que olha |
|---|---|
| **Avaliação geral** | uma linha por componente e o que merece atenção primeiro |
| **Análises clínicas** | o que está fora do intervalo (e se já estava nas anteriores), o que se mexeu muito dentro do intervalo, o que o médico disse |
| **Pressão arterial** | a média recente, por período, a tendência face à base; uma medição isolada muito alta é sempre assinalada |
| **Recuperação e sono** | sono, FC em repouso e HRV recentes face à tua base; dores, stress, energia |
| **Corpo** | peso e cintura face à base |
| **Hábitos diários** | álcool por semana, doces, refeições fora, água, passos, cafés |
| **Sinais do treino** | carga crónica, fadiga, forma, dias seguidos, FC máxima vista |
| **Os teus separadores** | as notas mais recentes de cada separador teu |

Compara o **período recente** (14 dias) com o **de base** (90 dias); as janelas e todos os
limiares estão em Definições → Avançado → Saúde e pressão arterial. Numa colheita, o botão
**Assistente de saúde** abre a leitura dessa colheita. **O que existia para o médico fica como
estava** (comentários por resultado e comentário geral): o assistente é mais uma leitura, não a
substitui. **Não faz diagnósticos**; diz quando é caso para falar com um médico.

### O Treinador

Cartão **Treinador** no ecrã inicial. Tem cinco separadores:

- **Hoje** — o que fazer hoje (descanso, fácil, qualidade…) a partir da tua forma, da carga de
  ontem, da recuperação (sono, FC em repouso, HRV, dores), do que está no calendário e do teu
  eixo mais fraco da longevidade; e os **comportamentos** a cuidar. **«Abrir este treino no
  construtor»** programa-o.
- **Eventos** — planear um evento numa data. **+ Evento de resistência** ou **+ Evento de
  força** abrem as perguntas do Treinador:
  - *Resistência* (ciclismo, corrida, remo, natação): nome, data, prioridade, **a rota (.gpx)**
    — escolhida numa lista das rotas importadas, preenche a distância e a subida —, a
    **velocidade média pretendida**, a **hora de partida**, a **disponibilidade** (minutos por
    dia de semana e por dia de fim de semana), **férias de/até** (um período em que podes
    treinar mais; sem férias fica limitado ao dia a dia e ao fim de semana) e notas.
  - *Força*: nome, data, prioridade, **limite de tempo** (ex.: 5 min), sessões por semana e os
    **objetivos** — cada um com o exercício (lista dos teus exercícios, ou escrito), a unidade
    (repetições, kg, segundos, metros), o objetivo e **o que fazes hoje**. Serve para «200
    flexões e 50 elevações em 5 min» e para «flexões, elevações, peso morto, agachamento e
    saco de areia».
  - **Enter num evento** abre o plano: quanto falta, **se é realista** (na bicicleta: a potência
    média que a velocidade pede face à tua FTP e ao que se aguenta nessa duração; o teu treino
    mais longo face ao evento; na força: a progressão por semana de cada objetivo e o ritmo em
    repetições por minuto), a disponibilidade, as **fases** (base → construção → específica →
    afinação, com datas), a **alimentação e hidratação** (hidratos e líquidos por hora, totais,
    e as refeições acertadas pela hora de partida) e as **perguntas** sobre o que ficou por
    dizer. **«Pôr no calendário»** agenda as sessões propostas (dentro dos minutos de cada dia;
    nas férias há mais dias); voltar a pôr substitui as anteriores; **«Tirar do calendário»**
    desfaz. Apagar o evento tira também as sessões dele.
- **Desafios** — todos os teus desafios com o que o Treinador acha. **Enter** (ou o botão
  **Treinador** no detalhe de um desafio) abre o feedback: onde estás, **longe ou perto**, o
  que falta por semana, e a pergunta **«Quão importante é este desafio para ti?»** (lista:
  baixa / média / alta). Com a resposta, **ajusta os treinos**: propõe as sessões por semana e
  **«Pôr no calendário»** agenda-as (prioridade alta: 4 semanas; média: 2; baixa: não mexe).
- **Longevidade** — o **caminho para a longevidade**: o índice, os teus pontos fortes, as
  **fraquezas** (eixos abaixo de 50) e as **fases** propostas (4 semanas cada, duas fraquezas de
  cada vez: mais aeróbio, força, VO2máx…), com o que fazer em cada uma; a primeira fase pode ir
  para o calendário. O mesmo abre-se no menu Longevidade (**Treinador: caminho para a
  longevidade**).
- **Programar treino** — escolhes o **desporto** (ciclismo, corrida, remo), o **foco**
  (recuperação, Z2, tempo, sweet spot, limiar, VO2máx, anaeróbio) e a **duração**; o Treinador
  mostra o treino que faria e o feedback dele, e **«Abrir no construtor»** abre-o no construtor
  de treinos, por guardar, para ajustares. Se estiveres cansado, encurta o bloco principal.

**Feedback a um treino construído.** No construtor de treinos, o botão **Treinador** dá o
feedback ao treino que lá está, **tendo em conta a tua forma atual**: a carga face à carga típica
das tuas sessões, como ficas no dia seguinte (TSB), a duração face ao teu treino mais longo, a
recuperação, os minutos em Z4 e Z5, a falta de aquecimento, blocos fortes seguidos. Um treino
pesado demais para a forma que tens é apanhado, com uma sugestão concreta e o botão **«Aplicar a
versão mais leve»** (tira repetições até a carga descer; fica por guardar). **Só aparece depois
de pedires**; a partir daí o veredicto fica **ao vivo** na linha por baixo do título e
atualiza-se a cada alteração (desliga-se em Definições → Avançado → «Construtor: feedback do
Treinador ao vivo»). O Treinador programa treinos de ciclismo, corrida e remo; para a força,
planeia as sessões no calendário (ainda não preenche o construtor de força).

### Aconselhamento: regras, LLM local ou agente online

O Treinador e o Assistente de saúde têm, no topo, a linha **Aconselhamento** (lista):

| Modo | O que é | Estado |
|---|---|---|
| **Regras da Perennia (offline)** | as regras descritas acima, com os limiares das opções; sem rede e sem IA | **funciona já** |
| **LLM local (offline)** | um modelo a correr no teu computador (Ollama, LM Studio, llama.cpp); nada sai da máquina | preparado, **por ligar** |
| **Agente online** | Claude, ChatGPT, Gemini ou outro compatível; **os dados do pedido seriam partilhados com o fornecedor** | preparado, **por ligar** |

Nos dois modos com LLM, **antes de qualquer envio** vês: os **tokens do pedido** (≈), se **cabe
na janela do modelo local** ou o **custo máximo** no online, os **dados partilhados** (as
categorias autorizadas; **nada do Strava**), e **«Ver o que seria enviado»** mostra o pedido
inteiro, os tokens por partes e deixa desligar categorias. Podes juntar **a tua pergunta**.
Como as chamadas ainda não estão ativas, o botão Enviar fica desligado e o ecrã mostra a leitura
das regras. A escolha guarda-se por figura.

- **Chave do fornecedor: só por variável de ambiente** — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `GEMINI_API_KEY` ou `PERENNIA_AI_API_KEY` (outro). Nunca se escreve na aplicação nem fica na
  base; o ecrã só diz «definida» ou «em falta».
- **LLM local:** o endereço (por omissão `http://127.0.0.1:11434`; ou a variável
  `PERENNIA_LLM_URL`) e o nome do modelo estão em Definições → Avançado. Se o endereço não for
  deste computador, o ecrã avisa que isso já não seria offline.

### Sincronização (GarminDB)

Em **Backups e Sincronização → Sincronização** (o botão da barra do topo; a Sincronização já
não está nas Definições) trazes os teus dados de uma fonte para a
base da Perennia. As opções gravam-se logo. Cada fonte tem o seu separador:

- **Saúde (.csv)** — o diário de saúde **por data**: uma linha por dia, a coluna `data`, uma
  coluna por métrica do diário **com o nome que ela tem na Perennia** (número, sim/não, escala,
  hora, escolha ou texto) e a `nota` do dia. **Descarregar o modelo (.csv)** dá o cabeçalho e
  uma linha de exemplo; **Exportar o diário (.csv)** dá o que já tens, no mesmo formato.
  Colunas desconhecidas ignoram-se e os valores inválidos contam-se (não param a importação).
  Também por `--csv-modelo saude`, `--csv-exportar saude` e `--importar saude ficheiro.csv`.
- **HRV4Training (.csv)** — o export da app (Definições → Exportar
  medições). Entra no diário da Saúde.
- **Análises (.csv)** — uma linha por resultado: data, análise, valor (e,
  se quiseres, unidade, mínimo, máximo, laboratório), separador «,» ou «;»,
  datas AAAA-MM-DD ou DD/MM/AAAA. Também serve o Excel das análises.
- **CSV** — **artigos, exercícios, grupos e subgrupos musculares, disciplinas, testes de
  aptidão** e os **tipos de material**: para cada conjunto, **Descarregar o modelo
  (.csv)** (o cabeçalho e uma linha de exemplo), **Exportar o que tenho (.csv)** e
  **importar** um .csv preenchido (a Perennia descobre o conjunto pelo cabeçalho; cria o que
  falta e atualiza o que já existe, pelo nome, sem duplicar). Os ficheiros são UTF-8
  (com BOM, o Excel abre-os bem) com `;` a separar colunas (na importação aceita-se também
  `,` e tab) e `|` a separar listas dentro de uma célula (`Isométrico|Força`). Os grupos,
  subgrupos, modalidades (disciplinas) e material que não existirem **são criados**.
  Gravam-se em Transferências. Os tipos de material são só de consulta.
- **Upload manual** — **uma atividade** de cada vez, vinda do teu
  computador: um **.fit** (relógios Garmin, Wahoo, Zwift…) ou um **.tcx**.
  Escolhe-o na lista (a Perennia procura em `imports/`, Transferências e
  Documentos) ou **arrasta-o para a janela**. A Perennia lê-o e mostra, numa
  janela, o **nome**, o **desporto** (que podes mudar com ←/→), a data, o
  tempo total e em movimento, a distância, a subida, a FC, a potência, as
  calorias e o n.º de voltas; **Fazer upload** guarda a atividade no
  Histórico desse desporto (e conta para a forma e a fadiga), **Cancelar**
  descarta. Carregar o mesmo ficheiro outra vez não duplica. Um ficheiro
  estragado ou incompleto dá uma mensagem de erro e não guarda nada.
- **TrainingPeaks (.csv de atividades)** — no TrainingPeaks web:
  Calendário → Exportar → Workouts. As atividades entram no Histórico com a
  **TSS do TrainingPeaks** e contam para a forma e a fadiga. Os treinos só
  planeados (sem tempo feito) ignoram-se; importar outra vez não duplica.

Nos três, a lista mostra os ficheiros que a Perennia encontra em
Transferências e na pasta `imports/` (ou arrasta o ficheiro para a janela);
Enter importa.

E o [GarminDB](https://github.com/tcgoetz/GarminDB), que descarrega os dados do
Garmin Connect para bases locais (`~/HealthData/DBs`). A Perennia **lê essas
bases** e, se o GarminDB estiver instalado, corre-o por ti. A tua
palavra-passe do Garmin fica só na configuração do GarminDB
(`~/.GarminDb/GarminConnectConfig.json`); a Perennia nunca a lê.

1. Instala e configura o GarminDB: `pip install garmindb`, e o ficheiro de
   configuração com o teu utilizador.
2. Escolhe as opções (ficam guardadas):
   - **Período**:
     - *Só o mais recente* — `--latest`: o GarminDB traz só o que falta desde
       o último dia que já tem; a Perennia importa a partir da última
       sincronização.
     - *Todo o histórico* — sem `--latest`: desde as datas de início da
       configuração do GarminDB (`data.<dado>_start_date`; nas atividades,
       as últimas `download_all_activities`).
     - *Um intervalo de datas* — **Desde** e **Até** (Enter abre o
       **seletor de datas**; ←/→ também muda um dia, Shift um mês). Com **Escrever as datas na configuração** ligado, as datas vão
       para `data.<dado>_start_date` e `data.<dado>_end_date` (formato
       MM/DD/AAAA) do GarminDB, com uma cópia `GarminConnectConfig.json.bak`
       antes; a Perennia importa só esse intervalo. As atividades, no
       GarminDB, contam-se por número e não por data: a Perennia filtra-as
       pelas datas ao importar.
   - **Dados**: Atividades (`--activities`), Monitorização diária
     (`--monitoring`: passos, stress, Body Battery…), FC em repouso
     (`--rhr`), HRV (`--hrv`), Sono (`--sleep`), Peso (`--weight`). Todos
     juntos dá `--all`.
   - **Passos do GarminDB**: descarregar do Garmin Connect (`--download`),
     copiar de um relógio ligado por USB (`--copy`), importar para as bases
     do GarminDB (`--import`), analisar (`--analyze`) e voltar a descarregar
     o que já existe (`--overwrite`).
   - **Pastas**: a das bases (por omissão `~/HealthData/DBs`) e a da
     configuração (por omissão `~/.GarminDb`; outra pasta vai como `-f`).
   - A linha **Comando** mostra o comando exato que vai correr.
3. **Sincronizar agora** (o botão principal, ou Ctrl+S) corre o GarminDB e
   importa; **Só importar** lê o que já está nas bases, sem correr o
   GarminDB. Sem o GarminDB instalado, Sincronizar agora também só importa.
4. Manutenção: **Cópia de segurança das bases** (`--backup`, um `.zip` em
   `HealthData/Backups`) e **Reconstruir as bases** (`--rebuild_db`, quando o
   GarminDB o pedir numa mudança de versão). As duas perguntam antes.

Entram na **Saúde**: passos, FC em repouso, FC mínima e máxima do dia, stress
médio, Body Battery (máxima, mínima, carregada), SpO2, respiração, calorias
ativas, distância, andares, minutos moderados e vigorosos, sono (total,
profundo, leve, REM, acordado, pontuação, stress no sono), HRV da noite e
semanal com o estado, e o peso. Ficam marcados com a origem "garmin";
voltar a importar atualiza o mesmo dia em vez de duplicar.

Entram também as **atividades** (`garmin_activities.db`): aparecem no fim
do separador **Histórico** de cada desporto, marcadas «Garmin», com tempo,
distância, FC, subida e carga. As distâncias são convertidas para km e m
quando o GarminDB está em milhas e pés (`settings.metric = false`).
Importar outra vez não as duplica.

A Saúde (**Importar dados → Sincronização (GarminDB)**) abre o mesmo ecrã.

### Backups e Sincronização (botão na barra do topo)

Tudo o que a Perennia guarda — **mesmo tudo** — sai num só ficheiro `.zip`,
e volta a entrar com um clique. Abre-se no botão **Backups e Sincronização** da barra do
topo (ao lado de Dispositivos e Definições), em qualquer ecrã fora de uma
sessão. Tem três separadores — **Exportar**, **Repor** e **Sincronização** (esta última é a
secção acima):

**Exportar** — marca **Tudo (exportação completa)** ou só as componentes que
quiseres (Enter ou ←/→ marca e desmarca) e carrega em **Exportar** (ou
Ctrl+S). O ficheiro fica na pasta `backups` dos teus dados, com a data no
nome: `perennia-backup_2026-11-04_16-30-12_completo.zip` (ou `_parcial`).
Copia-o para uma pen ou para a nuvem.

| Componente | O que leva |
|---|---|
| Perfil do atleta | nome, peso, FTP e limiares |
| Definições | unidades, tema, zonas, Geral (os passos seguintes do treino), **Avançado** (as opções afináveis: pausa automática, tolerâncias, tokens do agente, Análise AdHoc…), as **vistas guardadas** da AdHoc Analysis, os **períodos da pressão arterial**, o modo de **aconselhamento** do Treinador e do Assistente de saúde e a **importância dos desafios**, a contagem antes de começar, os bips, limites Não ERG dos aparelhos, a fórmula da Longevidade, preferências… |
| Atalhos de teclado | as teclas que mudaste (volta, pausa, terminar, começar sem contagem e saltar bloco são as mesmas em todos os desportos). Um backup antigo, com um atalho por desporto, **volta já unificado** |
| Ecrã da sessão | disposição do ecrã e métricas de sessão disponíveis em cada desporto |
| Aparelhos | dispositivos emparelhados e calibrações |
| Rotas | os .gpx: pontos, perfil, subidas |
| Segmentos | os da Perennia e os do Strava |
| Treinos | as listas de treinos de todos os desportos (com definição, objetivos, planos de voltas e as cópias das sessões) |
| Ginásio e exercícios | exercícios, treinos de força e as suas estruturas |
| Inventário de artigos | bicicletas, sapatilhas, peças, com data e preço de compra |
| Histórico de sessões | todas as sessões, com amostras, voltas, tempos em subidas e segmentos, jogos, importadas (Garmin, TrainingPeaks, com a TSS) — e os `.fit` |
| Análises e feedback | o feedback e a análise de cada sessão, picos e curvas de potência |
| Desafios | desafios e tentativas |
| Testes de aptidão | testes, resultados, testes de FTP |
| Saúde | valores diários (HRV4Training incluído), métricas, análises clínicas com os comentários do médico, **as medições da pressão arterial** e **os separadores que criaste, com as notas** |
| Calendário | treinos planeados, notas do dia e **os eventos do Treinador** (com as respostas) |
| Ficheiros | treinos exportados, importações, a pasta `workouts` |
| Ligações externas (credenciais) | Strava (chaves e sessão) e GarminDB (pastas) — **só se pedires** |

As credenciais ficam fora por omissão: quem tiver o ficheiro teria as tuas
chaves do Strava. Liga «Ligações externas» se o backup for só para ti.

**Dentro do .zip, tudo segmentado:** uma pasta por componente
(`01-perfil/`, `06-rotas/`, `11-sessoes/`…), um ficheiro `.jsonl` por tabela
(um registo por linha, em JSON — dá para abrir em qualquer editor), os `.fit`
em `11-sessoes/ficheiros/`, um `manifest.json` com o que lá está (data,
versão, quantos registos de cada tabela) e um `LEIA-ME.txt`.

**Repor** — a lista mostra os backups que a Perennia encontra na pasta
`backups`, em Transferências, Documentos e no Ambiente de trabalho. Para
**trazer um backup** de outro sítio (o «upload»): **arrasta o .zip para a
janela da Perennia**, em qualquer ecrã, ou põe-no numa dessas pastas.
Enter abre a janela da reposição:

- marca as componentes a repor (por omissão, todas as que o ficheiro tem);
- **Como repor**: **Substituir** (os dados dessas componentes passam a ser
  os do backup — o normal para mudar de computador ou voltar atrás) ou
  **Juntar** (acrescenta o que falta e deixa o resto: juntar duas vezes o
  mesmo backup não duplica nada);
- **Repor** → confirma.

O resto é automático: **antes de mexer, a Perennia guarda um backup do que
tens agora** (`perennia-antes-de-repor_….zip`, também na lista), repõe tudo
numa só transação (se algo falhar, nada fica a meio), põe os `.fit` na pasta
de dados e corrige os caminhos, arruma as referências que ficaram sem
destino (uma sessão de uma rota que não veio fica sem rota), e volta ao ecrã
inicial já com as definições repostas (língua, unidades, tema, atalhos). Del
apaga um ficheiro de backup da lista (com confirmação). Durante uma sessão
não se repõe nada.

**Pela linha de comandos** (sem abrir a janela, útil para backups
automáticos):

```bash
python main.py --backup
```

```bash
python main.py --backup /media/pen --componentes rotas,segmentos,sessoes
```

```bash
python main.py --restore perennia-backup_2026-11-04_16-30-12_completo.zip
```

```bash
python main.py --restore backup.zip --modo juntar --componentes treinos
```

`--credenciais` inclui as ligações externas no backup; `--data-dir` escolhe a
pasta de dados, como de costume. Os nomes das componentes são: perfil,
definicoes, atalhos, ecra, aparelhos, rotas, segmentos, treinos, ginasio,
inventario, sessoes, analises, desafios, testes, saude, calendario,
ficheiros, ligacoes.

**Importar pela linha de comandos** (as mesmas importações da
Sincronização, sem abrir a janela):

```bash
python main.py --importar trainingpeaks ~/Transferências/workouts.csv
```

```bash
python main.py --importar hrv4training ~/Transferências/MyMeasurements.csv
```

```bash
python main.py --importar analises ~/Transferências/analises.csv
```

```bash
python main.py --importar atividade ~/Transferências/corrida.fit
```

```bash
python main.py --importar csv ~/Transferências/perennia_exercicios.csv
```

(`atividade` lê um `.fit` ou `.tcx` e guarda-o no desporto respetivo, como o
Upload manual. `csv` importa um .csv de artigos, exercícios, grupos musculares,
disciplinas ou testes — descobre o conjunto pelo cabeçalho.)

**Modelos e exportações em CSV** (os mesmos da Sincronização → CSV; gravam em
Transferências, ou na pasta de `--destino`):

```bash
python main.py --csv-modelo exercicios
```

```bash
python main.py --csv-exportar grupos --destino ~/Documentos
```

O diário de saúde tem o seu conjunto, `saude` (o `--importar saude` lê o .csv por data):

```bash
python main.py --csv-modelo saude
```

```bash
python main.py --importar saude ~/Transferências/perennia_saude.csv
```

Os conjuntos são `artigos`, `exercicios`, `grupos`, `disciplinas`, `testes` e `material`.

**A Análise AdHoc, em .csv** (as fontes `sessions`, `sets`, `daily`, `labs`, `tests`, `bp`; usa o separador
e o decimal das Definições, se não os deres; grava na pasta `exports`, ou em `--destino`):

```bash
python main.py --adhoc-exportar sessions --destino ~/Documentos --nome minhas-sessoes --separador ";"
python main.py --adhoc-exportar daily --vista "Peso por mês"
```

### Rotas (menu do ecrã inicial)

O **único sítio onde se carregam ficheiros .gpx**. O ciclismo e a corrida já
não carregam rotas: na janela da sessão escolhes uma das rotas que já
estão aqui (não há distinção de modalidade — a mesma rota serve as duas).

- **A lista** — cada rota com a distância, a subida e **quantas vezes já a
  fizeste** («feita 3× (2× ciclismo · 1× corrida)»); à direita, o **perfil
  de altimetria** da rota escolhida (cores pela inclinação: azul a descer,
  verde plano, amarelo 2–5 %, laranja 5–8 %, vermelho acima) com os
  segmentos por cima. **+ Carregar .gpx** em cima, à direita. F favorita,
  Del apaga (com confirmação; as sessões ficam no histórico).
- **A rota** (Enter) — o perfil em cima; por baixo a distância, a subida e
  a descida, as altitudes, as vezes feita, o melhor tempo, as subidas
  detetadas (com a classificação), os **segmentos** (Perennia e Strava, com
  o melhor tempo), as últimas sessões feitas nela (Enter abre a análise) e
  os botões **Começar no ciclismo** · **Começar na corrida**.

### Segmentos (menu do ecrã inicial)

Continuas a ter os segmentos do Strava, e passas a poder **definir os teus**:

1. Carrega a rota no menu **Rotas**.
2. Em **Segmentos → + Novo segmento** (ou na ficha da rota): escolhe a rota
   (←/→), o nome, o **km de início** e o **km de fim** — ou, em «Fim por»,
   a **distância a percorrer**. A janela mostra o perfil com o segmento
   marcado, a inclinação média e a subida.
3. Os segmentos de uma rota **entram sozinhos nas sessões** feitas nela
   (ciclismo e corrida): ao passar o km de início começa a contar, no km de
   fim aparece o tempo e a comparação com o teu melhor, e o tempo fica
   guardado.

O menu tem três separadores — **Visão geral**, **Perennia**, **Strava** —
com os segmentos agrupados por rota, o melhor tempo e quantas vezes os
fizeste; à direita, o perfil da rota com o segmento escolhido. Enter abre o
segmento: todos os tempos (o melhor primeiro, com o desporto e a sessão) e,
nos da Perennia, Editar e Apagar.

### Exportar um treino (todos os desportos)

Na ficha de qualquer treino (a que se abre ao escolhê-lo na Lista de
treinos) há, em baixo à direita, **Exportar**. Abre uma janela onde dás o
**nome do ficheiro** e escolhes o **formato**; **OK** grava-o na pasta
**Transferências** (Downloads) e a mensagem do topo diz onde ficou;
**Cancelar** (ou Esc) volta à ficha do treino. Um ficheiro que já exista
não é substituído: o novo leva «_2», «_3»…

| Desporto | Formatos |
|---|---|
| Ciclismo | `.zwo` (Zwift, TrainerRoad, MyWhoosh), `.erg` (watts, com a tua FTP), `.mrc` (% da FTP), `.fit` (Garmin/Wahoo), `.json`, `.txt` |
| Remo | `.fit` (treino estruturado), `.json`, `.txt` |
| Corrida, natação, ginásio | `.json` (o treino da Perennia, com blocos e objetivos) e `.txt` (para ler ou imprimir) |

A ficha do treino ocupa agora a largura toda: já não há a secção «Sobre
este treino»; o que lá estava (objetivo, blocos e alvos) tem o espaço todo.
Na **natação** a ficha não tem «Configurar sessão de treino» (só Editar
objetivos, Abrir no construtor e Exportar).

### Treinos do computador (todos os desportos menos o Ginásio)

Na **Sessão de treino** há agora **Do computador**, e nas listas de treinos
**+ Carregar do computador**. Lê `.zwo`, `.fit` (treinos Garmin/Wahoo e os
que a Perennia exporta) e, no ciclismo, `.mrc`/`.erg`, das pastas
`workouts` (ao lado da aplicação), Transferências e Documentos.

Ao escolher um ficheiro, a Perennia pergunta **«Guardar na lista de
treinos?»** — para a lista não ir enchendo com treinos que só se fazem uma
vez:

- **Guardar na lista** — fica na lista de treinos, como os outros;
- **Só para esta sessão** — não aparece na lista.

Se o mesmo treino (nome e passos) já estiver na lista, usa-se esse, sem
duplicar. A natação não tem sessão na Perennia: o treino vai para a lista.

**Cada sessão guarda a sua cópia do treino.** Quando uma sessão começa com
um treino, a Perennia guarda uma cópia (passos, ERG/manual, tolerâncias,
velocidades, objetivos) só para essa sessão. A análise e o feedback usam a
cópia — veem o treino como foi feito, mesmo que o original seja editado ou
apagado — e dizem o estado do treino: **Na lista de treinos**, **Apagado da
lista · a cópia ficou com a sessão** ou **Carregado do computador · não
guardado na lista**. Apagar um treino da lista (Del, com confirmação) já não
apaga os passos: o treino fica marcado como apagado.

### Treinos: voltas e distância

- **Voltas só no modo Livre.** Numa sessão com um treino (carregado da
  lista ou do computador, em qualquer desporto), **cada bloco é uma volta**
  e o **L** não cria voltas (aparece um aviso).
- **Corrida na passadeira (treino manual)**: com a velocidade de cada bloco,
  a **distância é calculada sozinha** (velocidade × tempo) e não se mexe; o
  bloco passa a ser por tempo, e a distância de cada bloco e a do treino
  ajustam-se quando mudas a velocidade. Na sessão, a velocidade de cada
  bloco põe-se sozinha e fica presa (T e +/− avisam).

### FC simulada: SEM HARDWARE - Banda cardíaca

Em **Dispositivos** há **SEM HARDWARE - Banda cardíaca**: uma banda de peito
simulada que manda só a FC. A FC **segue o esforço** da sessão em curso —
a potência no ciclismo e no remo, a velocidade na corrida — com o atraso
de um coração verdadeiro (sobe mais depressa do que desce). Ganha à FC do
trainer simulado. Serve todos os desportos, para testar sem cinta.

### Strava: segmentos das tuas rotas e os teus PR

1. Em <https://www.strava.com/settings/api> cria uma aplicação: nome
   "Perennia", site `http://localhost`, **Authorization Callback Domain:
   `localhost`**.
2. Em **Definições → Strava** escreve o **Client ID** e o **Client Secret**
   (ficam só neste computador) e escolhe **Autorizar no browser**. Aceita na
   página do Strava; a janela diz "Strava ligado" e podes fechá-la.
3. Na janela da sessão (linha **Segmentos do Strava**, Enter) ou na rota
   (**Rotas → a rota → Segmentos do Strava → Atualizar do Strava**): a Perennia procura os segmentos ao longo da rota, fica com os
   que a rota percorre no mesmo sentido, e vai buscar o teu **PR** e o número
   de esforços de cada um.

Durante o passeio, ao entrares num segmento aparece a placa com a distância,
a inclinação e o teu PR, e o quadro da direita compara-te com o PR no mesmo
ponto (como se o PR fosse a ritmo constante) e projeta o tempo final. No fim
vês o tempo e a diferença; o melhor tempo **na Perennia** fica guardado para
a próxima vez.

Limites que vêm do Strava, não da Perennia: a classificação completa (o
top 15) **deixou de existir na API em 2020** — só se vê o teu PR e o KOM; o
Strava aceita ~100 pedidos a cada 15 minutos (uma rota longa usa umas
dezenas); e um passeio no rolo não conta para o Strava. Pelo acordo da API,
**nada do Strava vai para o agente de IA**: os ecrãs do Strava não têm F1/F2
e as linhas do Strava são retiradas de qualquer resumo.

### Remo

O cartão **Remo** do ecrã inicial tem, em Treinar: **Sessão de treino**
(livre — com voltas na tecla L — ou carregar um treino, sempre pela janela
da sessão, onde também se emparelha a máquina), **Challenge**, **Desafios** e
**Testes** (os campos do ecrã estão em Definições → Ecrã da sessão); e os outros separadores (treinos — sete que vêm com a
aplicação —, construtor, histórico, estatísticas). A **FTP do remo** está em
**Definições → Atleta**.

**A máquina.** A Domyos Rowing 500B liga-se por Bluetooth (não tem ANT+), em
**Dispositivos → Procurar Bluetooth**: aparece marcada REMO, pelo nome
(DOMYOS-ROW…) ou pelo serviço, e Enter liga-a ali mesmo; uma máquina FTMS
(como o Concept2 PM5) também é reconhecida. **Dispositivos → Máquina de remo
simulada** serve para experimentares sem a ligar.

**Estatísticas do remo.** Cada recorde (melhor ritmo aos 500 m, melhor ritmo
médio, maior distância, sessão mais longa, potência média e máxima, voga)
diz em que sessão foi feito; Enter abre essa sessão. Na corrida e na
natação é igual. A FC vem da banda
ou do relógio (o Swim 2 por ANT+), ou da própria máquina se não houver outra.

**A sessão** mostra oito quadrados configuráveis (ritmo /500 m, voga,
potência, distância, tempo, FC, resistência, ritmo médio; também potência
média, remadas, zona de FC, kcal, W/kg, metros por remada, volta atual e
projeção aos 2 km). **+ / −** mudam o nível de resistência (1–15), **L**
marca volta, **P** pausa (e pausa sozinha quando paras de remar), **Esc**
termina e grava um `.fit` de remo indoor.

**As voltas, sempre no mesmo sítio.** Como no ciclismo, à direita da
sessão (remo, corrida e natação) há um painel só para as voltas: em cima a
volta em curso (tempo, distância, ritmo, potência ou FC média, voga ou
piscinas), por baixo as voltas já feitas, da mais recente para a mais
antiga. O painel pisca quando marcas uma volta.

**Treinos.** Passos por **tempo** (mínimo 10 s) ou por **distância** (mínimo
50 m), com alvo de **ritmo /500 m**, **potência** (% da FTP do remo, também
mostrada em ritmo) ou **voga**, e o **nível de resistência** que a aplicação
põe sozinha no início de cada passo. "Repetir os 2 últimos passos × N" faz
os blocos de intervalos. Exporta para `.fit` de treino (desporto remo).

**A potência.** A Domyos não mede watts: a Perennia calcula-os do ritmo pela
fórmula da Concept2 (P = 2,80 / (s/m)³), que é a que todos os remos indoor
usam. A **FTP do remo** começa em 80 % da do ciclismo; ajusta-a com ←/→ ou faz
o teste de 2000 m (fica 85 % da potência média).

**Challenge.** Os jogos do ciclismo com a tua FTP do remo (desafio adaptativo
com nível próprio, Zone Hero, Power Ladder, Aquecimento, Cabo de guerra) e a
**Regata**: 500 m, 1, 2 ou 5 km contra bots ao teu nível; o quadro mostra a
que distância estás de cada um.

**No Conditioning** há uma volta de **Remo**: com a máquina ligada, a
distância, o ritmo, a voga e a resistência enchem-se sozinhos; sem ela,
escreves a distância que o visor mostra e o ritmo calcula-se.

O remo conta para a sequência de dias, para a carga (fitness, fadiga e
forma: pela potência ou, sem ela, pela FC), para o tempo em zona e para as
estatísticas gerais.

### O agente de IA (preparado, por ligar)

(O **Treinador** e o **Assistente de saúde** usam o mesmo mecanismo de pedido e de tokens: ver
«Aconselhamento: regras, LLM local ou agente online».)

Em quase todos os ecrãs (não durante as sessões), **F1** pede o **resumo
desta página** e **F2** o **resumo contextualizado**. O primeiro leva o que
está no ecrã (linhas, valores, classificações, dados do gráfico). O segundo
junta um retrato teu: carga e forma, FTP estimada, progressão da força,
médias do diário dos últimos 28 dias (com as notas), análises fora do
intervalo com o comentário do médico, e os testes.

O agente ainda não está ligado: o ecrã mostra **exatamente o que lhe seria
enviado**, para veres a privacidade antes de o ligar. Ficam já estas regras:
só saem as categorias autorizadas; **nada do Strava** (o acordo da API do
Strava proíbe usar esses dados em IA); e o agente sugere, não diagnostica.

**Quantos tokens vai gastar — antes de enviar.** O ecrã do agente mostra, por cima do pedido, uma
**estimativa dos tokens**: o total, o peso de cada parte (instruções, a página, cada categoria do
contexto), o máximo que a resposta pode ter e, se puseres os preços, **o custo** (do pedido e o pior
caso com a resposta no limite). Acima do limite que definires aparece um **aviso** — e podes tirar
categorias do contexto para o pedido encolher. A conta faz-se **no teu computador, sem rede e sem
custo**: caracteres ÷ caracteres por token (3,5 por omissão, que em português e com JSON é uma boa
aproximação). É uma **estimativa** (diz «≈»); o número exato só o fornecedor dá — a Anthropic tem um
pedido gratuito, `count_tokens`, que fica para quando o agente estiver ligado. As opções (caracteres
por token, máximo da resposta, limite do aviso, preços por milhão de tokens e a moeda) estão em
Definições → Avançado → Agente de IA e tokens.

### Se a aplicação fechar a meio de uma sessão

A sessão vai sendo gravada enquanto treinas: no ciclismo as amostras e um
ponto de recuperação a cada 5 segundos (e a cada volta), na força cada série
logo que termina e a FC a cada 5 segundos.

Se a aplicação fechar por um erro, se o computador se desligar ou se faltar
a luz, ao abrir de novo aparece **Sessão interrompida**, com o desporto, a
hora, o tempo e a distância (ou as séries). Escolhes:

- **Retomar a sessão:** volta ao ponto onde estava — mesmo tempo, distância,
  posição na rota, volta, passo do treino e intensidade, médias, zonas e
  traço de potência e FC. Fica em pausa e continua quando voltares a pedalar
  (na força, quando tirares a pausa). Perdem-se no máximo os últimos 5
  segundos.
- **Guardar como está:** termina com o que ficou gravado, escreve o `.fit` e
  conta para as estatísticas.
- **Descartar.**

Duas notas: uma subida que estivesse a meio já não conta para a classificação
dessa subida; e uma fuga retomada continua, mas fica fora da classificação
(como numa pausa). Fechar a janela normalmente continua a terminar e a
gravar a sessão, como até aqui.

### Balanço esquerda/direita

Aparece no ecrã da sessão como **Balanço E/D**, em percentagem de cada perna,
por exemplo `49 / 51`, com média de 3 segundos para não saltar a cada
pedalada. Há também a métrica **Balanço E/D médio** (da sessão), que podes
pôr no ecrã em Definições → Desportos → Disposição do ecrã de sessão. O balanço fica:

- no resumo da sessão, e em cada subida (ao lado da potência, do pulso e da
  cadência);
- em cada volta e em cada subida, na base de dados;
- no `.fit`, segundo a norma (segundo a segundo, por volta e na sessão), para
  o Garmin Connect, o Strava ou o Golden Cheetah o lerem;
- nas Estatísticas, com o gráfico da evolução sessão a sessão.

**Precisa de um medidor que o meça.** Só os medidores de dois lados (pedais
Assioma Duo, Favero, Garmin Rally, ou pedaleiros de duplo lado) medem cada
perna. Os de um só lado (Stages, 4iiii só esquerdo, Assioma Uno) estimam o
total a partir de uma perna e não dão balanço. A maioria dos rolos não o
mede: o protocolo de controlo do rolo (FTMS) nem tem esse campo. A
aplicação lê o balanço pelo perfil de potência, tanto por Bluetooth como por
ANT+. Liga o medidor de potência em Dispositivos, além do rolo: o medidor
tem prioridade para potência, cadência e balanço, e o rolo continua a fazer
a resistência. Sem medidor de dois lados, a métrica mostra `—`.

### Eficácia do binário e suavidade da pedalada

Com pedais de duplo lado por ANT+ (Assioma Duo, Favero, Garmin Rally) a
aplicação mostra mais duas métricas, por perna:

- **Eficácia binário E/D**, por exemplo `78 / 80 %`: quanto da força
  aplicada empurra o pedal para a frente. O resto vai contra a pedalada da
  outra perna.
- **Suavidade E/D**, por exemplo `22 / 24 %`: quão regular é a força ao
  longo da volta. Alguns medidores só dão um valor combinado, e aparece
  esse.

Ficam no ecrã por omissão, com as médias da sessão disponíveis em
Definições → Desportos → Disposição do ecrã de sessão. Também ficam no resumo, em cada volta, na
base de dados e no `.fit`, nos campos próprios da norma, que o Garmin
Connect e o Golden Cheetah mostram. Só chegam por **ANT+**: o perfil de
potência do Bluetooth não os transporta.

### O ficheiro .fit: nome e "Virtual"

Cada sessão grava `perennia_<data>_<ficheiro .gpx>.fit`, por exemplo
`perennia_2026-10-26_serra-da-estrela.fit`. Os espaços passam a `-` e saem
os caracteres que o Windows não aceita em nomes de ficheiro. Uma segunda
sessão no mesmo dia e na mesma rota fica com `_2`, depois `_3`, e assim por
diante. Sem rota, o nome usa o treino, `fuga`, `teste-ftp` ou `livre`.

O nome vai também para o resumo da sessão; no `.fit`, o nome do perfil desportivo leva
as **etiquetas** da sessão (ver «Etiquetas e tipo de sessão»). A atividade vai marcada
como **virtual** (subtipo "virtual activity", o mesmo de uma sessão do Zwift ou do
MyWhoosh) **quando segue uma rota .gpx** (ciclismo e corrida); sem rota é «indoor»
(rolo, passadeira, máquina de remo). O Strava mostra a virtual como *Virtual Ride* e o
Garmin Connect como ciclismo virtual.

Nota: o Strava e o Garmin Connect dão às atividades um título deles
("Treino da manhã"…) e não leem o título de dentro do `.fit`. O nome do
ficheiro e o perfil levam o teu nome; o título no site, se o quiseres
igual, muda-se lá.

### Classificações sempre à vista

Em todos os menus há um painel à direita com a classificação do que está
selecionado: os teus recordes no menu inicial, a classificação de cada rota
na biblioteca, a de cada subida no detalhe da rota, a de cada treino, os
melhores FTP, os desafios e as fugas. Durante a sessão o painel fica no canto
direito e mostra-te a ti ("Tu") na posição em que ficarias se acabasses agora
ao ritmo atual. Mostra a subida enquanto estás numa, senão a fuga, o treino,
o teste de FTP, a rota, ou o progresso dos desafios se pedalares sem rota.

### Desafios com objetivo à tua escolha

Todos os desportos têm Desafios (separador Treinar). **Desafios → Novo
desafio**:

1. **Tipo**: Enter alterna entre os que fazem sentido no desporto —
   distância, subida (ciclismo), tempo de treino ou número de sessões.
2. **Objetivo**: escreve o número com o teclado. Aceita decimais com ponto
   ou vírgula: `5000.34`, `5000,34` ou `5,000.34` dão todos 5000,34. A linha
   mostra logo como o número foi lido.
3. **Unidade**: km ou m (mi ou ft em imperial), para os dois tipos. Assim
   "subir 23,5 km" escreve-se `23.5` em km.
4. **Nome**: opcional. Se o deixares vazio, fica "Pedalar 5000.34 km" ou
   "Subir 23.5 km".
5. **Data limite** (opcional): ←/→ mudam um dia, Shift+←/→ uma semana, Del
   tira-a. Com data limite, o desafio mostra quanto tempo falta («faltam 12
   dias e 4 h», «termina hoje · faltam 3 h 20 min», «terminou a 31/10/2026»),
   e o que se fizer depois dessa data já não conta.
6. **Criar desafio** (o botão em baixo, à direita).

No ciclismo o progresso soma-se durante a sessão; nos outros desportos
conta-se a partir do histórico (as sessões concluídas desde que o desafio
começou e até à data limite).

### Fuga

**Challenge → Fuga** no menu do ciclismo: o pelotão parte 150 m atrás de ti e acelera a cada
minuto. Tens de pedalar para não ser apanhado.

- **Níveis**: Fácil começa a 50 % da tua FTP e sobe 3 % por minuto; Normal
  60 % e +4 %; Difícil 70 % e +5 %. Na lista vês em que minuto o pelotão
  chega à tua FTP.
- O pelotão tem o teu peso e a tua aerodinâmica e anda na mesma estrada, por
  isso só a potência decide. Com a mesma potência que ele, a vantagem não
  muda. Escolhe uma rota ou "Sem rota" (plano).
- No ecrã vês a vantagem em metros e segundos, uma barra que muda de cor ao
  aproximarem-se, a potência atual do pelotão e quanto falta para acelerar.
  Há avisos aos 100, 50 e 20 m.
- Quando te apanham, o tempo fica gravado e a sessão continua até carregares
  em parar. Se parares antes, conta o tempo até aí.
- Na fuga não há pausa automática, porque parar de pedalar é deixar o
  pelotão chegar. Uma pausa manual tira essa tentativa da classificação.
- A classificação é por nível e por rota: a subir, a vantagem fecha mais
  devagar, por isso tempos de estradas diferentes não se comparam.

### Segurança e segredos

- **A palavra-passe do Garmin nunca vai para o disco nem para a linha de comandos.** Define a
  variável de ambiente **`PERENNIA_GARMIN_PASSWORD`** (fica fora de qualquer ficheiro) ou escreve-a
  nas Definições (fica **só na memória** até fechares a aplicação). Ao sincronizar, a Perennia
  entrega-a ao GarminDB num ficheiro temporário privado (só o teu utilizador o lê) que apaga no fim,
  mesmo que a sincronização falhe. Se a configuração do GarminDB ainda tiver uma palavra-passe em
  claro (de uma versão antiga), ela é **retirada do ficheiro e da cópia `.bak`** na primeira
  sincronização. Alternativa mais forte: o cofre do sistema (`secure_password` do GarminDB).
- **Strava:** o *Client ID* e o *Client Secret* podem vir das variáveis de ambiente
  **`PERENNIA_STRAVA_CLIENT_ID`** e **`PERENNIA_STRAVA_CLIENT_SECRET`** (nesse caso o segredo nem
  chega à base de dados). A autorização usa um `state` aleatório (o retorno local só aceita o pedido
  que a Perennia fez, e só em `127.0.0.1`).
- **Ficheiros de fora** (`.gpx`, `.zwo`, `.tcx`) são lidos sem DTD nem entidades (recusam-se os que
  as tragam) e com limite de tamanho. Um **backup** não pode escrever fora da pasta de dados (`..`,
  caminhos absolutos e letras de unidade são recusados).
- **A base de dados** fica com permissões só do dono (0600, em Linux/macOS). Os backups só levam as
  *Ligações externas* (Strava) se o pedires.
- **`.gitignore`:** `.claude/`, `.env*`, `*.db`, os `.fit`, `exports/`, `backups/`, chaves e
  certificados nunca vão para o git.
- Lembra-te: **nunca coles chaves ou palavras-passe numa conversa** com um assistente; põe-nas
  sempre em variáveis de ambiente.

- **Treinador e Assistente de saúde:** a chave de um agente online vem **só** de uma variável de
  ambiente (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `PERENNIA_AI_API_KEY`);
  nenhuma chamada a LLM está ativa nesta versão; o pedido que seria enviado vê-se inteiro antes.
- **Repor um backup** recusa um ficheiro que, descomprimido, passe do máximo (4 GB por omissão;
  Definições → Avançado → Dados e backups): um .zip pequeno pode ser feito para encher o disco.

Limites conhecidos: os *tokens* de acesso do Strava ficam **em texto** na base local (protegida pelas
permissões do ficheiro; o Windows ignora o 0600 e vale a pasta do teu utilizador); as ações do
workflow do GitHub estão por etiqueta de versão e não por hash; e o `criar_atalho_windows.bat` usa
`-ExecutionPolicy Bypass` só para o script do atalho.

---

## 5. Bluetooth: o que cada sistema precisa

**Windows 10/11** — funciona sem mais nada. Se o trainer já estiver
emparelhado nas Definições do Windows, desemparelha-o: o FTMS funciona
melhor com o dispositivo livre, e dois programas não podem usar o mesmo
trainer ao mesmo tempo (fecha o Zwift, o MyWhoosh, a app do fabricante).

**Linux** — precisas do BlueZ, que já vem instalado na maioria das
distribuições (`bluetoothctl --version` confirma). Se a procura não
encontrar nada:

```bash
sudo systemctl start bluetooth
sudo usermod -aG bluetooth $USER     # e volta a iniciar sessão
```

**macOS** — na primeira procura, o sistema pede autorização de Bluetooth.
Aceita. Se recusaste por engano: Definições do Sistema → Privacidade e
Segurança → Bluetooth.

> **Acorda o trainer antes de procurar.** A maior parte só anuncia o serviço
> FTMS depois de dar duas ou três pedaladas. Se não aparecer na lista, pedala
> um pouco e procura outra vez.

---

## 6. ANT+ (antena USB)

Usa ANT+ para os pedais de potência (Assioma, Favero, Garmin Rally…), para
um rolo FE-C ou para a cinta de cardio. Podes misturar: por exemplo, rolo
por Bluetooth e Assioma por ANT+.

### Instalar (uma vez)

Com o ambiente virtual ativo:

```powershell
pip install -r requirements.txt
```

Isto instala o `pyusb` e, no Windows e no macOS, o `libusb-package`, que
traz a libusb de que o `pyusb` precisa. No Linux e no Raspberry Pi
instala-a pelo sistema: `sudo apt install libusb-1.0-0`.

**Windows: o driver da antena.** A antena vem com o driver da Garmin, que o
`pyusb` não consegue usar. Tens de o trocar por WinUSB com o
[Zadig](https://zadig.akeo.ie/):

1. Liga a antena e fecha o Zwift, o Garmin Express e qualquer outra
   aplicação que a use.
2. Abre o Zadig → menu *Options* → *List All Devices*.
3. Escolhe a antena na lista ("ANT USB-m Stick", "ANT USBStick2" ou
   parecido; o USB ID começa por `0FCF`).
4. Do lado direito escolhe **WinUSB** e carrega em *Replace Driver*.

Depois disto, outras aplicações que usem o driver da Garmin podem deixar de
ver a antena. Para voltar atrás: Gestor de Dispositivos → a antena → Driver →
Reverter (ou desinstalar o dispositivo e voltar a ligá-lo).

**Linux / Raspberry Pi: permissão.** Cria `/etc/udev/rules.d/99-ant.rules`
com

```
SUBSYSTEM=="usb", ATTRS{idVendor}=="0fcf", MODE="0666"
```

e corre `sudo udevadm control --reload-rules && sudo udevadm trigger`.
Desliga e volta a ligar a antena.

### Emparelhar

1. Pedala umas voltas para acordar os pedais (a Assioma adormece parada).
2. **Dispositivos → Procurar ANT+**. Demora até 12 segundos.
3. Aparecem os dispositivos com o número ANT+, por exemplo
   "ANT+ Potência #4321". Escolhe-os para ligar.

Se tiveres um rolo FE-C e pedais ao mesmo tempo, a aplicação trata disso:
o rolo também emite como medidor de potência, por isso a procura exclui-o e
volta a procurar até encontrar os pedais. A potência do rolo não aparece na
lista, porque já vem pelo FE-C.

Os pedais ficam com prioridade sobre o rolo na potência, na cadência e no
balanço; o rolo continua a fazer a resistência. Se os pedais deixarem de
emitir (bateria, adormeceram), a potência passa para o rolo ao fim de 5
segundos, e volta aos pedais quando eles voltarem.

Se a antena não for encontrada, a linha de estado do ecrã diz porquê (falta
de biblioteca, driver ou permissão).

### Se a FC (cinta ou relógio) não aparece por ANT+

Testa **só a FC**, fora da aplicação — abre um único canal (sem procurar rolo nem potência ao mesmo
tempo, que se atropelam) e escreve o que chega, ao segundo:

```bash
python main.py --testar-hr-ant 30
```

Com o relógio ou a cinta já a transmitir (no Garmin Swim 2: UP no widget da FC → **Transmitir FC**,
ou «durante a atividade» e inicias uma atividade) e a 1–2 m da antena. Diz-te se **a antena abre**,
se **o aparelho é encontrado** (`ANT+ Cardio #nnnn`), quantos **pacotes por segundo** chegam (o
normal são ~4) e a **FC**. Leitura: *nada chega* → o aparelho não transmite ou está longe; *FC 0* →
o sensor ainda não mediu; *poucos pacotes por segundo* → interferência (afasta a antena do PC com uma
extensão USB, evita as portas USB 3 ao lado, aproxima o relógio). Eventos como «colisão com outro
canal» aparecem quando há várias procuras em simultâneo — é normal durante **Procurar ANT+**.

No ecrã **Dispositivos**, cada aparelho ligado mostra **ao vivo** o que está a mandar
(`ANT+ · 59 bpm`, ou `ANT+ · sem dados` se ligou mas calou-se), e o subtítulo atualiza-se ao segundo.
Assim vês logo se uma cinta ou um relógio ligado está mesmo a dar dados.

Se o **computador fica pesado ao procurar** (ventoinhas, CPU ou memória a subir): abre o
Gestor de Tarefas → **Detalhes** e vê se é o `python.exe` e quanto gasta de CPU e de memória; depois
experimenta **só Procurar ANT+** e **só Procurar Bluetooth** (e com a antena desligada) para ver
qual dos dois é. A leitura da antena desiste sozinha (≈ 10 s) se a antena deixar de responder, em
vez de ficar a tentar sem parar, e diz-te «a antena deixou de responder».

### ANT+ primeiro, Bluetooth de reserva

Basta emparelhar cada aparelho **uma vez**, por ANT+ e/ou por Bluetooth. A
partir daí a aplicação lembra-se dele e, **ao abrir, liga tudo sozinha**:

1. Procura por **ANT+** os aparelhos que conhece.
2. O que não aparecer por ANT+ procura-se por **Bluetooth**.
3. Os pedais e a cinta que também conheça por Bluetooth ficam ligados nos
   dois, **como reserva**. O ANT+ manda sempre; se o sinal ANT+ cair a meio
   da sessão, a potência e o balanço continuam a chegar por Bluetooth e
   voltam ao ANT+ quando ele regressar, sem fazeres nada.
4. O **rolo** liga-se só por um caminho (o ANT+, se responder), porque dois
   canais a mandar resistência ao mesmo rolo dariam ordens contraditórias.

Só se ligam aparelhos que já emparelhaste. Os pedais de quem treina ao lado
não entram.

Para voltar a ligar a meio (por exemplo se ligaste os pedais depois de
abrir a aplicação): **Dispositivos → Ligar os meus dispositivos**. Em
**Definições** escolhes a ordem (*ANT+ primeiro*, que é o normal,
*Bluetooth primeiro*, *Só ANT+*, *Só Bluetooth*) e se liga sozinho ao abrir.

Para a Assioma ficar como reserva, emparelha-a uma vez por Bluetooth também.
A Assioma Duo deixa ANT+ e uma ligação Bluetooth em simultâneo.

---

## 7. Partilhar com colegas (sem Python)

Os teus colegas não precisam de Python, venv nem PyCharm. Tu crias uma vez a
versão empacotada, com o Python e as bibliotecas lá dentro, e envias-lhes um
`.zip`.

### No teu PC Windows

1. Faz **duplo clique em `build_windows.bat`**, na pasta do projeto.
   Demora alguns minutos da primeira vez. O script cria um ambiente só para
   o build, que não mexe no teu venv do PyCharm, corre o autoteste e
   empacota.
2. Experimenta `dist\Perennia\Perennia.exe`.
3. Envia `dist\Perennia-windows.zip` (por exemplo pelo OneDrive, Google
   Drive ou WeTransfer; costuma ter 40 a 70 MB).

Os colegas descompactam e abrem `Perennia.exe`. Dentro do zip vai um
`LEIA-ME.txt` com o essencial: abrir pela primeira vez, onde ficam os dados
e o driver da antena ANT+.

**O aviso do Windows.** Da primeira vez aparece "O Windows protegeu o PC",
porque a aplicação não tem assinatura digital, que custa dinheiro todos os
anos. Carrega em *Mais informações* → *Executar mesmo assim*. Só acontece
uma vez.

**Atualizar.** Quando houver versão nova, voltas a correr o
`build_windows.bat` e envias o zip novo. Os colegas substituem a pasta; os
dados deles estão noutro sítio (`%APPDATA%\Perennia`) e ficam.

**O que refazer depois de um `git pull`** (a ronda 15 renomeou o pacote `velo/` para `perennia/`; a ronda 16 só junta ficheiros novos dentro de `perennia/`, por isso a tabela é a mesma):

| Como abres a Perennia | O que fazer |
|---|---|
| `Perennia.bat` / `./perennia.sh` / `python main.py` | **nada**: já abrem o código novo |
| um atalho que criaste com o `criar_atalho_windows.bat` (versão do projeto) | **nada**; se o atalho já não abrir, apaga-o e volta a correr `criar_atalho_windows.bat` |
| a app construída (`dist\Perennia\Perennia.exe`) | **refazer**: apaga a pasta `build` e `dist` e corre `build_windows.bat` outra vez (o `packaging/perennia.spec` já aponta para `perennia`); depois `criar_atalho_windows.bat` para o atalho apontar para o novo `.exe` |
| Mac / Linux | `./build.sh` |

Os dados **ficam**: a pasta e a base são migradas sozinhas na primeira abertura (ver o topo deste
guia). O `.venv` não muda (o `requirements.txt` é o mesmo).

### Mac, Linux, Raspberry Pi

O empacotamento é sempre feito no sistema de destino: um `.exe` só se faz
no Windows, uma app de Mac só num Mac, e uma versão de Raspberry Pi só num
Raspberry Pi. Nesse computador, com Python instalado, corre `./build.sh`.
Sai `dist/Perennia-mac.zip` ou `dist/Perennia-linux-<arquitetura>.tar.gz`.
No Mac, a primeira abertura faz-se com botão direito → *Abrir*.

### Alternativa: o GitHub faz tudo

Se puseres o projeto num repositório do GitHub (pode ser privado), o ficheiro
`.github/workflows/build.yml` já está pronto. Em *Actions* → *Build* → *Run
workflow*, o GitHub gera as versões de Windows, macOS e Linux nas máquinas
dele, sem precisares de ter um Mac. Os ficheiros aparecem em *Artifacts*, no
fundo da página da execução. Se criares uma etiqueta `v1.0.1`, ficam também
publicados numa *Release*, com um link para os colegas descarregarem.

### Se a versão empacotada fechar com um erro

Não há janela de consola. O erro fica em `perennia-erro.log`, na pasta dos
dados, e o Windows mostra uma caixa a dizer onde. É esse ficheiro que te
devem enviar.

---

## 8. Onde ficam os teus dados, e como os mudas de computador

Tudo vive em **dois sítios, numa só pasta**:

| | |
|---|---|
| `perennia.db` | base de dados SQLite: rotas, histórico, classificações, desafios, definições |
| `backups/` | os backups (`.zip`) feitos no menu Backups e as cópias automáticas antes de repor |
| `rides/*.fit` | um ficheiro `.fit` por sessão de ciclismo, pronto a enviar para onde quiseres |
| `strength/*.fit` | um `.fit` por treino de força |
| `exports/` | os treinos que exportas no construtor (`.zwo`, `.erg`, `.mrc`, `.fit`) |
| `imports/` | onde pôr os ficheiros do HRV4Training e do Garmin para importar |

A pasta é:

- **Windows**: `%APPDATA%\Perennia`
- **macOS**: `~/Library/Application Support/Perennia`
- **Linux / Raspberry Pi**: `~/.local/share/perennia`

**A base de dados atualiza-se sozinha.** Ao abrir uma versão nova, a
Perennia acrescenta o que faltar (tabelas e colunas novas) sem tocar no que
já lá está — não tens de fazer nada. Antes de atualizar, por cautela, copia
o `perennia.db`. O que a ronda 6 acrescentou:

| Tabela / coluna | Para quê |
|---|---|
| `workouts.status`, `row_workouts.status`, `endurance_workouts.status` | `active` (na lista) · `deleted` (apagado, os passos ficam) · `session` (só de uma sessão) |
| `session_workouts` | a cópia do treino de cada sessão e o original (`workout_id`, vazio quando veio do computador e não ficou na lista) |
| `perennia_segments` | os teus segmentos: rota, nome, km de início e de fim |
| `segment_efforts` | os tempos nos segmentos (Perennia, e Strava na corrida), por sessão e desporto |
| `endurance_sessions.route_id` | a rota de uma corrida (para as vezes feitas e os segmentos) |

A ronda 7 (Backups e reposição) **não muda o esquema**: lê e escreve as
tabelas que já existem.

O que a ronda 8 acrescentou (tudo automático ao abrir):

| Tabela / coluna / definição | Para quê |
|---|---|
| `equipment_items.purchase_date`, `equipment_items.purchase_price` | data e preço de compra de cada artigo |
| `lab_results.doctor_comment` | o comentário do médico a cada análise |
| `synced_activities.tss`, `.if_value`, `.avg_power_w`, `.np_w` | a TSS, o IF e a potência das atividades importadas (TrainingPeaks) |
| definição `pmc_synced` | se as atividades importadas contam para a forma |
| definições `rower_levels`, `treadmill_max_kmh`, `treadmill_max_incline` | os limites Não ERG do remo e da passadeira (os níveis do rolo já existiam) |
| definições `metrics_disabled_<desporto>` | as métricas de sessão desligadas de cada desporto |

Na primeira vez que abres a ronda 8, a carga das corridas (rTSS) e das
natações (sTSS) já gravadas é **recalculada uma vez** com as fórmulas do
TrainingPeaks, e o feedback no fim das sessões passa a estar sempre ligado.

**A ronda 16 cria 4 tabelas novas — sozinha, na primeira vez que são precisas** (**não tens de
fazer nada** na base local; antes de abrires a versão nova podes fazer um backup). Nenhuma tabela
antiga muda de colunas:

| O quê | Como fica |
|---|---|
| tabela `bp_readings` | as medições da pressão arterial (dia, período, hora, máxima, mínima, pulsação, nota, origem) |
| tabela `health_tabs` | os separadores que criares na Saúde |
| tabela `health_tab_notes` | as notas de cada separador |
| tabela `coach_events` | os eventos do Treinador (com as respostas e as sessões que pôs no calendário) |
| `daily_values` (tensão máxima e mínima) | passam a guardar a **média diária** das medições (origem `bp`); os valores que lá tinhas viram uma medição «Sem período» (automático e idempotente) |
| definição `bp_periods` | os teus períodos, se os mudares |
| definições `coach_challenge_priority`, `coach_plans` | a importância de cada desafio e as sessões que o Treinador pôs no calendário |
| as opções novas de Definições → Avançado | uma definição por opção, só criada quando a mudas |

As tabelas criam-se com `CREATE TABLE IF NOT EXISTS` em `bp.ensure`, `health_tabs.ensure` e
`coach.ensure`. Os backups levam-nas: as três primeiras com a **Saúde**, `coach_events` com o
**Calendário**, e as definições com as **Definições**.

**A ronda 15 NÃO cria tabelas nem colunas — e é tudo automático** (**não tens de fazer nada** na
base local; antes de abrires a versão nova podes fazer um backup). O que muda:

| O quê | Como fica |
|---|---|
| a pasta de dados `VeloLocal`/`velolocal` | passa a `Perennia`/`perennia` (renomeada de uma vez, na primeira abertura) |
| `velolocal.db` | passa a `perennia.db` |
| `rides.fit_path` e outros caminhos; `source_format = 'velolocal'` | atualizados (idempotente: correr duas vezes não muda nada) |
| definição `adhoc_state` | a última vista da AdHoc Analysis (JSON) |
| definição `adhoc_views` | as vistas guardadas (lista de nome + vista, JSON) |
| as opções de Definições → Avançado (tabela acima) | uma definição por opção, **só criada quando a mudas**; sem ela, vale o valor por omissão |

Tudo isto são linhas da tabela `settings`: não há `ALTER TABLE`. Os backups levam-nas com as
**Definições** (o conjunto «Definições» foi alargado: as opções do Avançado e as vistas da AdHoc já
vão lá, mesmo as que se chamam `agent_…` ou `strava_…`, que não guardam segredos). A migração do
nome antigo está toda em `perennia/legacy.py` e `Database._migrate`.

**A ronda 14 NÃO cria tabelas nem colunas — e continua a ser tudo automático** (**não tens de fazer
nada** para que fique guardado na base local: o que muda são só **definições**, na tabela `settings`,
e a Perennia arruma-as sozinha ao abrir; antes de abrires a versão nova podes fazer um backup:
*Backups e Sincronização → Exportar → Tudo*, ou `python main.py --backup`). O que muda:

| Onde | O quê |
|---|---|
| definição `keymap` (tabela `settings`) | os atalhos de **volta, pausa, terminar e começar** eram um por desporto (`ride_lap`, `row_lap`, `run_lap`, `ride_pause`, `row_pause`, `run_pause`, `gym_pause`, `ride_finish`, `row_finish`, `run_finish`, `gym_finish`, `run_start`); agora são **um só para todos** (`lap`, `pause`, `finish`, `start_now`) e há ids novos: `skip_block` (saltar bloco), `ride_res_up`/`ride_res_down` e `row_res_up`/`row_res_down` (resistência), `row_fields`, `speed_up`/`speed_down` e `incline_up`/`incline_down` (corrida) e `run_total`. **Ao abrir**, a Perennia reescreve **uma vez** o que já tinhas mudado para os ids novos (fica a primeira tecla que encontra, pela ordem ciclismo, remo, corrida, ginásio) e apaga os ids antigos; se não tinhas mudado nada, nada acontece. Vai no backup, componente «Atalhos de teclado»; um **backup antigo** repõe-se na mesma e fica já unificado |
| definição `gym_auto_end_timed` (opcional) | as séries **por tempo** do ginásio (a prancha de 40 s) terminam sozinhas quando a contagem chega a zero. Não existe na base: vale **ligado**. (Não há opção para isto nas Definições; quem quiser desligar escreve `false` nesta chave.) Vai no backup, componente «Definições» |
| `strength_sets.rpe` | a sessão de ginásio já **não pede o RPE**: nas séries novas a coluna fica vazia; as antigas mantêm o que tinham. A 1RM estimada só conta as repetições em reserva quando há RPE |
| `session_countdown_s`, `sound_rules`, `workout_lookahead` | continuam como estavam; agora podem mudar-se durante uma sessão (Definições → Geral e Configurações sonoras) |

Os **backups** continuam a levar tudo e nenhuma tabela ficou por tratar; **nada** do que aqui está
precisa de um script de migração à mão.

**A ronda 13 acrescenta UMA coluna — e continua a ser tudo automático** (**não tens de fazer nada**
para que fique guardado na base local: ao abrir a versão nova a Perennia acrescenta a coluna sozinha,
sem tocar nos dados que já lá estão; antes de abrires a versão nova podes fazer um backup: *Backups e
Sincronização → Exportar → Tudo*, ou `python main.py --backup`). O que muda:

| Onde | O quê |
|---|---|
| `endurance_samples.incline_pct` (coluna nova, `REAL`) | a **inclinação da passadeira**, ao segundo, nas sessões de corrida (o que escolheste nos cartões Velocidade/Inclinação, ou a do bloco do treino). As sessões antigas ficam com a coluna **vazia** (a análise só mostra a linha «Inclinação (%)» quando há valores). A velocidade já se gravava (`speed_mps`) e continua |
| definição `screen_layout_gym` (tabela `settings`) | a **disposição dos painéis do ecrã do ginásio** (estado, métricas, séries, lista). Sem nada guardado vale a de origem. Vai no backup, na componente «Ecrã da sessão» |
| definições `layout_<desporto>` | deixa de haver o «Número de métricas no ecrã»: o número é o das métricas que escolheres no editor (a lista guardada é a mesma de antes) |

Os **backups** levam a coluna nova (e um backup feito **antes** da ronda 13 repõe-se na mesma: a
inclinação fica por preencher) e nenhuma tabela ficou por tratar.

**A ronda 12 NÃO cria tabelas — e continua a ser tudo automático** (**não tens de fazer nada** para
que fique guardado na base local; antes de abrires a versão nova podes fazer um backup:
*Backups e Sincronização → Exportar → Tudo*, ou `python main.py --backup`). O que muda:

| Onde | O quê |
|---|---|
| definições `sound_rules`, `sound_on`, `sound_end` (tabela `settings`) | as **configurações sonoras**: a lista de regras de bips, os bips ligados/desligados e o bip longo no fim. Sem nada guardado valem as de origem (últimos 5 s, 1 bip/s). Vão no backup, componente «Definições» |
| `strength_sessions.mode` | passa a ter o valor **`freeplan`** nas sessões de **treino livre** do ginásio (a coluna já existia; se faltar, a Perennia acrescenta-a sozinha). É o que marca as sessões que se podem editar depois. As sessões antigas ficam como estavam (`plan`, `free`, `conditioning`) |
| `strength_workouts` / `strength_workout_items` | um treino livre cria um treino **escondido** com os exercícios (1 volta, 0 repetições, sem RPE nem descanso); se escolheres «Guardar como treino da modalidade» fica visível com 3 × 10 e 90 s. Os rascunhos que nunca foram usados limpam-se sozinhos |
| `strength_sets.reps` | nos treinos livres começa em **0** («por marcar») e o que escreves na janela das repetições (ou depois, em *Editar séries*) fica aqui; os totais da sessão (`total_reps`, `volume_kg`) acertam-se quando corriges |
| `training_plan` | já não aceita dias passados (só hoje e dias futuros) |

**A ronda 11 NÃO cria tabelas nem colunas — e continua a ser tudo automático**: **não tens de
fazer nada** (nem correr scripts) para que as alterações fiquem guardadas na base local; ao
abrir a versão nova a Perennia faz sozinha o que precisa. O que muda no que já lá está:

| Onde | O quê |
|---|---|
| definição `longevity_formula` (tabela `settings`) | a **fórmula da Longevidade** que editaste (pesos e doses de referência dos eixos, mistura com os testes, minutos dos hábitos e os **parâmetros próprios**). Vazia = a fórmula de origem. O índice continua a não guardar nada: recalcula-se sempre. Vai no backup, na componente «Definições» |
| `strength_workouts.modality`, `strength_sessions.modality`, `exercise_modalities` | a modalidade **Longevidade** deixou de existir: **uma vez** (ao abrir), os treinos e as sessões que lhe pertenciam passam para a **Força**, o treino de origem passa de «Longevidade · força e equilíbrio» para «Força e equilíbrio» e os exercícios que só estavam na Longevidade ficam na Força. Nada se apaga (as tuas sessões e o histórico mantêm-se) |
| `session_tags` / `tag_catalog` | as sessões de **ginásio** passam a ter etiquetas (`sport = 'strength'`: `Perennia`, `Indoor Strength` e as que escolhas) e o `.fit` leva-as; as sessões antigas não têm etiquetas (não se alteram) |
| `daily_values`, `day_notes` | o **.csv da Saúde** escreve aqui, com `source = 'csv'` (para as apagares: `DELETE FROM daily_values WHERE source = 'csv'`) |
| `strength_workouts` | os treinos de ginásio importados **do computador** (.csv, .json, .txt, .fit) entram aqui (e os exercícios que ainda não existiam em `exercises`); os que escolheres «só para esta sessão» ficam escondidos da lista |
| `training_plan` | o botão **Planear** e a janela do dia escrevem aqui (um treino por dia e por desporto, sem duplicar) |

A **Sincronização mudou de sítio** (de Definições para Backups e Sincronização), mas as suas
opções continuam nas mesmas definições (`sync_*`, `garmindb_*`) — **não perdes nada**. A
password do GarminDB continua só na configuração do próprio GarminDB, e os backups continuam a
deixar de fora as credenciais por omissão. Se quiseres uma rede de segurança antes de abrires
a versão nova: **Backups e Sincronização → Exportar → Tudo**, ou `python main.py --backup`.

**A ronda 10 acrescenta tabelas e colunas — e continua a ser tudo automático**: ao abrir a
versão nova a Perennia cria o que falta (`CREATE TABLE IF NOT EXISTS` e `ALTER TABLE ADD
COLUMN` só quando a coluna não existe), **não tens de fazer nada** nem de correr nenhum
script — as tuas sessões, treinos, rotas e definições ficam como estão. (Se quiseres uma rede
de segurança, faz um backup antes: Backups, ou `python main.py --backup`.)

| Tabela / coluna / definição | Para quê |
|---|---|
| `workout_types` (`sport`, `workout_id`, `wtype`) | o **tipo de treino** de cada treino (o do construtor); vazio = «Automático» |
| `session_tags` (`sport`, `session_id`, `tag`, `kind`) | as **etiquetas** de cada sessão: `workout_type`, `session` (Perennia, Indoor…) ou `custom` |
| `tag_catalog` (`tag`) | as etiquetas livres já usadas (para sugerir ao escreveres) |
| `muscle_groups` (`key`, `name_pt`, `name_en`) e `muscle_subgroups` | os **grupos e subgrupos musculares**; os de origem são criados uma vez (só se a tabela estiver vazia) |
| `exercises.subgroup_id` | o subgrupo muscular de cada exercício (`exercises.category` continua a guardar a chave do grupo) |
| `gym_disciplines` (`key`, `name_pt`, `name_en`, `icon`) | as **disciplinas** que juntas: cada uma é uma modalidade com o seu separador |
| definição `treadmill_incline_step` | o **passo da inclinação** da passadeira (0,1 · 0,5 · 1 %) |

Mais: três modalidades novas (**mobility**, **tendons**, **isometric**) com os seus exercícios
entram na lista (o catálogo de origem é acrescentado, sem mexer nos teus exercícios). O
**índice de longevidade não guarda nada**: calcula-se sempre de novo a partir das sessões, dos
diários e dos testes (por isso corrige-se sozinho se apagares ou editares uma sessão). Os
`.fit` **já gravados** não mudam (as etiquetas só entram nos novos); as sessões antigas não
têm etiquetas, e a análise delas simplesmente não mostra a linha «Etiquetas».

Os **backups** levam as tabelas novas: `workout_types` em «Treinos»; `session_tags` e
`tag_catalog` em «Histórico de sessões»; `muscle_groups`, `muscle_subgroups` e
`gym_disciplines` em «Ginásio e exercícios». A definição `treadmill_incline_step` vai em
«Definições». O que **não** entra num backup por omissão continua a ser só as credenciais.

**A ronda 9 não muda o esquema da base de dados** — não há tabelas nem
colunas novas, **não tens de fazer nada** para que as alterações fiquem
guardadas. O que muda no que já lá está:

| Onde | O quê |
|---|---|
| `synced_activities` | as atividades do **Upload manual** entram aqui com `source = 'upload'` e o id `up:<impressão do ficheiro>` (por isso o mesmo ficheiro não se duplica). Podes apagá-las com SQL: `DELETE FROM synced_activities WHERE source = 'upload'` |
| definições `layout_<desporto>` e `row_fields` | passam a ter o **tamanho que escolheres** (o número de métricas do ecrã), em vez de um tamanho fixo (8 na corrida, 24 no remo, 4 no ginásio); as listas que já tinhas continuam a valer |
| definições `pmc_ctl0`, `pmc_atl0` | deixaram de existir nas Definições e de ser usadas (a forma parte de zero); se estiverem na base, são ignoradas |
| definições de **Natação** (`layout_swimming`, `metrics_disabled_swimming`) | deixaram de ter ecrã; ficam na base, sem efeito |

Os **backups** continuam a levar tudo (as listas de métricas vão na componente
«Ecrã da sessão» e os uploads em «Histórico de sessões»).

**Para mudar de computador:** faz um backup completo (menu Backups ou
`python main.py --backup`), leva o .zip e, no computador novo, arrasta-o para
a janela da Perennia e escolhe Substituir. Também continua a dar para copiar
a pasta inteira. Na máquina nova,
instala a aplicação e põe a pasta no caminho equivalente — abre com todo o
histórico, as classificações e os recordes intactos. Também podes guardar a
pasta onde quiseres e correr sempre com `--data-dir /caminho/para/a/pasta`,
por exemplo numa pen ou numa pasta sincronizada.

**Para enviar uma sessão para o Strava, o Garmin Connect ou o Intervals.icu:**
abre o sítio no navegador e arrasta para lá o `.fit` da pasta `rides/`. O
caminho exato aparece no ecrã de resumo no fim de cada sessão.

---

## 9. Raspberry Pi

**Ainda por confirmar.** O Raspberry Pi 3 não serve: a placa gráfica só chega
ao OpenGL ES 2.0 e a pyglet 2 precisa de OpenGL 3.3 ou ES 3.1. O Pi 4 e o Pi 5
têm OpenGL ES 3.1, mas o desenho da estrada ainda está escrito para o OpenGL
de computador; falta acrescentar o modo OpenGL ES e testá-lo num Pi. O resto
(sensores, ANT+, Bluetooth, `.fit`) não depende disso.

Quando estiver pronto, num Pi 4 ou 5 com Raspberry Pi OS de 64 bits instala-se
como em Linux, e depois:

```bash
python main.py --fullscreen
```

Nas **Definições**, põe a qualidade do render em **Baixa**. É o preset
desenhado para o Pi: desenha 600 m à frente em vez de 3000 m, com menos
vegetação. Se a imagem ficar a tremer, reduz a resolução da janela
(`--width 1280 --height 720`).

No Pi, confirma que a aceleração gráfica está ligada: `raspi-config` →
*Advanced Options* → *GL Driver* → **GL (Full KMS)**.

---

## 10. Se algo não correr bem

**"No module named pyglet"** — o ambiente virtual não está ativado. Corre
outra vez `source .venv/bin/activate` (ou `.\.venv\Scripts\Activate.ps1`).

**A janela abre negra ou fecha logo** — é quase sempre o driver gráfico. O
`--self-test` passa mesmo assim, o que te diz que o problema é só o render.
Em Linux, instala `sudo apt install libgl1 libglib2.0-0`. Em máquinas
virtuais, a aceleração 3D costuma faltar.

**O trainer aparece mas a resistência não muda** — fecha qualquer outra
aplicação que esteja ligada a ele. Só um programa de cada vez pode controlar
um trainer. Confirma também, no ecrã de Dispositivos, que aparece "declive"
e "ERG" na linha do trainer: é o que o próprio trainer declara saber fazer.

**A frequência cardíaca não aparece** — a cinta é um dispositivo separado.
Liga-a também no ecrã de Dispositivos; podes ter os dois ligados ao mesmo
tempo, e a cinta tem prioridade sobre o sensor do trainer.

**Não encontro o meu .gpx** — põe-no na pasta `gpx/` ao lado do `main.py`.
A aplicação também procura em `~/Downloads`, `~/Transferências`,
`~/Documents` e na pasta atual.

---

## 11. Estado honesto do que está feito

**Verificado com testes automáticos nesta versão** (1094 testes a passar).

*Novidades da ronda 16 (testes novos em `tests/test_round16.py`):* a **pressão arterial** com
várias medições por dia e por período (média de cada período, média diária nas duas formas,
ignorar a 1.ª, validação, períodos teus, migração dos valores antigos do diário, AdHoc e backup);
os **separadores da Saúde criados por ti**, com Notas; o **Assistente de saúde** (avaliação geral
e por componente, com os limiares nas opções); o **Treinador** (avaliação da sessão, eventos de
resistência e de força com perguntas, viabilidade, fases, alimentação e calendário, feedback aos
desafios com a importância, caminho para a longevidade, sugestão do dia, treino programado para o
construtor e feedback a um treino construído, com versão mais leve e veredicto ao vivo); o
**aconselhamento** em três modos (regras; LLM local e agente online preparados, com tokens, janela
e custo à vista, chave só por variável de ambiente e nada do Strava); o **limite de tamanho ao
repor um backup**; a piscina passou a escolher-se numa lista; e as opções do Avançado são agora
86. **O LLM local e o agente online não foram ligados nem testados contra um modelo real**
(continuamos offline): só o pedido, os tokens e os ecrãs. As regras do Treinador e do Assistente
são heurísticas de treino e de leitura de registos, testadas na lógica, **não validadas por um
treinador ou por um médico**. Sem hardware real, sem Windows/macOS.

*Novidades da ronda 15 (testes novos em `tests/test_round15.py`, e os antigos atualizados):* o
**nome Perennia em todo o lado** (o pacote `velo/` passa a `perennia/`; a pasta de dados, a base e
os ficheiros antigos migram sozinhos e de forma idempotente; o nome antigo só existe em
`perennia/legacy.py`); a **segurança** (a palavra-passe do Garmin só em memória ou na variável
`PERENNIA_GARMIN_PASSWORD` e entregue ao GarminDB por um ficheiro temporário privado; o Strava por
variáveis de ambiente e com `state`; XML de fora sem DTD; backups que não escrevem fora da pasta de
dados; a base com permissões do dono; `.claude/`, `.env*`, `*.fit`, `exports/` no `.gitignore`;
permissões mínimas no workflow do GitHub); as **listas pendentes** (Enter abre uma lista com pesquisa
onde antes só havia ←/→ — exercícios, rotas, etc.; ←/→ continuam a passar ao seguinte); a
**estimativa de tokens** (e de custo) no ecrã do agente antes de enviar; a **AdHoc Analysis** (as
cinco fontes, filtros, os cinco tipos de gráfico, o .csv com nome, separador e decimal, a proteção
contra fórmulas, as vistas guardadas e o `--adhoc-exportar`); **Definições → Avançado** com
31 opções afináveis (a tabela está em «Definições → Avançado», mais atrás) e os backups a
levá-las com as Definições. **Não foi testado com hardware real, com Windows/macOS nem com um
GarminDB verdadeiro** (a entrega da palavra-passe por `password_file` está testada contra um
substituto, não contra o programa real).

*Novidades da ronda 14 (testes novos em `tests/test_round14.py`, `tests/test_ui_walk.py` e nos de
backup, e os antigos atualizados):* o aviso **PAUSA** nos cinco desportos (P, Esc, os botões
Retomar e Terminar, F10/D, o «Não» que volta ao PAUSA, nada antes de a sessão começar); Dispositivos
e Definições a **pôr a sessão em pausa** e o PAUSA à espera ao voltar; as Definições durante a
sessão (os cinco separadores, só o desporto da sessão, só os passos seguintes e o tema, as unidades e
o idioma, perguntar antes de sair com alterações); os **atalhos únicos** (a mesma tecla em todos os
desportos, a migração dos antigos, os novos: saltar bloco, velocidade, declive, resistência); o
**ginásio** (sem cronómetro nem RPE, a contagem decrescente na métrica Série / descanso ou no aviso ao
centro, a série por tempo a contar para trás, o descanso com o tempo na coluna das repetições, o
Saltar a meio de uma série); o **robô** que percorre todos os menus e carrega em teclas ao acaso em
cada sessão (`SEEDS=30 python -m unittest tests.test_ui_walk`); e os backups (os atalhos antigos
voltam unificados, a base unifica-os ao abrir).

*Novidades da ronda 13 (13 testes novos em `tests/test_round13.py`, e os antigos atualizados):* a
janela de **Dispositivos** por ligação (os blocos Bluetooth, ANT+ e SEM HARDWARE pela ordem
certa, cada um com o seu «Procurar»; os encontrados recuados por baixo; o ✓ nos ligados; Enter
liga e desliga; a passadeira e o remo simulados nos ligados; a lista informativa do fim, sem
ações; a janela que cresce para caber tudo e passa a duas colunas se a janela for pequena); a
**corrida livre** (as teclas e os cliques nos cartões, os passos de 0,1 km/h e 0,5 %, o limite da
inclinação, o tempo total e o da volta como métricas, o subtítulo vazio, a inclinação gravada ao
segundo, a linha da análise e o campo *grade* do `.fit`); a coluna `incline_pct` numa base antiga e
nos backups (também num backup sem a coluna); a disposição dos painéis do ginásio a abrir o ecrã do
ginásio; as Definições sem «Número de métricas no ecrã»; e o treino de ciclismo sem o mundo 3D.

*Novidades da ronda 12 (testes novos em `tests/test_round11.py`, e os antigos atualizados):* o
calendário (um dia passado só carrega treino, hoje e o futuro planeiam; o seletor de datas do
Planear só de hoje para a frente; `plan_it` recusa o passado); o fim do treino por blocos (o diálogo
de terminar abre-se sozinho e o tempo pára, em ciclismo, corrida, remo e ginásio); os avisos
sonoros (as regras primeiros/últimos N segundos, bips por segundo, o âmbito, o bip longo, os que já
passaram não tocam, o som desligado mas os últimos segundos à vista, o tom WAV, o separador das
Definições: adicionar, editar, apagar, repor, testar, guardar); a sessão de ginásio (começa sozinha
depois dos 15 s, o botão Lap, as colunas de repetições e carga, os descansos na lista, o fim
automático); o treino livre (só exercícios, Lap abre as repetições, o descanso continua, não
termina sozinho, editar séries depois — só nas sessões livres); o botão «Começar treino»; e o
backup a levar as configurações sonoras e a marca de sessão livre.

*Novidades da ronda 11 (35 testes novos em `tests/test_round11.py`, e os antigos atualizados):*
o .csv da Saúde (modelo, exportação, ida e volta por data, colunas desconhecidas e valores
inválidos) e o separador na Sincronização; o menu **Backups e Sincronização** com os três
separadores e a Sincronização fora das Definições; o decoupling (Pa:HR, os limiares de leitura,
o histórico lido das sessões com FC e a vista nas estatísticas do ciclismo); os ícones dos botões
(o mesmo para a mesma ação, o «+» desenhado pelo ícone, todos os ficheiros existem); as etiquetas
(`Perennia` e `Indoor …` sempre, criar uma etiqueta nova, o `.fit` e a base nas sessões de
ginásio); o calendário (seletor de datas, a janela do dia com nota, diário e planear, o planear
de um dia futuro e de um dia passado); a fórmula da Longevidade (editar, recalcular, parâmetros
próprios, o separador); o ginásio sem Longevidade (modalidades, importar de .txt/.csv/.json/.fit,
a janela da sessão por níveis, a configuração com o auto lap bloqueado); a sessão de força em
lista (Enter começa a série, botões em baixo, Esc pausa, F10 pergunta, etiquetas) e o ecrã das
voltas com o mesmo fluxo; o botão **Planear** na ficha de todos os desportos; o subtítulo
*atleta · FTP · LTHR*; e a fórmula e o .csv a viajarem no backup. **Não foi testado com
hardware real** nem com Windows/macOS.

*Novidades da ronda 10 (46 testes novos em `tests/test_round10.py`, e os antigos atualizados):*
o diálogo de terminar (Esc pausa, F10 pergunta, Enter/S/Y, Esc/N, D) igual no ciclismo, na
corrida e no remo, e a janela das etiquetas a seguir; os simuladores (cada um só com os seus
dados, a passadeira); as etiquetas (a sugestão do tipo de treino pelo esforço, o tipo de sessão
e o «virtual» só com rota, a deteção das etiquetas existentes, as etiquetas dentro do `.fit` e
na base, o tipo de treino no construtor); o índice de longevidade (13 períodos, a saturação,
Z2 → 100 % aeróbio, VO2máx + Z2, o impacto de cada sessão, os testes e os hábitos, o
construtor), o menu Longevidade e o radar nas páginas das sessões; o GPX Conversor (as três
fórmulas da passadeira e as duas do rolo, a média móvel, os troços, o passo e o máximo da
passadeira, o separador do construtor); os grupos musculares, as novas modalidades, as listas
no editor de exercícios, as disciplinas novas com o seu separador; os CSV (modelos, exportação,
importação sem duplicar, deteção pelo cabeçalho, ida e volta) e o `--importar csv`; as
tabelas novas nas componentes do backup. **Não foi testado com hardware real** (a passadeira
simulada, o rolo e o remo são simuladores) nem com um Windows/macOS.

*Novidades da ronda 9 (27 testes novos, e os antigos atualizados):* o número
de métricas do ecrã da sessão (1 até ao máximo de cada desporto) e a sessão de
corrida, de remo (com páginas repartidas por igual) e de ginásio a desenhá-las;
a pesquisa na barra do topo e as mensagens; o leitor de `.fit` (escrito de
raiz, testado com um `.fit` escrito pelo próprio codificador, e com ficheiros
cortados e estranhos), o `.tcx` e o fluxo do Upload manual (desporto à
escolha, sem duplicar, arrastar para a janela); o `--importar atividade`; os
resultados dos testes em janelas (editar, apagar, registar) e a natação sem
«Fazer o teste»; a exportação de treinos (os quatro formatos do ciclismo,
`.fit` do remo, `.json` e `.txt`, sem escrever por cima); a ficha do treino
sem «Sobre este treino» e a natação sem sessão; os objetivos numa janela e o
nome e o objetivo alinhados; e a janela única da «Sessão de treino» (todos os
modos, Esc a voltar atrás) em todos os desportos.

*Novidades desta versão (24 testes novos, e os antigos atualizados):* o
fitness, a fadiga e a forma com as constantes e a forma do dia anterior do
TrainingPeaks (100 TSS a partir do zero dá CTL 2,353, ATL 13,312 e TSB
−10,96 no dia seguinte); rTSS (1 h ao limiar =
100) e sTSS (a intensidade ao cubo); EF, desacoplamento e durabilidade;
os avisos de progressão (corrida longa e volume semanal); Riegel, Tanda e o
VDOT de Daniels (5 km em 20:00 ≈ 49,8) com as três tabelas de zonas; a
prontidão (pronto, atenção, descansa); a importação do TrainingPeaks (sem
duplicar, a contar para a carga) e das análises em .csv com o comentário do
médico; a data e o preço de compra; os limites dos aparelhos; a pesquisa
nas listas; o seletor de datas e a lista com pesquisa; o calendário no
ecrã inicial; o ecrã das métricas de evolução; as definições novas nas
componentes certas do backup; e o `--importar` da linha de comandos.

*Novidades desta versão (13 testes):*

- o modelo dos blocos: juntar, desligar, mover e converter blocos;
  parâmetros, RPE↔RIR e % da 1RM; a prescrição e o resumo; a ordem das
  séries nos supersets e nos circuitos, e os descansos;
- gravar o treino, e o editor simples a desfazer a estrutura;
- a sessão a seguir os blocos, com o alvo de cada série;
- o construtor no ecrã: menus, escrever nas células, arrastar para juntar
  e para reordenar, o texto, a hora de início, o planear e o aviso ao
  sair;
- a análise pós-treino (cumprimento, 1RM contra a sessão anterior, séries
  prescritas e feitas) e o histórico e a evolução por exercício.

*Novidades desta versão (29 testes):* nome novo, com a pasta e a base de
dados antigas aproveitadas; os quatro temas, sem preto, com as cores
trocadas em todos os ecrãs; objetivos escritos e sugeridos, nomes e alvos
dos blocos, repetições agrupadas e o resumo antes de começar; o objetivo do
bloco no HUD; o feedback no fim da sessão, a análise que o cruza com o
objetivo (execução, duração, RPE previsto, dores) e o registo para o
agente; o editor do ecrã de cada desporto, também a arrastar com o rato; o
calendário, com planos, dias e resumos das semanas; e a carga e prontidão.

*Novidades desta versão (31 testes):* volta automática por tempo e por
distância, conversão das intensidades (% do limiar para W, FC, RPE e ritmo),
modalidades do ginásio, treino surpresa só com o equipamento que tens,
inventário de artigos, planos de Conditioning (o tempo só arranca na
primeira volta), sessões de corrida e natação com `.fit` e recuperação
depois de uma falha, as métricas novas do remo, terminar sem guardar, o
construtor de blocos (incluindo arrastar com o rato), o aviso de aparelho
desligado a meio da sessão, e o menu de cada desporto por separadores.

*Novidades desta versão (40 testes):* importação do Excel das análises (com
o intervalo de referência certo para a tua idade e sexo, valores com % e com
"<", reimportação sem perder o comentário do médico, correção manual que
fica), HRV4Training no formato real do export, GarminDB (com uma
`garmin.db` construída com as mesmas tabelas e colunas), Strava (autorização,
renovação das chaves, segmentos que a rota percorre no mesmo sentido, PR, o
segmento ao vivo no passeio, e a garantia de que nada vai para o agente — com
o Strava a fingir, sem rede), e o remo: os pacotes da Domyos e do FTMS
montados à mão e lidos, os comandos de resistência byte a byte, o motor
(distância, ritmo, pausas, voltas, treinos por tempo e distância com a
resistência posta sozinha, testes, Regata e jogos com a FTP do remo,
recuperação depois de uma falha), o `.fit` de remo indoor, a volta de remo
no Conditioning e os ecrãs.

*Novidades desta versão (32 testes):* os seis jogos do modo Challenge (alvos
nunca abaixo de 10 s, escala pela FTP, nível adaptativo que sobe e desce,
combos e anéis, eliminação em que a tática conta, recuperação do estado),
o jogo dentro do passeio (alvo, ERG, classificação ao vivo, resumo e
recorde), testes de aptidão das quatro modalidades (cronómetro, resultados,
tendência, testes teus, VO2máx do teste de 5 min), diário de saúde (todos os
tipos de métrica, notas, dias), análises com comentário do médico,
importação do HRV4Training e do Garmin, treino livre e Conditioning (voltas,
distância da passadeira, `.fit`, recuperação) e o pedido do agente.

*Novidades desta versão (35 testes):* sessões de força do princípio ao fim
(séries, correções no descanso, carga pela FC e pelo RPE, 1RM estimada,
volume, `.fit` com as séries), construtor de planos e de exercícios,
recuperação depois de uma falha (ciclismo e força: retomar, guardar ou
descartar, com o estado reconstruído e as amostras sem buracos nem
repetidas), exportação `.zwo`/`.mrc`/`.erg` lida de volta pela própria
aplicação, `.fit` de treino estruturado, fitness/fadiga/forma, FTP estimada
(20 min, 60 min e potência crítica) e tempo em zona por período.

*Núcleo (145 testes):* importação de GPX e reamostragem, deteção de subidas,
física do ciclista, escala da sensação de declive e resistência extra,
declives médios a 500 m / 1 / 3 / 5 / 10 km, registo extensível de métricas,
base de dados e portabilidade, classificações de rota e de subida, voltas
manuais, desafios com progresso e reinício, modo de comparação com
fantasmas, treinos estruturados e ERG, protocolos de teste de FTP,
codificador `.fit` (estrutura e CRC validados), fusão de vários sensores com
prioridades, e a descodificação byte a byte dos protocolos FTMS, Cycling
Power, Heart Rate, CSC e ANT+ FE-C contra pacotes construídos à mão.

*Interface (51 testes):* como esta máquina não tem placa gráfica, foi
construída uma pyglet falsa — janelas, etiquetas e formas que registam o que
lhes é pedido em vez de desenhar. Os testes abrem todos os ecrãs, movem a
seleção, importam um `.gpx`, ajustam as definições, trocam o idioma,
constroem o mundo 3D dos três presets (com validação da coerência dos
vértices e dos índices), correm uma sessão, carregam na tecla L, apanham a
placa da subida, terminam e chegam ao resumo com o `.fit` verificado. Isto
apanhou dois defeitos reais: escolher "Sem rota" num treino ou num teste de
FTP abortava a aplicação, e o evento da subida não transportava a posição,
pelo que a distância ao topo aparecia errada.

**Precisa do teu hardware e da tua placa gráfica para confirmar**: a camada
que fala com o rádio, e o desenho em si. Os descodificadores e a lógica da
interface estão testados, mas a pyglet verdadeira nunca correu aqui, e se o
teu trainer tem alguma particularidade é no primeiro emparelhamento que se
vê. O ecrã de Dispositivos mostra o que o trainer declara suportar — é por
aí que começas.

**Por confirmar com aparelhos verdadeiros**: como o Garmin Connect mostra as
séries do `.fit` da força, e o `.fit` de treino estruturado num Edge ou num
relógio. Os ficheiros seguem a especificação FIT e são validados (estrutura e
CRC), mas não foram abertos num aparelho Garmin.

**Remo, por confirmar na tua Domyos 500B**: o protocolo foi reimplementado a
partir do que o projeto qdomyos-zwift documenta (sem copiar código, que é
GPLv3). Os pacotes estão testados como o protocolo os descreve, mas nunca
falaram com a máquina. O que pode precisar de afinação: o nível de
resistência que a máquina aceita pelo comando, e se a tua expõe o protocolo
próprio ou o FTMS (as duas coisas estão feitas). O ecrã **Máquina de remo**
mostra ao vivo voga, ritmo e nível — é aí que se vê.

**GarminDB e Strava, por confirmar com as tuas contas**: daqui não há rede
para o Garmin nem para o Strava. A leitura da `garmin.db` está testada com
uma base com as mesmas tabelas; a conversa com o Strava está testada com
respostas no formato da API.

**Limites desta versão**:

- O construtor de força segue a página de ajuda do TrainingPeaks. Essa
  página não tem imagens nem descreve como se registam as séries no
  telemóvel, nem os gráficos da análise; nessas partes, o desenho é meu,
  com o mesmo espírito.
- Não há vídeos dos exercícios: sem rede, a pré-visualização mostra as
  instruções escritas, o grupo muscular e o material.
- A % da 1RM precisa de histórico desse exercício. Sem histórico, a carga
  fica por preencher e escreve-se à mão na sessão.

- O calendário segue o formato mensal habitual do intervals.icu. A imagem
  de referência não chegou; se a mandares, acerto-o por ela.
- A análise do feedback é feita por regras no computador, não pela IA. O
  agente treinador vai ler o mesmo registo quando for ligado.
- No ginásio e no Conditioning, o gráfico «Prescrito e realizado» mostra só
  a FC: os exercícios não têm um alvo de potência.
- A prontidão vem dos pontos de recuperação do HRV4Training. Sem check-ins,
  esse gráfico fica vazio.

- A corrida e a natação ainda não leem sensores; a velocidade e os
  comprimentos entram à mão.
- A Longevidade junta os outros desportos como blocos de tempo dentro do
  treino, não como sessões de bicicleta ou de remo ligadas ao aparelho.
- A volta automática existe no ciclismo, no remo, na corrida, na natação e
  no Conditioning. Nas sessões de séries do ginásio não, porque aí as
  voltas são as próprias séries.
- Com 14 modalidades, a lista de modalidades da janela do Ginásio desloca-se um pouco num
  ecrã de 1024×640.

**Não está incluído**: envio automático para o Strava, Garmin ou
Intervals.icu (o `.fit` fica gravado e envias à mão), o top 15 dos segmentos
(o Strava retirou-o da API), e a versão web (fica para quando criares as
contas).
