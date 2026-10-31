# Perennia

*Perene: que dura ao longo dos anos sem perder a vitalidade.* (Antes:
VeloLocal.)

Aplicação de treino indoor que corre inteiramente offline: ciclismo, remo,
corrida, natação e ginásio. No ciclismo carrega um `.gpx`, pedala essa
estrada em primeira pessoa com o declive real a comandar o trainer, e no fim
guarda um `.fit`.

**Para instalar e correr: [RUN.md](RUN.md).** Começa por
`python main.py --self-test`, que verifica tudo sem precisar de hardware.

```
python main.py --self-test                      # verifica o núcleo
python main.py                                  # abre a aplicação
python -m unittest discover -s tests -t .       # 560 testes
```

**Para partilhar com quem não usa Python:** duplo clique em
`build_windows.bat` cria `dist/Perennia-windows.zip`, uma versão que abre
com duplo clique. Detalhes em [RUN.md](RUN.md), secção 7.

## O que faz

- Liga-se ao trainer e aos sensores por **Bluetooth (FTMS, potência, cardio,
  velocidade/cadência)** e por **ANT+ (FE-C)**, vários ao mesmo tempo, com
  prioridade por métrica — potência dos pedais, cardio da cinta, cadência do
  trainer.
- Envia **declive** em modo de simulação e **watts alvo** em modo ERG, com
  *sensação de declive* ajustável. Dispara o
  **spindown** de calibração.
- Importa `.gpx`, reamostra a 5 m, suaviza a elevação e **deteta as subidas**,
  com placas de início, distância ao topo e fim, cronometragem e
  **classificação local** por subida e por rota.
- Mostra em tempo real distância, falta, declive, declives médios a 500 m /
  1 / 3 / 5 / 10 km, potência, balanço esquerda/direita, zonas, torque,
  cadência, cardio, carga, velocidades e médias — e **o perfil que vem a
  seguir**. Acrescentar uma métrica é escrever uma função.
- **Modo de comparação** contra sessões anteriores, com diferença ao segundo.
- **Treinos estruturados** (`.zwo`, `.mrc`, `.erg`) com ERG ligado ou
  desligado, **teste de FTP** em três protocolos, **desafios** com
  objetivo à escolha (distância ou subida, com decimais) e classificação,
  modo **fuga** contra um pelotão que acelera a cada minuto, classificações
  visíveis em todos os ecrãs e durante a sessão, e **estatísticas** com curva
  de potência, zonas, volume semanal e carga de treino.
- **Construtor de treinos** de ciclismo (passos, rampas, livres, blocos de
  repetição) com **exportação** para `.zwo`, `.erg`, `.mrc` e `.fit`.
- **Força:** planos com séries, repetições, carga, RPE e descanso; sessão com
  FC (banda ou relógio que a transmita, como o Garmin Swim 2 por ANT+);
  histórico, progressão por exercício (1RM estimada) e `.fit` com as séries.
- **Fitness, fadiga e forma** (CTL/ATL/TSB) por desporto e juntos, **FTP
  estimada** (20 min, 60 min ou potência crítica) e **tempo em zona por
  período**.
- **Challenge:** desafio adaptativo à medida da tua FTP e curva de potência
  (o nível evolui de sessão para sessão) e jogos contra bots — Zone Hero,
  Power Ladder, Aquecimento, Eliminação com aspiração e Cabo de guerra.
- **Força livre e Conditioning** por voltas (força, descanso, passadeira com
  a distância calculada pelo visor, cardio), com a FC do relógio.
- **Remo:** Domyos Rowing 500B (Bluetooth, 15 níveis) e máquinas FTMS
  (Concept2 PM5); ecrã com campos à escolha, treinos por tempo ou distância
  com alvo de ritmo, potência ou voga e a resistência posta sozinha,
  construtor, testes (2000 m, 500 m, 30 min, 1 min), Challenge com a Regata
  contra bots, e a volta de remo no Conditioning.
- **Cinco desportos** com o mesmo menu em separadores (Treinar, Construtor,
  Lista de treinos, Histórico, Estatísticas). Corrida em passadeira e
  natação em piscina com dados à mão, `.fit` e treinos.
- **Construtor por blocos**: arrastas blocos de zona para um gráfico e
  mudas a duração e a intensidade com o rato. A vista é por zonas de
  potência, FC, RPE ou ritmo.
- **Ginásio** com 12 modalidades (Força, Pliométricos, Animal Flow, Cardio,
  HIIT, Calisténicos, Argolas, Elásticos, Kettlebell, Sandbag, Longevidade,
  Conditioning). Cada uma tem treino livre (plano primeiro, depois
  começar), treino surpresa e os seus treinos. Acrescentar uma modalidade é
  um bloco no `gym.py`.
- **Construtor de treinos de força por blocos** (como o do TrainingPeaks):
  exercício único, superset, circuito, aquecimento e retorno à calma;
  parâmetros por série (reps, carga, % 1RM, RPE/RIR, tempo, distância,
  descanso); arrastar para reordenar ou juntar; resumo ao vivo. A sessão
  segue a estrutura.
- **Análise pós-treino** da força (cumprimento, reps, volume, 1RM estimada,
  séries prescritas e feitas) e **estatísticas por exercício** (carga,
  1RM, volume, RPE, tempo).
- **Inventário de artigos** (o teu equipamento) e **inventário de
  exercícios** por modalidade, ligado ao equipamento.
- **Barra do topo** com os aparelhos e o estado de cada um, e uma janela de
  dispositivos que funciona a meio da sessão. Avisa quando um aparelho se
  desliga. Também tem Definições (em separadores) e Desligar, que pede
  confirmação.
- **Temas profissionais**, todos sem preto: Perennia (azul-marinho),
  Sálvia, Areia e Ardósia (pouca luz).
- **Objetivo de cada treino e de cada bloco**, com o alvo, num resumo antes
  de começar (gráfico por zonas, repetições agrupadas), e na sessão.
- **Feedback no fim de cada sessão** (RPE, dores, sensação, objetivo
  cumprido, comentário), com «prescrito e realizado» e uma análise que diz
  se a sessão foi proveitosa para o objetivo. Fica guardado para o agente.
- **Editor do ecrã da sessão** de cada desporto: arrastam-se as métricas.
- **Calendário mensal** com sessões, treinos planeados e o resumo de cada
  semana, e **Carga e prontidão** (fitness, fadiga, forma, prontidão, ramp).
- **Volta automática** por tempo ou distância, opcional antes de cada
  treino, e **Terminar sem guardar**.
- **Testes de aptidão** de ciclismo, remo, corrida, natação e longevidade, editáveis.
- **Saúde:** diário com métricas tuas e notas, análises clínicas agrupadas
  por área com o comentário do médico e importação do teu Excel (catálogo de
  parâmetros e intervalos de referência), HRV4Training e Garmin.
- **Sincronização** (Definições): traz os dados do **GarminDB** para a base
  da Perennia — tudo, só o mais recente ou um intervalo de datas, e que
  dados (atividades, monitorização, FC em repouso, HRV, sono, peso).
- **Strava:** os segmentos que cruzam as tuas rotas e os teus PR, com a
  comparação ao vivo durante o passeio (nunca enviados ao agente de IA).
- **Agente de IA preparado** (F1 resumo da página, F2 resumo contextualizado),
  em pré-visualização até ser ligado.
- **Recuperação**: se a aplicação fechar a meio, retoma-se a sessão onde
  estava (ou guarda-se como está).
- Guarda tudo num **único ficheiro SQLite portátil** e escreve um **`.fit`**
  por sessão. Português e inglês. Métrico e imperial.

## Interface

Janela de secretária com menu inicial, biblioteca de rotas, dispositivos,
definições, desafios, estatísticas com gráficos, e o ecrã da sessão: estrada
em 3D em primeira pessoa, HUD com as métricas escolhidas, perfil do que vem
a seguir, placas de subida e diferença para os fantasmas. Navega-se pelo
teclado — setas, Enter, Esc — porque quem está em cima da bicicleta não
chega ao rato; a lista de todas as teclas está em **Definições → Atalhos de
teclado**, e **Ctrl+S** guarda em qualquer ecrã. Não há barras de
deslocamento (as listas continuam em colunas), os botões de ação ficam em
baixo à direita e a data e a hora estão na faixa do topo. **L** marca volta, **P** ou o botão ❚❚ pausa (e pausa sozinho quando paras de pedalar), **F10** ou o botão ■ termina e grava, **F11**
põe em ecrã inteiro. A sessão nunca termina sozinha: ao fim da rota dá a
volta e conta as voltas; só o botão de parar a fecha.

## Estrutura

```
main.py              ponto de entrada e autoteste
velo/core/           lógica — sem interface, sem rádio, inteiramente testada
  db.py              SQLite: esquema, repositórios, portabilidade
  gpx.py             importação, projeção local, reamostragem
  climbs.py          deteção de subidas e placas
  physics.py         modelo do ciclista, declive do trainer, NP, TSS, curva
  route_index.py     elevação, declives futuros, perfil
  metrics.py         registo extensível de métricas
  ride.py            motor da sessão: voltas, subidas, fantasmas, desafios, pausas,
                     ponto de recuperação
  strength.py        força: exercícios, planos, sessão, 1RM estimada, histórico
  workout_export.py  construtor: blocos de repetição, .zwo/.erg/.mrc/.fit
  games.py           modo Challenge: desafio adaptativo e jogos com bots
  laps_session.py    treino livre e Conditioning (voltas)
  fitness_tests.py   testes de aptidão das quatro modalidades
  health.py          diário, métricas, análises clínicas, importação
  labs.py            Excel das análises, catálogo de parâmetros e referências
  importers.py       HRV4Training (formato do export) e a garmin.db do GarminDB
  garmin_sync.py     Sincronização: opções e comando do GarminDB, atividades
  sport_challenges.py Desafios de todos os desportos, com data limite
  segments.py        segmentos do Strava numa rota e o segmento ao vivo
  rowing.py          remo: sessão, treinos, testes, Regata, recuperação
  sports.py          registo dos desportos e volta automática
  intensity.py       % do limiar ↔ W, FC, RPE e ritmo, por desporto
  endurance.py       corrida e natação: treinos, sessão, .fit, recuperação
  gym.py             modalidades do ginásio, exercícios, treino surpresa
  inventory.py       inventário de artigos (equipamento)
  objectives.py      objetivos dos treinos e dos blocos, alvos, resumo
  blocks.py          blocos de um treino (ler/gravar/estimar), para todos os desportos
  feedback.py        feedback no fim da sessão e a análise que o cruza com o objetivo
  layouts.py         que métricas aparecem no ecrã da sessão de cada desporto
  calendar_view.py   calendário mensal, plano por dia e resumos das semanas
  strength_builder.py treinos de força por blocos (superset, circuito…), séries e parâmetros
  strength_analysis.py análise pós-treino da força e histórico de cada exercício
  agent.py           pedidos ao agente de IA (por ligar)
  chase.py           modo fuga: o pelotão que acelera
  boards.py          classificações para os menus e para a sessão
  boxes.py           as 6 caixas de métricas do ecrã da sessão
  zones.py           zonas de potência e FC: intervalos em W, W/kg e bpm
  workout_library.py os 18 treinos que vêm com a aplicação
  naming.py          nome da atividade e do .fit: perennia_<data>_<gpx>
  workouts.py        .zwo/.mrc/.erg e controlo ERG
  ftp.py             protocolos de teste de FTP
  fit.py             codificador .fit escrito do zero
  stats.py           agregações do histórico
  curves.py          curvas suaves para os gráficos (cúbica monótona, escala log)
  i18n.py units.py   traduções e unidades
velo/io/             rádio e sensores
  ble.py             FTMS, Cycling Power, Heart Rate, CSC
  ant.py             FE-C, potência, cardio
  hub.py             fusão de vários sensores por prioridade
  autoconnect.py     liga os aparelhos conhecidos: ANT+ primeiro, Bluetooth de reserva
  sim.py             trainer simulado — usar e testar sem hardware
  rower.py           máquinas de remo: Domyos (protocolo próprio) e FTMS, simulador
  strava.py          Strava: autorização e pedidos (só leitura)
  stall.py           pedais parados que continuam a emitir contam como zero
velo/gfx/            world.py (estrada 3D) · hud.py (HUD e sinalética) · icons.py ·
                     theme.py (temas)
velo/assets/icons/   ícones PNG (refeitos com tools/make_icons.py)
velo/ui/             app.py (ecrãs) · sport_screens.py (força, construtores,
                     Challenge, estatísticas gerais, recuperação) ·
                     health_screens.py (saúde, testes, agente) ·
                     rowing_screens.py (remo) · connect_screens.py (Strava) ·
                     sync_screens.py (Sincronização) · shortcuts.py (atalhos) ·
                     challenge_screens.py (separador Treinar, Challenge da
                     corrida, natação e ginásio) · hub_screens.py (menus dos desportos,
                     inventários) · builder_screens.py (blocos) ·
                     endurance_screens.py (corrida, natação) ·
                     gym_screens.py (modalidades) · stats_screens.py ·
                     brief.py (resumo do treino) · feedback_screens.py ·
                     layout_screens.py (ecrã da sessão) · calendar_screens.py ·
                     load_screens.py (carga e prontidão) ·
                     strength_builder_screens.py · strength_analysis_screens.py ·
                     exercise_stats_screens.py ·
                     widgets.py (inclui a barra do topo e os separadores)
velo/paths.py        onde está a aplicação (script ou executável)
packaging/           receita do PyInstaller e LEIA-ME para os colegas
build_windows.bat    cria a versão para Windows, para partilhar
build.sh             o mesmo, para macOS, Linux e Raspberry Pi
.github/workflows/   o GitHub gera as três versões sozinho
tests/               560 testes: núcleo, protocolos, força, remo, saúde,
                     ligações e interface
  pyglet_stub.py     pyglet falsa, para testar a interface sem ecrã
```
