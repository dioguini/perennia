# Perennia

*Perene: que dura ao longo dos anos sem perder a vitalidade.*

Aplicação de treino indoor que corre inteiramente offline: ciclismo, remo,
corrida, natação e ginásio. No ciclismo carrega um `.gpx`, pedala essa
estrada em primeira pessoa com o declive real a comandar o trainer, e no fim
guarda um `.fit`.

**Para instalar e correr: [RUN.md](RUN.md).** A forma mais fácil é o **`perennia_setup`**
(`perennia_setup.bat` no Windows, `./perennia_setup.sh` no macOS e no Linux): cria o ambiente,
instala os requisitos, cria a pasta `data/` com a base de dados e o conteúdo de base, os modelos,
faz o autoteste e, se quiseres, configura o GarminDB e o atalho.

```
./perennia_setup.sh                             # ou perennia_setup.bat: prepara tudo
python main.py --self-test                      # verifica o núcleo
python main.py                                  # abre a aplicação
python -m unittest discover -s tests -t .       # 1501 testes
```

**Os teus dados ficam todos em `data/`**, dentro da pasta do projeto (e nunca vão para o git):
`data/in/<categoria>` para o que queres importar, `data/out/<categoria>` para o que a Perennia grava
(o `.fit` de cada sessão em `data/out/sessoes/<desporto>`), `data/garmin` para o GarminDB e a base
`data/perennia.db`.

**Sem o PyCharm:** duplo clique em `Perennia.bat` (Windows) ou `./perennia.sh` (macOS, Linux) abre a
aplicação com o ambiente do projeto; `criar_atalho_windows.bat` põe um atalho com ícone no Ambiente de
trabalho. Detalhes em [RUN.md](RUN.md), «Abrir como uma app, sem o PyCharm».

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
- Importa `.gpx` (no menu **Rotas**, o centro das rotas para o ciclismo e a
  corrida, com o perfil de altimetria e as vezes que fizeste cada uma),
  reamostra a 5 m, suaviza a elevação e **deteta as subidas**, com placas de
  início, distância ao topo e fim, cronometragem e **classificação local**
  por subida e por rota.
- **Segmentos** da Perennia (km de início e de fim numa rota) e do Strava,
  com visão geral e melhores tempos; contam sozinhos nas sessões.
- Treinos do computador (`.zwo`, `.fit`, `.mrc`, `.erg`) perguntam se ficam
  na lista; cada sessão guarda a sua cópia do treino.
- **Terminar uma sessão** é igual no ciclismo, na corrida, no remo e no ginásio (Esc pausa e abre o
  aviso PAUSA, F10
  pergunta, Sim / Não / Terminar sem guardar) e abre a janela das **etiquetas** do `.fit`: tipo
  de treino (sugerido pelo esforço nas sessões livres), tipo de sessão (`Perennia` sempre; o
  `Indoor …` do desporto sozinho — `Indoor Cycling`, `Indoor Strength`…; `Virtual …` só quando
  segue um .gpx) e etiquetas livres: escolhe-se uma das que existem ou **cria-se uma nova**.
  Os botões de todas as sessões são os mesmos (− + Pausa Terminar) e **todo o botão tem um
  ícone ao lado da etiqueta — o mesmo para a mesma ação**.
- **Ronda 29** — **Tudo numa pasta `data/`** na raiz do projeto: `data/in/…` (gpx, treinos, planos,
  csv, atividades, analises, hrv4training, trainingpeaks, historico, backups) e `data/out/…` (sessoes
  por desporto, treinos, planos, csv, powerbi, backups, relatorios); cada módulo lê e grava na sua
  pasta e as listas de importação **só procuram em `data/in`** (já não em Transferências); os
  **backups** exportam para `data/out/backups` e repõem-se de `data/in/backups`; os dados das versões
  anteriores são **copiados** na primeira vez. **GarminDB** em `data/garmin`, e **a palavra-passe é
  pedida a cada sincronização e não fica guardada em lado nenhum**. **`perennia_setup`** (`.bat`/`.sh`,
  ou `main.py --setup`) prepara tudo num computador novo — ver «Dar a Perennia a um amigo» no RUN.md.
- **Ronda 28** — **Guia da passadeira manual**: para passadeiras sem ligação (como a NordicTrack T 7.0),
  num treino por blocos a sessão avisa antes de cada mudança («daqui a 8 s · 12,6 km/h · 2,0 %») com
  **quantos toques** dar em cada botão («▲ velocidade ×42 · ▲ inclinação ×4») e um bip; o passo da
  velocidade e o tempo do aviso escolhem-se nas Definições.
- **Ronda 27** — **Glossário das análises** (Saúde): 67 componentes (hemoglobina, ferritina, ácido
  fólico, testosterona, leucócitos…) com o que é, o que faz subir e descer, o que é bom e mau e as
  estratégias para ficar no intervalo (editável, com os teus); **rato por cima** de um resultado mostra
  o resumo (G abre a ficha); **Exportar para o Power BI** (Excel em modelo em estrela + CSV + `.pbids`
  + medidas DAX, pasta fixa para «Atualizar»); **mapa da rota** na sessão (tecla M); e o **segmento ao
  vivo**: a altimetria com o KOM (vermelho), o teu melhor (azul) e tu (rosa), as diferenças no mesmo
  ponto e os W/kg. Base de dados: uma tabela nova (`lab_glossary`), criada sozinha.
- **Ronda 26** — **Tags ao criar treinos**: todos os construtores (blocos, força/ginásio, Conditioning)
  mostram as tags automáticas (desporto, modalidade no ginásio, `Workout`, `Indoor …`) e juntam as tuas;
  saíram os editores sem tags. **Construtor de Conditioning por blocos**: blocos de ciclismo, passadeira,
  remo e ginásio (Manual ou ERG, configurados no construtor do próprio desporto, com «Adicionar bloco a
  treino de Conditioning»), descansos, duplicar e arrastar; na sessão, o passo de cada bloco e a potência
  ERG no rolo. O ciclismo entra no Conditioning (com o seu .fit).
- **Ronda 25** — **Conditioning como agregador**: uma sessão (livre ou um treino) feita de blocos de
  remo, passadeira e ginásio (há agora o «Bloco de ginásio» com tempo). No fim grava **um .fit total e
  um por desporto** (cada um junta tudo o que foi desse desporto). Tags `Conditioning` + uma por desporto,
  e todas as sessões passam a ter a tag do seu desporto. Na Análise AdHoc, a fonte **«Sessões por
  desporto»** reparte o Conditioning, para contar conditioning e corrida/remo/ginásio sem perder a
  noção; os históricos da corrida e do remo mostram o que foi feito dentro de um Conditioning.
- **Ronda 24** — **Tags**: cada sessão, em qualquer desporto, leva o seu tipo (`Free Session`, `Workout`,
  `Challenge` + o nome do jogo, `Test` + o teste) e os **treinos têm tags** próprias (que as sessões herdam).
  As tags são **sempre em inglês**. Na Análise AdHoc há os campos «Tipo de sessão», «Jogo ou teste» e
  «Tags» e o filtro «tem todas / tem alguma / não tem nenhuma» para ir buscar tudo para uma ou mais tags.
  As sessões antigas recebem o tipo sozinhas. Ver o RUN.md.
- **Ronda 23** — **Fim automático das sessões**: quando acaba o último bloco de um treino, um challenge,
  um teste, a fuga ou um plano de voltas (em qualquer desporto; a sessão livre nunca), o tempo pára e
  abre-se o ecrã **«… concluído»** com o menu de guardar ou não, como em «Terminar» (opção
  `session_auto_finish` para desligar). E **todos os textos ficam dentro das caixas** (listas, construtor,
  separadores, métricas, avisos, diálogos), com um teste que os mede em 1024×640 e 1280×760. Ver o RUN.md.
- **Ronda 22** — **Segment Pace** e **Segment KOM** no Challenge: sobre qualquer segmento que já
  tenhas (subida, plano ou descida; também os da biblioteca, offline). No **Pace** dás um alvo (tempo,
  o teu melhor + x % ou potência média) e a Perennia calcula, por física, **os watts de cada secção**
  (mais onde custa mais, a recuperar nas descidas, ± 20 %), com ERG ligado por omissão, **sinal** com os
  watts, guia com a diferença em tempo e recálculo se te atrasas. No **KOM** tentas bater **o meu KOM**
  ou **o KOM do segmento**, em esforço máximo com fantasmas. Avisa se o alvo cabe na tua capacidade,
  começa 500 m antes e termina com a **tabela por secção** (plano × real × tempo ganho/perdido) e
  histórico por segmento. A preparação só pede **o segmento** (uma janela com os da Perennia e os do
  Strava; os da biblioteca sem rota jogam-se num percurso feito com o próprio segmento). Doze opções novas. Ver o RUN.md.
- **Ronda 21** — **Biblioteca de segmentos do Strava**: importa segmentos por **ID ou ligação**, pelos
  **favoritos ⭐**, ou pela pesquisa de uma rota (que se mantém, para rotas noutros países), com o
  traçado, o teu PR e (com subscrição Strava) **todos os teus esforços**. Ficam neste computador e
  **ligam-se sozinhos a cada rota .gpx sem internet**, seguindo o traçado do segmento. Menu
  Segmentos → Biblioteca. Onze opções novas (Avançado → Ligações) e um erro de estabilidade
  corrigido nos trabalhos do Strava. Ver o RUN.md.
- **Ronda 20** — **Métricas de saúde**: adicionar, editar, **descontinuar** (o histórico fica) e
  apagar; perguntas **«se sim, onde?»** que só aparecem quando outra tem essa resposta; filtro por
  grupo no diário; **catálogo de 63 perguntas** (refeições, digestão, sono, rotina, recuperação)
  criado uma só vez e sem duplicar; **importação em massa por CSV** («metricas»); **feedback do
  treino do dia anterior** no topo do diário. Três opções novas (Avançado → Saúde). Ver o RUN.md.
- **Ronda 19** — **Alterar e saltar blocos** durante a sessão (ERG, remo, corrida, ginásio) com o
  **original sempre guardado** para comparar e o que foi feito no bloco saltado; **corrigir as
  repetições, a carga ou os segundos** de qualquer série (planeada ou livre, a decorrer ou
  terminada) sem perder o plano; **complexos de kettlebell** (exercícios feitos de exercícios, com
  evolução por exercício); **~340 exercícios e 25 treinos de força** de origem; **Definições →
  Pastas** (desde a ronda 29 só mostra as pastas fixas de `data/`); **planos de X semanas em CSV** além
  do JSON; **histórico de outras apps** (TrainingPeaks, Strava, Garmin Connect) normalizado por
  **regras** (`--importar historico`, `--historico-normalizar`); **sincronização por Wi-Fi** entre
  duas Perennia (`--sync-receber` / `--sync-enviar`, TLS + PIN de uso único, só rede local);
  **desempenho**: índices na base, cache e gravações mais rápidas. Ver o RUN.md.
- **Ronda 18** — **Glossário** (botão na barra do topo, antes de Dispositivos, ou F9): os termos da
  Perennia, dos ficheiros (.gpx, .fit…), do treino (forma, fadiga, série…) e da saúde, por separadores,
  com adicionar, editar, apagar e repor. **Tamanho da letra** configurável (Definições e janelas de
  sessão, com pré-visualização). **Barra do bloco** (ciclismo, remo, corrida, ginásio em tempo) que
  passa a amarelo, vermelho e preto, configurável; **gráfico ao vivo** configurável por desporto, com
  um traço em cada volta; sem comparação com sessões passadas num treino carregado; **remo** com
  velocidade e remadas totais; **Notas** nos exercícios e artigos; **Fonte** em cada indicador de
  saúde (respeitada pelas sincronizações); sincronização do GarminDB com **requisitos, passos e
  relato ao vivo**; calendário sem diário de saúde no futuro, com **Planear evento** (Treinador) e
  treinos futuros só para ver; o botão de recuar do rato volta atrás; o menu de saída com as opções
  lado a lado; Página ↑/↓ andam nas listas (comandos Bluetooth «apresentador»).
- **Ronda 14** — o aviso **PAUSA** ao centro, em todos os desportos (**Retomar sessão** ou **Terminar
  treino**); **Dispositivos** e **Definições** abrem por cima da sessão e **põem-na em pausa** (nas
  Definições só há o que se pode mexer: *Geral → passos seguintes*, o separador do desporto da sessão,
  *Ecrã e idioma → tema, unidades e idioma*, os atalhos e os bips); os atalhos de **volta, pausa,
  terminar e começar sem contagem são um só para todos os desportos**, com **saltar bloco** em todos,
  **velocidade e declive** na corrida e **resistência** no remo; no **ginásio** já não há cronómetro
  no topo nem RPE, as séries por tempo contam para trás (na métrica *Série / descanso* ou num aviso ao
  centro), o descanso é a única linha por baixo de cada exercício e traz o tempo, e o **Saltar** passou
  a funcionar a meio de uma série; **abre-se como uma app**, sem o PyCharm (`Perennia.bat`,
  `perennia.sh`, o atalho com ícone e o `Perennia.exe`). Base de dados: nada a fazer — o `keymap`
  antigo (um atalho por desporto) é unificado ao abrir, e também nos backups antigos.
- **Ronda 13** — a janela de **Dispositivos** tem um bloco por ligação (**Bluetooth**, **ANT+** e
  **SEM HARDWARE**): os aparelhos encontrados ficam por baixo da sua ligação, os ligados levam o ✓ e
  os valores ao vivo, e no fim há a lista informativa dos **Dispositivos ligados**; a **corrida livre**
  tem, ao meio do ecrã, os cartões **Velocidade** (de 0,1 em 0,1 km/h) e **Inclinação** (de 0,5 em
  0,5 %), com a escolha **registada ao segundo** para a análise do treino (e no `.fit`); a corrida e o
  remo já não têm o contador do topo nem textos repetidos — o **tempo total** e o **tempo da volta**
  são métricas — e a letra das voltas é maior; os treinos de ciclismo ficam, por agora, com o fundo da
  cor do tema (sem 3D); a **Disposição dos painéis** do ginásio abre o ecrã do ginásio; e a linha
  «Número de métricas no ecrã» saiu das Definições. Base de dados: uma coluna nova
  (`endurance_samples.incline_pct`), acrescentada sozinha.
- **Ronda 12** — as **Configurações sonoras** (Definições): bips para os primeiros/últimos N
  segundos de um bloco, de uma série ou de um descanso (por exemplo, os últimos 5 s com 2 bips por
  segundo), e os últimos 5 segundos **sempre à vista** (a caixa do tempo pisca); ao acabar o **último
  bloco** de um treino, o tempo pára e abre-se o diálogo de terminar; o **calendário** só planeia de
  hoje para a frente (num dia passado carrega-se o ficheiro de treino); no **Ginásio**, a sessão
  começa sozinha após os 15 s com um botão **Lap**, o treino é uma lista com as repetições e a carga
  à frente de cada exercício e o seu descanso, e o **Treino livre** é só uma lista de exercícios:
  marcas as voltas com Lap, abre-se a janela das repetições e, depois, edita-se o que faltou; o
  botão **Começar treino** fica em baixo, à direita.
- **Ronda 11** — o **Backups** é agora **Backups e Sincronização**, com três separadores
  (**Exportar**, **Repor** e **Sincronização**, que saiu das Definições); a Sincronização ganhou
  o separador **Saúde** (importa um .csv do diário por data, com modelo para descarregar); o
  **calendário** do ecrã inicial tem seletor de datas e, ao escolher um dia, uma janela com a
  nota, o diário de saúde e **Planear treino** (desporto → de onde vem o treino: lista,
  computador ou construtor; num dia passado, carregar um .fit ou sincronizar a HRV e os dados de
  saúde); a ficha de qualquer treino tem o botão **Planear**; o ciclismo ganhou a análise do
  **decoupling** (Pa:HR) nas estatísticas; a **fórmula da Longevidade** vê-se, edita-se e pode
  receber parâmetros novos; todos os desportos mostram *atleta · FTP · LTHR* por baixo do
  título (o ginásio não); e o **Ginásio** perdeu a modalidade Longevidade, escolhe a modalidade
  na mesma janela da sessão (treino livre, surpresa, carregar, por blocos, do computador,
  Challenge e Testes), configura a sessão numa janela (com o auto lap bloqueado, porque é a
  cada bloco) e a sessão de força mostra o treino **numa lista** (Enter começa a série).
- **Longevidade**: um índice (0–100) para 1 dia … 20 anos, com a tendência e um **radar**
  de onde o corpo tem estado mais ou menos concentrado; cada sessão mostra o seu radar (o que
  treinou) e o que acrescentou ao índice, e o construtor mostra o impacto do treino antes de o
  fazeres. Os testes de longevidade vivem aqui.
- **GPX Conversor**: de um percurso .gpx para um treino manual (níveis do rolo, inclinação e
  velocidade da passadeira), com média móvel, troços e várias fórmulas.
- **Exercícios** com grupos e subgrupos musculares, modalidades novas (Mobilidade, Tendões,
  Isométrico) e disciplinas que crias tu (cada uma ganha o seu separador).
- **CSV**: modelos, exportação e importação de artigos, exercícios, grupos musculares,
  disciplinas e testes (Backups e Sincronização → Sincronização → CSV, ou `--csv-modelo`,
  `--csv-exportar` e `--importar csv`); e, no separador **Saúde**, o diário por data (`--csv-modelo
  saude`, `--importar saude`).
- **Backups e Sincronização**: tudo, ou só algumas componentes, num `.zip`
  segmentado (uma pasta por componente, um `.jsonl` por tabela, os `.fit`);
  repor é arrastar o ficheiro para a janela (substituir ou juntar), com um
  backup automático antes; e a **Sincronização** (GarminDB, HRV4Training, Análises, TrainingPeaks,
  Upload manual, CSV e Saúde). Abre-se no botão **Backups e Sincronização** da barra do topo.
  Também por `--backup` / `--restore`, e as importações por `--importar`. Sincronização Wi-Fi entre duas Perennia no separador **Wi-Fi**
  (ou `--sync-receber` / `--sync-enviar`).
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
- **Fitness, fadiga e forma** (CTL/ATL/TSB) **calculados como no
  TrainingPeaks/WKO (Coggan)** — constantes de 42 e 7 dias, forma do dia
  anterior, TSS no ciclismo, **rTSS** na corrida e
  **sTSS** na natação, atividades importadas sem contar duas vezes — por
  desporto e juntos, **FTP
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
  mudas a duração e a intensidade com o rato. Cada treino novo é **ERG**
  (o aparelho segue o treino sozinho) ou **Manual** (a sessão mostra o que
  pôr no aparelho). Ciclismo ERG: zonas de potência; manual: FC, RPE ou
  **níveis do rolo** (definidos em Definições → Desportos → Sessões Não ERG). Corrida: ritmo,
  e no manual a velocidade e a inclinação da passadeira. Remo: potência,
  ritmo, resistência e voga. Cada bloco tem cadência alvo e alvo exato ou
  com margem (± %); a paleta mostra o nome e o intervalo de cada zona e
  acaba no **Free ride** (sem alvo). Cada bloco mostra ao centro a zona, o
  valor (numa rampa, a média), a duração e a cadência. As listas de treinos
  mostram a definição e o tipo («Potência · ERG») e são iguais em todos os
  desportos, com **+ Novo treino** em baixo.
- **«Sessão de treino» numa só janela** (ciclismo, corrida, remo, e as
  modalidades no ginásio): escolhes o modo — *Livre*, *Carregar treino*,
  *Do computador*, *Challenge* ou *Testes* — na mesma janela (grande), e a
  seguir a preparação. A natação não tem sessão de treino. Na preparação:
  aparelhos (emparelhar), rota `.gpx` (uma tua ou uma nova; obrigatória na
  sessão livre de ciclismo, opcional no resto), segmentos do Strava da rota,
  modo (sozinho ou comparação), ERG, auto lap. Se o Strava não responder
  (sem internet), aparece um aviso e escolhes prosseguir sem os segmentos ou
  cancelar. A ficha de cada treino mostra o gráfico com os objetivos por
  baixo e, em baixo à direita, **Configurar sessão de treino**. Na corrida
  com uma rota, a sessão diz a inclinação da estrada a pôr na passadeira.
- **Análise de cada sessão** (todos os desportos), em separadores: **Geral**
  (com o tipo de sessão — livre, treino e o tipo do treino, teste,
  Challenge), **Feedback** (o próprio ecrã), **Análise do treino** (cada
  bloco: alvo, feito, tempo no alvo, cumprido ou não; no ginásio, cada
  exercício) e **Infográficos** (o gráfico da sessão com os blocos e o alvo
  por baixo; no ciclismo também o relatório à maneira do TrainingPeaks — NP,
  IF, TSS, VI, EF, desacoplamento —, a curva de potência, as zonas e os
  picos).
- **Janelas quando se justificam**: apagar pergunta sempre; voltar atrás
  com alterações pergunta (Sair sem guardar · Cancelar · Sair e guardar);
  guardar um treino diz «Treino guardado».
- **Estatísticas** com o separador **Geral** primeiro (resumo de cada
  desporto e o total) e **Picos** no ciclismo (melhor potência, FC, cadência
  e velocidade em cada duração). Entrando por um desporto, o desporto fica
  fixo.
- **Ginásio** com as modalidades Força, Pliométricos, Animal Flow, Cardio,
  HIIT, Calisténicos, Argolas, Elásticos, Kettlebell, Sandbag, Mobilidade, Tendões,
  Isométrico e Conditioning (a Longevidade saiu: o índice tem o seu menu). Cada uma tem treino livre (plano primeiro, depois
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
- **Métricas de evolução** (separadas das **métricas de sessão**, as do
  ecrã do treino): forma e fadiga; na corrida, **fator de eficiência,
  desacoplamento ritmo:FC e durabilidade**, **avisos de progressão da carga**
  (corrida longa +10 %, volume semanal +10 %), **previsões de prova**
  (Riegel e Tanda) e **zonas de ritmo** (80/20, Friel, Daniels); e a
  **prontidão** pela HRV, FC em repouso e sono face à tua linha de base.
- **Inventário de artigos** (o teu equipamento, com data e preço de compra
  e a lista completa com o valor gasto) e **inventário de
  exercícios** por modalidade, ligado ao equipamento.
- **Pesquisa na barra do topo** (sempre no mesmo sítio, Ctrl+F), **mensagens**
  a bold ao centro do título, e o calendário maior no ecrã inicial, com as
  próximas atividades à esquerda.
- **Métricas do ecrã da sessão** à tua escolha (1 até ao máximo do desporto, no editor
  «Escolher as métricas do ecrã»): a sessão de corrida, remo e ginásio desenha-as sozinha.
- **Upload manual** de uma atividade (.fit ou .tcx): vês o que o ficheiro tem
  e guardas no desporto respetivo; os testes têm a lista de resultados e
  janelas para registar, editar e apagar; qualquer treino se **exporta**
  (nome e formato, para `data/out/treinos`).
- **Barra do topo** com os aparelhos e o estado de cada um, e uma janela de
  dispositivos que funciona a meio da sessão. Avisa quando um aparelho se
  desliga. Também tem Backups e Sincronização, Definições (em separadores: Atleta, Geral,
  **Desportos** — métricas de sessão, disposição do ecrã e limites Não ERG
  de cada desporto, que o construtor respeita —, Ecrã e idioma, Ligações
  Externas, Atalhos) e Desligar, que pede confirmação.
- **Contagem de 15 s** antes de qualquer sessão; nos treinos estruturados,
  uma volta por bloco (sem auto lap).
- **Atalhos de teclado personalizáveis**, por contexto.
- **Temas profissionais** (vê-se logo; grava-se com Guardar), todos sem preto: Perennia (azul-marinho),
  Sálvia, Areia e Ardósia (pouca luz).
- **Objetivo de cada treino e de cada bloco**, com o alvo, num resumo antes
  de começar (gráfico por zonas, repetições agrupadas), e na sessão.
- **Feedback no fim de cada sessão** (RPE, dores, sensação, objetivo
  cumprido, comentário), com «prescrito e realizado» e uma análise que diz
  se a sessão foi proveitosa para o objetivo. Fica guardado para o agente.
- **Editor do ecrã da sessão** de cada desporto: arrastam-se as métricas.
  E a **disposição** é tua: caixas, voltas, classificação, plano, gráfico
  ao vivo e tabelas arrastam-se e redimensionam-se numa grelha.
- **Calendário no ecrã inicial** com sessões e treinos planeados; num dia
  planeias um treino, escreves a nota do dia ou preenches o diário de
  saúde. **Carga e prontidão** (fitness, fadiga, forma, prontidão, ramp).
- **Volta automática** por tempo ou distância, opcional antes de cada
  treino, e **Terminar sem guardar**.
- **Testes de aptidão** de ciclismo, remo, corrida, natação e longevidade,
  editáveis. Os do rolo e da máquina de remo abrem a janela da sessão em
  **Configurar sessão** (Enter); o resultado vem da própria sessão.
- **Saúde** em separadores (Análises, Diários, Tendências, Métricas):
  diário com métricas tuas e notas (a **+ Nova métrica** fica em baixo, à
  direita); as **análises clínicas** — a lista das colheitas e, dentro de uma
  colheita, os resultados com o valor atual e os 3 anteriores, o comentário do
  médico de cada análise e, em baixo, o **Comentário geral do médico** — e a
  importação do teu Excel (catálogo de parâmetros e intervalos de
  referência), HRV4Training e Garmin.
- **Sincronização** (Backups e Sincronização), com separadores **HRV4Training (.csv)**,
  **Análises (.csv)** e **TrainingPeaks (.csv de atividades**, com a TSS),
  e o **GarminDB**, que traz os dados para a base
  da Perennia — tudo, só o mais recente ou um intervalo de datas, e que
  dados (atividades, monitorização, FC em repouso, HRV, sono, peso).
- **Strava:** os segmentos que cruzam as tuas rotas e os teus PR, com a
  comparação ao vivo durante o passeio (nunca enviados ao agente de IA).
- **Planos de treino de X semanas** (Ginásio → Lista de treinos): 31 planos —
  StrongLifts 5×5, Starting Strength, Texas Method, Madcow, 5/3/1, GZCLP, Smolov
  Jr, Push/Pull/Legs, força de mãos, sandbag, Simple & Sinister… Ao começar um,
  as sessões vão todas para o **calendário** com as cargas de cada semana, e é só
  fazer a do dia. **Importas os teus** no formato Perennia
  (`*.perennia-plan.json`); há um **ficheiro modelo** e a descrição do formato
  (`modelos/in/planos/`, copiados para `data/in/planos`).
- **Perfil por desporto** (separador «Perfil» em cada desporto): no ciclismo, que
  **tipo de ciclista** és (sprinter, puncheur, trepador, rolador, completo) pela
  curva de potência; no ginásio, o teu **perfil de força** (força máxima,
  relativa, de mãos, tendões, explosividade, mobilidade, tronco,
  condicionamento) com as deficiências e o plano que as trata. As capacidades
  para a vida continuam na Longevidade.
- **Treinador** (cartão no ecrã inicial): avalia cada treino no fim da sessão;
  **planeia um evento numa data** (uma volta com o .gpx, a velocidade média e a
  hora de partida; ou um evento de força, como «200 flexões e 50 elevações em
  5 min») com perguntas, viabilidade, fases, alimentação e hidratação, e põe as
  sessões no calendário; dá **feedback a um desafio** (longe/perto, pergunta a
  importância e ajusta os treinos); propõe o **caminho para a longevidade** a
  partir das tuas fraquezas; sugere o treino e os comportamentos de **hoje**;
  **programa um treino no construtor** e dá **feedback a um treino construído**
  à luz da tua forma (com versão mais leve e veredicto ao vivo depois de pedires).
- **Assistente de saúde** (separador da Saúde): avaliação geral e por componente
  (análises, pressão arterial, recuperação e sono, corpo, hábitos, sinais do
  treino, as tuas notas). O que existe para o médico fica como estava. Não faz
  diagnósticos.
- **Aconselhamento em três modos**, para as duas figuras: **regras da Perennia**
  (offline, funciona já), **LLM local** (offline) e **agente online** (Claude,
  ChatGPT, Gemini…) — estes dois preparados e por ligar: mostram o pedido, os
  **tokens**, a janela do modelo local ou o custo, e os dados partilhados antes
  de qualquer envio. A chave vem só de uma variável de ambiente.
- **Pressão arterial:** várias medições por dia, por período (manhã, tarde,
  noite ou os teus); cada período tem a sua média e o dia tem a média diária.
- **Separadores da Saúde criados por ti**, sempre com Notas (como as
  disciplinas do ginásio).
- **AdHoc Analysis** (último separador das Estatísticas gerais): o centro
  exploratório. Escolhes a fonte (sessões, séries de força, diário, análises
  clínicas, testes), filtras, e ou **exportas um .csv** (com o nome do
  ficheiro, o separador de valores e o decimal à tua escolha) ou montas um
  **gráfico dinâmico** ao estilo Power BI (eixo X, valor, agregação, legenda,
  colunas, empilhadas, linhas ou dispersão). As vistas guardam-se. Também
  existe na linha de comandos: `python main.py --adhoc-exportar sessions`.
- **Definições → Avançado:** os valores que antes estavam fixos no código
  (contagem antes da sessão, pausa automática, tolerâncias dos treinos, passos
  do ginásio, porta do Strava, tokens do agente, limites da AdHoc…) são
  opções, cada uma com limites e valor por omissão; entram nos backups.
- **Agente de IA preparado** (F1 resumo da página, F2 resumo contextualizado),
  em pré-visualização até ser ligado. Antes de enviar mostra uma **estimativa
  dos tokens** (e do custo, se puseres os preços), com aviso acima de um limite.
- **Segurança:** a palavra-passe do Garmin é **pedida a cada sincronização e não fica guardada
  em lado nenhum** (vai ao GarminDB por um ficheiro temporário privado, apagado no fim); os dados do
  Strava vêm de **variáveis de ambiente** (`PERENNIA_STRAVA_CLIENT_ID`,
  `PERENNIA_STRAVA_CLIENT_SECRET`) e nunca ficam num ficheiro nem na linha de comandos; a pasta
  `data/` (os teus dados) nunca vai para o git; a base tem permissões só do dono;
  `.gpx/.zwo/.tcx` lêem-se sem DTD; os backups não escrevem fora da pasta de
  dados. Detalhes em [RUN.md](RUN.md), «Segurança e segredos».
- **Se vinhas de uma versão anterior** não tens de fazer nada: na primeira abertura os dados
  da pasta antiga (e o GarminDB de `~/.GarminDb`/`~/HealthData`, sem a palavra-passe) são
  **copiados** para `data/`, com os caminhos corrigidos; os originais ficam (ver [RUN.md](RUN.md),
  secção 8).
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
baixo à direita, a pesquisa fica em cima à direita, e a data e a
hora estão na faixa do topo. Acrescentar ou editar (artigos, exercícios,
desafios, testes, passos) abre uma janela com **Cancelar · Guardar · Guardar
e sair**; o Guardar só acende quando há alterações, e sair com alterações
pergunta *Sair sem guardar · Cancelar · Sair e guardar*. **Enter nunca muda
valores sozinho**: numa escolha abre uma **lista com pesquisa** (escreves para filtrar: não se
percorre um exercício a exercício com as setas) e numa
data o **seletor de datas**; **←/→** passam ao valor seguinte e continuam a mudar números. Todos os
separadores têm **pesquisa** no canto superior direito (Ctrl+F), que filtra
enquanto escreves; todos os botões de ação ficam em baixo à direita. Os títulos das listas ficam numa
faixa sombreada e as setas saltam-nos; a descrição de cada opção fica à
frente dela (nas listas grandes, como a dos exercícios, fica por baixo). Na
janela da sessão, a rota escolhe-se numa lista das tuas rotas `.gpx`. Os
aparelhos de experiência chamam-se **SEM HARDWARE - Trainer** e **SEM
HARDWARE - Remo**. **L** marca volta, **P** ou o botão ❚❚ pausa (e abre o aviso **PAUSA**; no ciclismo pausa sozinho quando paras de pedalar), **N** salta o bloco, **F10** ou o botão ■ termina e grava, **F11**
põe em ecrã inteiro (as mesmas teclas em todos os desportos). A sessão nunca termina sozinha: ao fim da rota dá a
volta e conta as voltas; só o botão de parar a fecha.

## Estrutura

```
main.py              ponto de entrada, autoteste e exportação AdHoc (--adhoc-exportar)
perennia/datadir.py      a pasta data/ do projeto e a cópia (uma vez) dos dados das versões anteriores
perennia/install.py      a instalação num computador novo (main.py --setup, o perennia_setup)
perennia/legacy.py       o único sítio que conhece o nome antigo (migração automática)
perennia/core/           lógica — sem interface, sem rádio, inteiramente testada
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
  workout_meta.py    tipo de cada treino (ERG ou Manual), níveis do rolo, extras dos blocos
  screen_layout.py   a disposição do ecrã da sessão: onde fica cada painel (grelha 24 × 16)
  session_review.py  análise de uma sessão feita: tipo, cumprimento de cada bloco, séries
  peaks.py           picos (melhores médias por duração) e o relatório de uma sessão
  feedback.py        feedback no fim da sessão e a análise que o cruza com o objetivo
  layouts.py         que métricas aparecem no ecrã da sessão de cada desporto
  calendar_view.py   calendário mensal, plano por dia e resumos das semanas
  strength_builder.py treinos de força por blocos (superset, circuito…), séries e parâmetros
  strength_analysis.py análise pós-treino da força e histórico de cada exercício
  agent.py           pedidos ao agente de IA (por ligar), estimativa de tokens e custo
  advice.py          o formato comum do que o Treinador e o Assistente dizem
  advisor.py         regras / LLM local / agente online: o pedido e os tokens (sem chamadas)
  coach.py           o Treinador: sessão, eventos, desafios, longevidade, hoje, construtor
  health_assistant.py  o Assistente de saúde: avaliação geral e por componente
  bp.py              pressão arterial: medições, médias por período e diária
  programs.py        planos de X semanas: formato, validação, calendário, cargas
  program_library.py os planos que vêm com a aplicação e o ficheiro modelo
  profile.py         perfil por desporto: tipo de ciclista, perfil de força
  health_tabs.py     separadores da Saúde criados por ti, com notas
  block_log.py       blocos alterados e saltados, com o original e o feito
  complexes.py       complexos de kettlebell: exercícios feitos de exercícios, evolução
  gym_catalog.py     os exercícios e treinos de força que vêm com a aplicação (catálogo)
  folders.py         as pastas de data/: in/<categoria>, out/<categoria>, garmin/ (fixas)
  plan_csv.py        planos de X semanas em CSV (a via fácil, além do JSON)
  history_etl.py     histórico de outras apps: importar e normalizar com regras
  lan_sync.py        sincronizar duas Perennia pelo Wi-Fi (fonte → destino, TLS + PIN)
  indexes.py         índices de leitura da base de dados (desempenho)
  options.py         registo único das opções afináveis (Definições → Avançado)
  adhoc.py           AdHoc Analysis: fontes, filtros, agregação, gráfico, .csv
  safexml.py         leitura de XML de fora sem DTD nem entidades
  chase.py           modo fuga: o pelotão que acelera
  boards.py          classificações para os menus e para a sessão
  boxes.py           as 6 caixas de métricas do ecrã da sessão
  zones.py           zonas de potência e FC: intervalos em W, W/kg e bpm
  workout_library.py os 18 treinos que vêm com a aplicação
  naming.py          nome da atividade e do .fit: perennia_<data>_<gpx>
  workouts.py        .zwo/.mrc/.erg e controlo ERG
  ftp.py             protocolos de teste de FTP
  fit.py             codificador .fit escrito do zero
  stats.py           agregações do histórico; CTL/ATL/TSB como o TrainingPeaks
  tss.py             rTSS (corrida) e sTSS (natação), velocidade normalizada
  evolution.py       métricas de evolução: EF, desacoplamento, durabilidade,
                     avisos de carga, previsões, zonas de ritmo, prontidão
  tp_import.py       .csv de atividades do TrainingPeaks
  file_import.py     as importações de ficheiros (ecrã e --importar)
  tags.py            etiquetas das sessões e tipos de treino (sugestão pelo esforço, .fit)
  longevity.py       índice de longevidade, eixos, radar, impacto de uma sessão, fórmula editável
  cues.py            os avisos sonoros e visíveis do fim de um bloco, série ou descanso
  shortcuts.py       os atalhos antigos (um por desporto) → os de agora; serve à base e aos backups
  health_csv.py      o diário de saúde em .csv (modelo, exportação, importação por data)
  strength_import.py treinos de ginásio de um .csv, .json, .txt ou .fit (TrainingPeaks…)
  gpx_convert.py     GPX Conversor: percurso → níveis do rolo / inclinação da passadeira
  muscles.py         grupos e subgrupos musculares
  csv_sync.py        modelos, exportação e importação em CSV
  fit_decode.py      leitor de .fit (o contrário de fit.py)
  activity_upload.py upload manual de uma atividade (.fit, .tcx)
  workout_download.py exportar um treino de qualquer desporto
  curves.py          curvas suaves para os gráficos (cúbica monótona, escala log)
  i18n.py units.py   traduções e unidades
perennia/io/             rádio e sensores
  ble.py             FTMS, Cycling Power, Heart Rate, CSC
  ant.py             FE-C, potência, cardio
  hub.py             fusão de vários sensores por prioridade
  autoconnect.py     liga os aparelhos conhecidos: ANT+ primeiro, Bluetooth de reserva
  sim.py             trainer simulado — usar e testar sem hardware
  rower.py           máquinas de remo: Domyos (protocolo próprio) e FTMS, simulador
  sound.py           os bips (um tom gerado em memória; sem som, o beep do terminal)
  strava.py          Strava: autorização e pedidos (só leitura)
  stall.py           pedais parados que continuam a emitir contam como zero
perennia/gfx/            world.py (estrada 3D) · hud.py (HUD e sinalética) · icons.py ·
                     theme.py (temas)
perennia/assets/icons/   ícones PNG (refeitos com tools/make_icons.py)
perennia/ui/             app.py (ecrãs) · sport_screens.py (força, construtores,
                     Challenge, estatísticas gerais, recuperação) ·
                     health_screens.py (saúde, testes, agente) ·
                     rowing_screens.py (remo) · connect_screens.py (Strava) ·
                     sync_screens.py (Sincronização) · evolution_screens.py
                     (métricas de evolução) · pickers.py (lista com pesquisa
                     e seletor de datas) · upload_screens.py (upload e
                     exportar) · goal_popup.py (objetivos) · keymap.py (atalhos
                     personalizáveis) · arrangement_screens.py (disposição) ·
                     session_panels.py (painéis das sessões) ·
                     session_flow.py (terminar sessões) · tag_popup.py (etiquetas) ·
                     longevity_screens.py · session_radar.py · radar.py (radar) ·
                     gpx_convert_screens.py · muscle_screens.py · csv_screens.py ·
                     challenge_screens.py (separador Treinar, Challenge da
                     corrida, natação e ginásio) · hub_screens.py (menus dos desportos,
                     inventários) · builder_screens.py (blocos) ·
                     endurance_screens.py (corrida, natação) ·
                     gym_screens.py (modalidades) · stats_screens.py ·
                     brief.py (ficha do treino) · session_analysis.py (a
                     análise de uma sessão, em separadores) · session_setup.py (a janela
                     que prepara a sessão) · ride_report_screens.py
                     (infográficos) · feedback_screens.py ·
                     layout_screens.py (ecrã da sessão) · calendar_screens.py ·
                     day_popups.py (a janela do dia e o planear) · sound_screens.py (configurações sonoras) ·
                     load_screens.py (carga e prontidão) ·
                     strength_builder_screens.py · strength_analysis_screens.py ·
                     exercise_stats_screens.py · adhoc_screens.py (AdHoc Analysis) ·
                     option_screens.py (Definições → Avançado) ·
                     coach_screens.py (Treinador) · advice_screens.py (conselhos e pedido ao LLM) ·
                     health_extra_screens.py (pressão arterial, separadores, assistente) ·
                     program_screens.py (planos de X semanas) · profile_screens.py (Perfil) ·
                     widgets.py (inclui a barra do topo e os separadores)
perennia/paths.py        onde está a aplicação (script ou executável)
packaging/           receita do PyInstaller, ícone (.ico), atalho do Windows e LEIA-ME para os colegas
perennia_setup.bat   instala e prepara tudo num computador novo (Windows); perennia_setup.sh no macOS e no Linux
Perennia.bat         abre a aplicação sem o PyCharm (Windows); perennia.sh no macOS e no Linux
modelos/             os ficheiros modelo copiados para data/in na primeira vez (LEIA-ME, .gpx, .zwo, planos)
data/                OS TEUS DADOS (criada sozinha; nunca vai para o git): perennia.db, in/, out/, garmin/
criar_atalho_windows.bat  o atalho «Perennia», com ícone, no Ambiente de trabalho
build_windows.bat    cria a versão para Windows (Perennia.exe), para partilhar
build.sh             o mesmo, para macOS, Linux e Raspberry Pi
tools/                make_icons.py (ícones dos botões) · make_app_icon.py (o ícone da aplicação)
.github/workflows/   o GitHub gera as três versões sozinho
tests/               1501 testes: núcleo, protocolos, força, remo, saúde,
                     ligações e interface
  pyglet_stub.py     pyglet falsa, para testar a interface sem ecrã
```
