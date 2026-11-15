"""Os termos de origem do Glossário, nos dois idiomas, por separador.

Cada termo é `(chave, termo_pt, termo_en, definição_pt, definição_en)`. A chave é estável:
é por ela que uma edição tua (ou um termo apagado) se liga ao termo de origem, por isso
nunca a mudes — para acrescentar um termo, junta uma linha com uma chave nova.

Os termos que acrescentas tu ficam na base de dados (tabela `glossary`), não aqui.
"""
from __future__ import annotations

# separador: (chave, pt, en)
TABS: tuple[tuple[str, str, str], ...] = (
    ("perennia", "Perennia", "Perennia"),
    ("files", "Ficheiros e formatos", "Files and formats"),
    ("training", "Conceitos de treino", "Training concepts"),
    ("gym", "Ginásio", "Gym"),
    ("sports", "Ciclismo, remo e corrida", "Cycling, rowing and running"),
    ("health", "Saúde", "Health"),
)

TERMS: dict[str, tuple[tuple[str, str, str, str, str], ...]] = {
    "perennia": (
        ("app.session", "Sessão", "Session",
         "Um treino feito do princípio ao fim, num desporto. Fica guardada no histórico com as "
         "amostras (uma por segundo), as voltas e o resumo.",
         "One workout done from start to finish, in one sport. It is saved in the history with "
         "its samples (one per second), laps and summary."),
        ("app.workout", "Treino", "Workout",
         "Uma sequência de blocos (aquecimento, intervalos, recuperação…) que a Perennia "
         "conduz por ti. Pode ser criado aqui, importado (.zwo, .erg, .mrc, .fit) ou vir de "
         "um plano.",
         "A sequence of blocks (warm-up, intervals, recovery…) that Perennia runs for you. It "
         "can be built here, imported (.zwo, .erg, .mrc, .fit) or come from a plan."),
        ("app.block", "Bloco", "Block",
         "Cada passo de um treino: tem uma duração (tempo ou distância) e um alvo (potência, "
         "ritmo, frequência cardíaca…). A barra horizontal da sessão mostra o tempo que falta "
         "no bloco atual.",
         "Each step of a workout: it has a duration (time or distance) and a target (power, "
         "pace, heart rate…). The horizontal bar of the session shows the time left in the "
         "current block."),
        ("app.block_bar", "Barra do bloco", "Block bar",
         "A barra no topo da sessão que se esvazia ao longo do bloco. Quando falta pouco passa "
         "a amarelo, depois a vermelho e, nos últimos instantes, a preto. Os limites estão em "
         "Definições → Avançado.",
         "The bar at the top of the session that empties along the block. When little is left "
         "it turns yellow, then red and, in the last moments, black. The thresholds are in "
         "Settings → Advanced."),
        ("app.free", "Sessão livre", "Free session",
         "Uma sessão sem treino carregado: pedalas, remas ou corres ao teu ritmo. É a única "
         "em que o ciclismo permite comparar com uma sessão passada, e só com uma rota .gpx "
         "escolhida.",
         "A session with no workout loaded: you ride, row or run at your own pace. It is the "
         "only one where cycling allows comparing with a past session, and only with a .gpx "
         "route chosen."),
        ("app.compare", "Comparação", "Comparison",
         "No ciclismo, correres contra uma sessão tua anterior na mesma rota (o «fantasma»). "
         "Só existe em sessão livre com uma rota .gpx.",
         "In cycling, racing against an earlier session of yours on the same route (the "
         "'ghost'). It only exists in a free session with a .gpx route."),
        ("app.route", "Rota", "Route",
         "Um percurso importado de um ficheiro .gpx: pontos, distância, perfil de altitude e "
         "subidas. A Perennia ajusta a resistência do rolo ao declive.",
         "A course imported from a .gpx file: points, distance, elevation profile and climbs. "
         "Perennia adjusts the trainer's resistance to the gradient."),
        ("app.segment", "Segmento", "Segment",
         "Um troço de uma rota com tempo cronometrado, para comparares as tuas passagens. "
         "Há os da Perennia (marcados por ti) e os do Strava (importados).",
         "A stretch of a route that is timed so you can compare your passes. There are "
         "Perennia's (marked by you) and Strava's (imported)."),
        ("app.climb", "Subida", "Climb",
         "Um troço contínuo a subir que a Perennia deteta na rota. Cada vez que o fazes fica "
         "registado o tempo e a potência.",
         "A continuous uphill stretch that Perennia detects in the route. Each time you ride it "
         "the time and power are recorded."),
        ("app.lap", "Volta", "Lap",
         "Uma marca no tempo da sessão (manual ou automática por tempo ou distância). Nos "
         "gráficos ao vivo aparece como um traço vertical.",
         "A mark in the session's time (manual or automatic by time or distance). In the live "
         "charts it shows as a vertical tick."),
        ("app.auto_lap", "Volta automática", "Auto lap",
         "A sessão marca uma volta sozinha a cada X minutos ou X quilómetros, conforme "
         "escolheres antes de começar.",
         "The session marks a lap by itself every X minutes or X kilometres, as you choose "
         "before starting."),
        ("app.plan", "Plano", "Plan",
         "Um conjunto de treinos distribuídos por dias e semanas (por exemplo, 8 semanas de "
         "base). Os dias planeados aparecem no calendário.",
         "A set of workouts spread over days and weeks (for example, 8 weeks of base). The "
         "planned days show in the calendar."),
        ("app.calendar", "Calendário", "Calendar",
         "O mês com o que fizeste, o que planeaste, as notas do dia, os eventos do Treinador e "
         "o diário de saúde. Não se regista saúde em dias futuros.",
         "The month with what you did, what you planned, day notes, the Coach's events and the "
         "health diary. Health is not logged on future days."),
        ("app.coach", "Treinador", "Coach",
         "O menu onde marcas eventos (provas, objetivos) e recebes ajuda para os preparar. "
         "Planear um evento a partir do calendário leva-te diretamente aqui.",
         "The menu where you set events (races, goals) and get help preparing for them. "
         "Planning an event from the calendar takes you straight here."),
        ("app.event", "Evento", "Event",
         "Uma data importante (prova, teste, viagem) com um objetivo. O Treinador usa-a para "
         "organizar a carga das semanas anteriores.",
         "An important date (race, test, trip) with a goal. The Coach uses it to organise the "
         "load of the preceding weeks."),
        ("app.inventory", "Inventário", "Inventory",
         "O teu material: máquinas, pesos, bicicletas, sapatilhas, eletrónica. Os exercícios "
         "pedem material por tipo, e o treino surpresa só escolhe o que consegues fazer.",
         "Your equipment: machines, weights, bikes, shoes, electronics. Exercises ask for "
         "equipment by kind, and the surprise workout only picks what you can do."),
        ("app.surprise", "Treino surpresa", "Surprise workout",
         "Um treino de ginásio montado ao acaso com os exercícios que o teu material permite.",
         "A gym workout put together at random from the exercises your equipment allows."),
        ("app.device", "Dispositivo", "Device",
         "Um aparelho ligado à Perennia: rolo, banda cardíaca, medidor de potência, máquina de "
         "remo, passadeira. As ligações são Bluetooth (BLE) ou ANT+.",
         "A piece of equipment connected to Perennia: trainer, heart-rate strap, power meter, "
         "rowing machine, treadmill. Connections are Bluetooth (BLE) or ANT+."),
        ("app.backup", "Backup", "Backup",
         "Uma cópia dos teus dados em ficheiro, por componentes (perfil, sessões, saúde…). Serve "
         "para guardar, mudar de computador ou partilhar.",
         "A copy of your data in a file, by component (profile, sessions, health…). Use it to "
         "keep, move to another computer or share."),
        ("app.sync", "Sincronização", "Sync",
         "Trazer dados de fora para a Perennia: do GarminDB, do HRV4Training, do Strava ou de "
         "ficheiros. Cada fonte é independente e só acrescenta o que ainda não existe.",
         "Bringing outside data into Perennia: from GarminDB, HRV4Training, Strava or files. "
         "Each source is independent and only adds what does not exist yet."),
        ("app.source", "Fonte", "Source",
         "De onde veio um valor de saúde: escrito por ti, GarminDB, HRV4Training, ficheiro "
         "importado… Aparece em cada indicador e ajuda a saber em que dados confiar.",
         "Where a health value came from: typed by you, GarminDB, HRV4Training, imported file… "
         "It shows on each indicator and helps you know which data to trust."),
        ("app.glossary", "Glossário", "Glossary",
         "Este menu. Os termos de origem podem ser editados e repostos; podes acrescentar os "
         "teus, em qualquer separador.",
         "This menu. Built-in terms can be edited and restored; you can add your own, in any "
         "tab."),
        ("app.layout", "Disposição dos painéis", "Panel layout",
         "Em Definições escolhes que painéis (métricas, gráfico, zonas…) aparecem no ecrã de "
         "cada desporto e onde ficam.",
         "In Settings you choose which panels (metrics, chart, zones…) show on each sport's "
         "screen and where they go."),
        ("app.live_chart", "Gráfico ao vivo", "Live chart",
         "O gráfico que se desenha durante a sessão. Escolhes as métricas (potência, "
         "frequência cardíaca, ritmo/500 m…), só as do próprio desporto.",
         "The chart drawn during the session. You choose the metrics (power, heart rate, "
         "pace/500 m…), only the sport's own."),
        ("app.theme", "Tema", "Theme",
         "As cores e o tamanho da letra da aplicação. O tamanho de letra também se ajusta na "
         "configuração de cada sessão, com pré-visualização imediata.",
         "The application's colours and font size. The font size can also be adjusted in each "
         "session's setup, with an immediate preview."),
        ("app.erg", "Modo ERG", "ERG mode",
         "O rolo impõe a potência do bloco, seja qual for a cadência. Em modo não ERG és tu a "
         "decidir a potência e o rolo só dá resistência.",
         "The trainer imposes the block's power, whatever your cadence. In non-ERG mode you "
         "decide the power and the trainer only gives resistance."),
        ("app.sim", "Modo simulação", "Simulation mode",
         "O rolo muda a resistência com o declive da rota, como na estrada.",
         "The trainer changes resistance with the route's gradient, as on the road."),
    ),
    "files": (
        ("file.gpx", ".gpx", ".gpx",
         "Ficheiro de rota (GPS Exchange Format): uma lista de pontos com latitude, longitude e "
         "altitude. É o que se importa em Rotas.",
         "Route file (GPS Exchange Format): a list of points with latitude, longitude and "
         "altitude. It is what you import in Routes."),
        ("file.fit", ".fit", ".fit",
         "Ficheiro de atividade da Garmin (Flexible and Interoperable Data Transfer), binário "
         "e compacto: amostras, voltas e resumo. A Perennia lê e grava .fit.",
         "Garmin's activity file (Flexible and Interoperable Data Transfer), binary and "
         "compact: samples, laps and summary. Perennia reads and writes .fit."),
        ("file.tcx", ".tcx", ".tcx",
         "Formato XML de atividade da Garmin, mais antigo que o .fit, com pontos, voltas e "
         "frequência cardíaca.",
         "Garmin's older XML activity format, with points, laps and heart rate."),
        ("file.zwo", ".zwo", ".zwo",
         "Treino de ciclismo no formato do Zwift (XML), com blocos expressos em percentagem do "
         "FTP.",
         "Cycling workout in Zwift's format (XML), with blocks expressed as a percentage of "
         "FTP."),
        ("file.erg_mrc", ".erg / .mrc", ".erg / .mrc",
         "Treinos de texto simples do TrainerRoad e de outros programas: .erg em watts, .mrc em "
         "percentagem do FTP.",
         "Plain-text workouts from TrainerRoad and other programs: .erg in watts, .mrc in "
         "percentage of FTP."),
        ("file.csv", ".csv", ".csv",
         "Tabela de texto separada por vírgulas ou ponto e vírgula. Serve para importar saúde, "
         "treinos de ginásio ou planos, e os modelos (templates) são CSV.",
         "Table of text separated by commas or semicolons. It is used to import health, gym "
         "workouts or plans, and the templates are CSV."),
        ("file.template", "Modelo (template)", "Template",
         "Um ficheiro de exemplo, com as colunas certas, que preenches e importas. Cada "
         "importação tem o seu.",
         "An example file, with the right columns, that you fill in and import. Each import "
         "has its own."),
        ("file.db", "Base de dados", "Database",
         "Tudo o que a Perennia guarda está num único ficheiro SQLite local. Não há servidor: "
         "os teus dados ficam no teu computador.",
         "Everything Perennia stores is in a single local SQLite file. There is no server: "
         "your data stays on your computer."),
        ("file.sqlite", "SQLite", "SQLite",
         "O motor de base de dados em ficheiro usado pela Perennia (e pelo GarminDB).",
         "The file-based database engine used by Perennia (and by GarminDB)."),
        ("file.garmindb", "GarminDB", "GarminDB",
         "Programa que descarrega os dados da tua conta Garmin para bases de dados SQLite "
         "(garmin.db, garmin_monitoring.db, garmin_activities.db). A Perennia lê essas "
         "bases.",
         "A program that downloads your Garmin account data into SQLite databases (garmin.db, "
         "garmin_monitoring.db, garmin_activities.db). Perennia reads those databases."),
        ("file.json", ".json", ".json",
         "Texto estruturado. É o formato de alguns planos e dos metadados dos backups.",
         "Structured text. It is the format of some plans and of the backups' metadata."),
        ("file.zip", "Backup (.zip)", "Backup (.zip)",
         "O ficheiro de um backup: um zip com uma pasta por componente.",
         "A backup's file: a zip with one folder per component."),
    ),
    "training": (
        ("tr.ftp", "FTP", "FTP",
         "Functional Threshold Power: a potência (em watts) que aguentas cerca de uma hora. É a "
         "base das zonas e da carga no ciclismo.",
         "Functional Threshold Power: the power (in watts) you can hold for about an hour. It "
         "is the basis of zones and load in cycling."),
        ("tr.wkg", "W/kg", "W/kg",
         "Potência a dividir pelo peso. Compara ciclistas de pesos diferentes e pesa nas subidas.",
         "Power divided by weight. It compares riders of different weights and matters on "
         "climbs."),
        ("tr.np", "Potência normalizada (NP)", "Normalized Power (NP)",
         "Uma média da potência que dá mais peso aos esforços fortes, para refletir o custo "
         "fisiológico de uma sessão irregular.",
         "An average of power that gives more weight to hard efforts, to reflect the "
         "physiological cost of an uneven session."),
        ("tr.if", "Fator de intensidade (IF)", "Intensity Factor (IF)",
         "NP a dividir pelo FTP. 1,0 é um esforço ao limiar durante a sessão toda.",
         "NP divided by FTP. 1.0 is a threshold effort for the whole session."),
        ("tr.tss", "TSS", "TSS",
         "Training Stress Score: a carga de uma sessão, em pontos. 100 pontos é uma hora ao "
         "limiar.",
         "Training Stress Score: a session's load, in points. 100 points is one hour at "
         "threshold."),
        ("tr.ctl", "Forma / fitness (CTL)", "Fitness (CTL)",
         "Chronic Training Load: a carga média dos últimos 42 dias. Sobe devagar com o treino "
         "regular e mede a condição que construíste.",
         "Chronic Training Load: the average load of the last 42 days. It rises slowly with "
         "regular training and measures the fitness you have built."),
        ("tr.atl", "Fadiga (ATL)", "Fatigue (ATL)",
         "Acute Training Load: a carga média dos últimos 7 dias. Sobe depressa depois de "
         "semanas duras.",
         "Acute Training Load: the average load of the last 7 days. It rises fast after hard "
         "weeks."),
        ("tr.tsb", "Frescura (TSB)", "Form (TSB)",
         "Training Stress Balance: CTL menos ATL. Positivo é estares fresco; muito negativo é "
         "fadiga acumulada.",
         "Training Stress Balance: CTL minus ATL. Positive means you are fresh; very negative "
         "means accumulated fatigue."),
        ("tr.zones", "Zonas", "Zones",
         "Faixas de intensidade (de potência, frequência cardíaca ou ritmo) calculadas a partir "
         "do FTP, do limiar ou da frequência máxima. Z1 é leve, Z5 ou mais é máximo.",
         "Intensity bands (power, heart rate or pace) calculated from FTP, threshold or maximum "
         "heart rate. Z1 is easy, Z5 and up is maximal."),
        ("tr.rpe", "RPE", "RPE",
         "Rate of Perceived Exertion: quão duro foi, de 1 a 10, na tua perceção.",
         "Rate of Perceived Exertion: how hard it was, from 1 to 10, as you felt it."),
        ("tr.vo2", "VO2máx", "VO2max",
         "O máximo de oxigénio que consegues usar por minuto e por quilo. Indica a capacidade "
         "aeróbia.",
         "The maximum oxygen you can use per minute and per kilo. It indicates aerobic "
         "capacity."),
        ("tr.hrmax", "Frequência cardíaca máxima", "Maximum heart rate",
         "O valor mais alto que o teu coração atinge em esforço. Define as zonas por "
         "frequência cardíaca.",
         "The highest value your heart reaches in effort. It defines the heart-rate zones."),
        ("tr.lthr", "Limiar de lactato (LTHR)", "Lactate threshold (LTHR)",
         "A frequência cardíaca ao limiar: o ritmo que aguentas cerca de uma hora.",
         "The heart rate at threshold: the effort you can hold for about an hour."),
        ("tr.warmup", "Aquecimento", "Warm-up",
         "A parte inicial, leve, que prepara o corpo para o esforço.",
         "The easy initial part that prepares the body for the effort."),
        ("tr.cooldown", "Arrefecimento", "Cool-down",
         "A parte final, leve, para baixar a frequência cardíaca e recuperar.",
         "The easy final part to bring heart rate down and recover."),
        ("tr.interval", "Intervalo", "Interval",
         "Um esforço forte e curto, repetido, com recuperação entre repetições.",
         "A hard, short effort, repeated, with recovery between repetitions."),
        ("tr.recovery", "Recuperação", "Recovery",
         "Esforço muito leve entre intervalos, ou o descanso entre sessões.",
         "Very easy effort between intervals, or the rest between sessions."),
        ("tr.base", "Base", "Base",
         "Fase de treino com muito volume a intensidade baixa que constrói a capacidade "
         "aeróbia.",
         "A training phase with a lot of volume at low intensity that builds aerobic "
         "capacity."),
        ("tr.taper", "Afinação (taper)", "Taper",
         "Reduzir a carga nos dias antes de uma prova para chegar fresco.",
         "Reducing load in the days before a race to arrive fresh."),
        ("tr.overreach", "Sobrecarga", "Overreaching",
         "Carga acima do que consegues absorver. Com descanso é boa; sem ele leva ao "
         "sobretreino.",
         "Load above what you can absorb. With rest it is good; without it, it leads to "
         "overtraining."),
        ("tr.cadence", "Cadência", "Cadence",
         "Rotações dos pedais por minuto (rpm) no ciclismo, passos por minuto na corrida.",
         "Pedal revolutions per minute (rpm) in cycling, steps per minute in running."),
        ("tr.ramp", "Teste de rampa", "Ramp test",
         "Teste em que a potência sobe a cada minuto até não conseguires continuar; serve para "
         "estimar o FTP.",
         "A test where power rises every minute until you cannot continue; it is used to "
         "estimate FTP."),
        ("tr.cp", "Curva de potência", "Power curve",
         "A tua melhor potência média para cada duração (5 s, 1 min, 5 min, 20 min…).",
         "Your best average power for each duration (5 s, 1 min, 5 min, 20 min…)."),
    ),
    "gym": (
        ("gym.set", "Série", "Set",
         "Um grupo de repetições seguidas de um exercício, antes de descansar.",
         "A group of consecutive repetitions of an exercise, before resting."),
        ("gym.rep", "Repetição", "Repetition (rep)",
         "Uma execução completa do movimento.",
         "One complete execution of the movement."),
        ("gym.rest", "Descanso", "Rest",
         "O tempo entre séries ou exercícios. A Perennia conta-o e avisa quando acaba.",
         "The time between sets or exercises. Perennia counts it and warns you when it ends."),
        ("gym.rir", "RIR", "RIR",
         "Repetitions In Reserve: quantas repetições ainda terias capacidade de fazer. RIR 2 "
         "é parar com duas «no depósito».",
         "Repetitions In Reserve: how many more repetitions you could still do. RIR 2 means "
         "stopping with two 'in the tank'."),
        ("gym.1rm", "1RM", "1RM",
         "Uma repetição máxima: o peso mais alto que levantas uma só vez. Estima-se a partir de "
         "séries mais leves.",
         "One-repetition maximum: the heaviest weight you lift once. It is estimated from "
         "lighter sets."),
        ("gym.volume", "Volume", "Volume",
         "Séries × repetições × carga. É a medida do trabalho feito.",
         "Sets × reps × load. It is the measure of the work done."),
        ("gym.superset", "Superssérie", "Superset",
         "Dois exercícios feitos seguidos, sem descanso entre eles.",
         "Two exercises done back to back, without rest between them."),
        ("gym.circuit", "Circuito", "Circuit",
         "Vários exercícios em sequência, repetidos em voltas, com pouco descanso.",
         "Several exercises in sequence, repeated in rounds, with little rest."),
        ("gym.amrap", "AMRAP", "AMRAP",
         "As Many Rounds (or Reps) As Possible: o máximo de voltas ou repetições num tempo "
         "dado.",
         "As Many Rounds (or Reps) As Possible: the most rounds or reps in a given time."),
        ("gym.emom", "EMOM", "EMOM",
         "Every Minute On the Minute: uma tarefa por minuto, e o que sobra do minuto é "
         "descanso.",
         "Every Minute On the Minute: one task per minute, and what is left of the minute is "
         "rest."),
        ("gym.tempo", "Ritmo de execução (tempo)", "Tempo",
         "A velocidade de cada fase do movimento, por exemplo 3-1-1: três segundos a descer, "
         "um parado, um a subir.",
         "The speed of each phase of the movement, for example 3-1-1: three seconds down, one "
         "pause, one up."),
        ("gym.measure", "Medida (reps ou tempo)", "Measure (reps or time)",
         "Cada exercício conta-se em repetições ou em tempo (uma prancha, por exemplo). Só os "
         "blocos em tempo têm barra do bloco no ginásio.",
         "Each exercise is counted in repetitions or in time (a plank, for example). Only the "
         "blocks in time have a block bar in the gym."),
        ("gym.modality", "Modalidade", "Modality",
         "Um tipo de treino de ginásio (força, mobilidade, condicionamento…). Cada uma tem os "
         "seus exercícios e treinos.",
         "A type of gym training (strength, mobility, conditioning…). Each has its own "
         "exercises and workouts."),
        ("gym.discipline", "Disciplina", "Discipline",
         "Uma modalidade que crias tu, com o seu separador.",
         "A modality you create yourself, with its own tab."),
        ("gym.muscle_group", "Grupo muscular", "Muscle group",
         "Conjunto de músculos que trabalham juntos (peito, costas, pernas…). Cada exercício "
         "diz que grupos trabalha.",
         "A set of muscles that work together (chest, back, legs…). Each exercise says which "
         "groups it trains."),
        ("gym.compound", "Exercício composto", "Compound exercise",
         "Um movimento que usa várias articulações e grupos musculares (agachamento, "
         "levantamento de terra).",
         "A movement that uses several joints and muscle groups (squat, deadlift)."),
        ("gym.isolation", "Exercício de isolamento", "Isolation exercise",
         "Um movimento que trabalha sobretudo um músculo (rosca de bíceps).",
         "A movement that mainly works one muscle (biceps curl)."),
        ("gym.program", "Programa", "Program",
         "Um plano de várias semanas de ginásio, com os dias e exercícios de cada semana.",
         "A multi-week gym plan, with each week's days and exercises."),
        ("gym.deload", "Semana de descarga (deload)", "Deload week",
         "Uma semana com menos carga para recuperar antes de voltar a subir.",
         "A week with less load to recover before going up again."),
        ("gym.progression", "Progressão", "Progression",
         "Aumentar aos poucos o peso, as repetições ou as séries para continuares a evoluir.",
         "Gradually increasing weight, reps or sets to keep improving."),
    ),
    "sports": (
        ("sp.power", "Potência", "Power",
         "O trabalho por segundo, em watts (W). É a métrica mais fiel do esforço no ciclismo e "
         "no remo.",
         "Work per second, in watts (W). It is the most faithful measure of effort in cycling "
         "and rowing."),
        ("sp.hr", "Frequência cardíaca", "Heart rate",
         "Batimentos por minuto (bpm), vindos da banda ou do relógio.",
         "Beats per minute (bpm), from the strap or the watch."),
        ("sp.pace500", "Ritmo /500 m", "Pace /500 m",
         "No remo, o tempo que levarias a fazer 500 m ao ritmo atual (min:seg /500 m). Quanto "
         "menor, mais rápido.",
         "In rowing, the time it would take to cover 500 m at the current effort (min:sec "
         "/500 m). Lower is faster."),
        ("sp.avg_pace", "Ritmo médio", "Average pace",
         "O ritmo médio da sessão: tempo a dividir pela distância, em min/500 m no remo e min/km "
         "na corrida.",
         "The session's average pace: time divided by distance, in min/500 m in rowing and "
         "min/km in running."),
        ("sp.speed", "Velocidade", "Speed",
         "Distância por unidade de tempo (km/h, ou m/s no remo). Complementa o ritmo.",
         "Distance per unit of time (km/h, or m/s in rowing). It complements pace."),
        ("sp.strokes", "Remadas totais", "Total strokes",
         "O número de remadas desde o início da sessão.",
         "The number of strokes since the session started."),
        ("sp.spm", "Remadas por minuto (SPM)", "Strokes per minute (SPM)",
         "A frequência de remada. 18–24 é típico em resistência; mais alto em sprint.",
         "The stroke rate. 18–24 is typical for endurance; higher in a sprint."),
        ("sp.drag", "Fator de resistência (drag)", "Drag factor",
         "Mede a resistência da roda da máquina de remo, que depende do damper e da poeira. É o "
         "que torna comparáveis as máquinas.",
         "Measures the rowing machine flywheel's resistance, which depends on the damper and "
         "dust. It is what makes machines comparable."),
        ("sp.damper", "Damper", "Damper",
         "A alavanca da máquina de remo que regula a entrada de ar. Mais alto dá a sensação de "
         "um barco mais pesado.",
         "The lever on the rowing machine that sets the air intake. Higher feels like a "
         "heavier boat."),
        ("sp.split", "Split", "Split",
         "O ritmo médio de um troço (por exemplo, a cada 500 m), usado no remo.",
         "The average pace of a stretch (for example every 500 m), used in rowing."),
        ("sp.incline", "Inclinação", "Incline",
         "O declive da passadeira, em percentagem.",
         "The treadmill's gradient, in percent."),
        ("sp.pace_km", "Ritmo (min/km)", "Pace (min/km)",
         "O tempo para fazer um quilómetro. É a medida habitual na corrida.",
         "The time to cover a kilometre. It is the usual measure in running."),
        ("sp.gradient", "Declive", "Gradient",
         "A inclinação da estrada, em percentagem. A Perennia aplica-o ao rolo em modo "
         "simulação.",
         "The slope of the road, in percent. Perennia applies it to the trainer in simulation "
         "mode."),
        ("sp.vam", "VAM", "VAM",
         "Velocidade média de ascensão, em metros por hora. Mede o quão depressa subes.",
         "Average ascent speed, in metres per hour. It measures how fast you climb."),
        ("sp.lr_balance", "Equilíbrio esq/dir", "Left/right balance",
         "A repartição da potência entre a perna esquerda e a direita, quando o medidor a mede.",
         "The split of power between the left and right leg, when the meter measures it."),
    ),
    "health": (
        ("he.hrv", "HRV", "HRV",
         "Variabilidade da frequência cardíaca: a variação entre batimentos. Mais alta tende a "
         "indicar boa recuperação.",
         "Heart-rate variability: the variation between beats. Higher tends to indicate good "
         "recovery."),
        ("he.rmssd", "rMSSD", "rMSSD",
         "A medida de HRV mais usada em repouso; o HRV4Training devolve-a.",
         "The most-used HRV measure at rest; HRV4Training reports it."),
        ("he.rhr", "Frequência cardíaca de repouso", "Resting heart rate",
         "Os batimentos por minuto em repouso, de manhã. Subir vários dias seguidos pode "
         "indicar cansaço ou doença.",
         "Beats per minute at rest, in the morning. Rising for several days in a row may "
         "indicate tiredness or illness."),
        ("he.sleep", "Sono", "Sleep",
         "Duração e qualidade da noite: horas, fases (leve, profundo, REM) e interrupções.",
         "Duration and quality of the night: hours, stages (light, deep, REM) and awakenings."),
        ("he.stress", "Stress", "Stress",
         "Um índice que a Garmin estima a partir da HRV ao longo do dia.",
         "An index that Garmin estimates from HRV through the day."),
        ("he.bb", "Body Battery", "Body Battery",
         "A «energia» do dia segundo a Garmin, de 0 a 100: carrega a dormir, gasta-se com "
         "esforço e stress.",
         "The day's 'energy' according to Garmin, from 0 to 100: it charges with sleep and "
         "drains with effort and stress."),
        ("he.spo2", "SpO2", "SpO2",
         "Saturação de oxigénio no sangue, em percentagem.",
         "Blood oxygen saturation, in percent."),
        ("he.bp", "Pressão arterial", "Blood pressure",
         "Sistólica (máxima) e diastólica (mínima), em mmHg.",
         "Systolic (maximum) and diastolic (minimum), in mmHg."),
        ("he.bmi", "IMC", "BMI",
         "Índice de massa corporal: peso a dividir pela altura ao quadrado.",
         "Body mass index: weight divided by height squared."),
        ("he.indicator", "Indicador", "Indicator",
         "Um valor de saúde que acompanhas ao longo do tempo (peso, HRV, sono…). Cada um tem "
         "uma fonte.",
         "A health value you track over time (weight, HRV, sleep…). Each has a source."),
        ("he.diary", "Diário de saúde", "Health diary",
         "O registo dos valores e notas de cada dia. Só se escreve até ao dia de hoje.",
         "The record of each day's values and notes. You can only write up to today."),
        ("he.lab", "Análises clínicas", "Lab reports",
         "Os resultados de análises ao sangue e outras, com valores de referência e os "
         "comentários do médico.",
         "The results of blood and other tests, with reference values and the doctor's "
         "comments."),
        ("he.longevity", "Longevidade", "Longevity",
         "Um painel que junta indicadores de saúde e treino numa pontuação, com a fórmula que "
         "podes ajustar.",
         "A panel that gathers health and training indicators into a score, with a formula "
         "you can adjust."),
    ),
}
