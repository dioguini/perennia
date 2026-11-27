# A base de dados da Perennia

Gerado por `python tools/db_doc.py`. É uma base **SQLite** num só ficheiro: `data/perennia.db` (ver RUN.md, «A base de dados»). Ao lado ficam `perennia.db-wal` e `perennia.db-shm` (o modo WAL): para copiar a base, fecha a Perennia antes.

88 tabelas descritas.

## `athlete`

O atleta: nome, ano de nascimento, peso, FTP, FC máxima, LTHR, bicicleta (peso, CdA, Crr).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `name` | TEXT | nome |
| `birth_year` | INTEGER |  |
| `weight_kg` | REAL | quilogramas |
| `ftp_w` | INTEGER | watts |
| `max_hr` | INTEGER | frequência cardíaca |
| `lthr` | INTEGER | frequência cardíaca |
| `bike_weight_kg` | REAL | quilogramas |
| `cda` | REAL |  |
| `crr` | REAL |  |

## `block_events`

Alterações feitas aos blocos durante uma sessão (+/−).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `sport` | TEXT | desporto |
| `session_id` | TEXT | → a sessão |
| `step_idx` | INTEGER | posição (0, 1, 2…) |
| `kind` | TEXT | tipo |
| `field` | TEXT |  |
| `original` | REAL |  |
| `value` | REAL |  |
| `planned` | REAL |  |
| `done` | REAL |  |
| `unit` | TEXT |  |
| `changes` | INTEGER |  |
| `t_s` | REAL | segundos |
| `updated_at` | TEXT | última alteração |

## `bp_readings`

Medições da pressão arterial.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `day` | TEXT | dia (AAAA-MM-DD) |
| `period` | TEXT |  |
| `at` | TEXT |  |
| `sys` | REAL |  |
| `dia` | REAL |  |
| `pulse` | REAL |  |
| `notes` | TEXT | notas |
| `source` | TEXT |  |
| `created_at` | TEXT | quando foi criado |

## `challenge_attempts`

As tentativas de cada desafio.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `challenge_id` | INTEGER |  |
| `started_at` | TEXT | data e hora (ISO) |
| `completed_at` | TEXT | data e hora (ISO) |
| `progress` | REAL |  |
| `elapsed_s` | REAL | segundos |
| `completing_ride_id` | TEXT |  |

## `challenges`

Os desafios (metas com prazo).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `name` | TEXT | nome |
| `metric` | TEXT |  |
| `target` | REAL |  |
| `is_default` | INTEGER |  |
| `display_unit` | TEXT |  |
| `created_at` | TEXT | quando foi criado |
| `sport` | TEXT | desporto |
| `deadline` | TEXT |  |

## `chase_efforts`

Ciclismo: o jogo da perseguição (quanto aguentaste).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `ride_id` | TEXT | → rides.id |
| `route_id` | TEXT | → routes.id |
| `level` | TEXT |  |
| `survived_s` | REAL | segundos |
| `distance_m` | REAL | metros |
| `avg_power_w` | REAL | watts |
| `final_chaser_w` | INTEGER | watts |
| `caught` | INTEGER |  |
| `clean` | INTEGER |  |
| `created_at` | TEXT | quando foi criado |

## `climb_efforts`

Ciclismo: os esforços em cada subida de uma rota.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `climb_id` | INTEGER |  |
| `ride_id` | TEXT | → rides.id |
| `start_t_s` | INTEGER | segundos |
| `end_t_s` | INTEGER | segundos |
| `elapsed_s` | INTEGER | segundos |
| `avg_power_w` | REAL | watts |
| `avg_hr` | REAL | frequência cardíaca |
| `avg_cadence` | REAL |  |
| `vam_mh` | REAL |  |
| `avg_balance_left` | REAL |  |

## `climbs`

As subidas detetadas em cada rota.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `route_id` | TEXT | → routes.id |
| `seq` | INTEGER |  |
| `name` | TEXT | nome |
| `start_m` | REAL | metros |
| `end_m` | REAL | metros |
| `length_m` | REAL | metros |
| `gain_m` | REAL | metros |
| `avg_grade_pct` | REAL | percentagem |
| `max_grade_pct` | REAL | percentagem |
| `category` | TEXT |  |
| `score` | REAL |  |

## `coach_events`

O Treinador: eventos (provas) e as respostas que deste.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `kind` | TEXT | tipo |
| `name` | TEXT | nome |
| `day` | TEXT | dia (AAAA-MM-DD) |
| `sport` | TEXT | desporto |
| `priority` | TEXT |  |
| `answers` | TEXT |  |
| `plan_ids` | TEXT |  |
| `created_at` | TEXT | quando foi criado |
| `updated_at` | TEXT | última alteração |

## `conditioning_parts`

As partes de uma sessão de Conditioning (blocos mistos).

| coluna | tipo | o que é |
|---|---|---|
| `session_id` | TEXT | → a sessão |
| `sport` | TEXT | desporto |
| `seq` | INTEGER |  |
| `blocks` | INTEGER |  |
| `laps` | INTEGER |  |
| `timer_s` | REAL | segundos |
| `span_s` | REAL | segundos |
| `start_t_s` | REAL | segundos |
| `distance_km` | REAL |  |
| `avg_hr` | REAL | frequência cardíaca |
| `max_hr` | INTEGER | frequência cardíaca |
| `sets` | INTEGER |  |
| `reps` | INTEGER |  |
| `load` | REAL | carga (escala TSS) |
| `fit_path` | TEXT |  |

## `daily_values`

O diário de saúde: o valor de cada métrica em cada dia (e a fonte).

| coluna | tipo | o que é |
|---|---|---|
| `day` | TEXT | AAAA-MM-DD |
| `metric_id` | INTEGER | → metric_defs.id |
| `num` | REAL | o valor (número ou texto) |
| `txt` | TEXT | o valor (número ou texto) |
| `notes` | TEXT | notas |
| `source` | TEXT | de onde veio |
| `updated_at` | TEXT | última alteração |

## `day_notes`

A nota de cada dia.

| coluna | tipo | o que é |
|---|---|---|
| `day` | TEXT | dia (AAAA-MM-DD) |
| `text` | TEXT |  |

## `devices`

Os aparelhos conhecidos (Bluetooth/ANT+): nome, perfis, prioridade, ligação automática.

| coluna | tipo | o que é |
|---|---|---|
| `id` | TEXT | chave |
| `transport` | TEXT | desporto |
| `name` | TEXT | nome |
| `profiles` | TEXT |  |
| `capabilities` | INTEGER |  |
| `priority_json` | TEXT | JSON |
| `auto_connect` | INTEGER |  |
| `last_seen_at` | TEXT | data e hora (ISO) |
| `role` | TEXT |  |

## `endurance_laps`

Corrida/natação: as voltas (e piscinas).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `session_id` | TEXT | → a sessão |
| `lap_no` | INTEGER |  |
| `trigger` | TEXT |  |
| `start_t` | REAL |  |
| `end_t` | REAL |  |
| `distance_m` | REAL | metros |
| `avg_hr` | REAL | frequência cardíaca |
| `max_hr` | INTEGER | frequência cardíaca |
| `lengths` | INTEGER |  |

## `endurance_samples`

Corrida/natação: uma amostra por segundo (velocidade, distância, FC, inclinação).

| coluna | tipo | o que é |
|---|---|---|
| `session_id` | TEXT | → a sessão |
| `t_s` | INTEGER | segundos |
| `dist_m` | REAL | metros |
| `speed_mps` | REAL | metros por segundo |
| `hr_bpm` | INTEGER | batimentos por minuto |
| `incline_pct` | REAL | percentagem |

## `endurance_sessions`

Sessões de corrida e natação: tempos, distância, ritmo, FC, carga (rTSS/sTSS) e de onde veio.

| coluna | tipo | o que é |
|---|---|---|
| `id` | TEXT | chave |
| `sport` | TEXT | desporto |
| `name` | TEXT | nome |
| `status` | TEXT | estado (recording, completed, aborted… ou active/deleted) |
| `workout_id` | TEXT | → o treino |
| `started_at` | TEXT | data e hora (ISO) |
| `ended_at` | TEXT | data e hora (ISO) |
| `elapsed_s` | INTEGER | segundos |
| `moving_s` | INTEGER | segundos |
| `paused_s` | INTEGER | segundos |
| `distance_m` | REAL | metros |
| `avg_pace_s` | REAL | segundos |
| `avg_hr` | REAL | frequência cardíaca |
| `max_hr` | INTEGER | frequência cardíaca |
| `load` | REAL | carga (escala TSS) |
| `load_source` | TEXT |  |
| `hr_zone_s` | TEXT | segundos |
| `lengths` | INTEGER |  |
| `pool_m` | REAL | metros |
| `fit_path` | TEXT |  |
| `route_id` | TEXT | → routes.id |

## `endurance_steps`

Os blocos de cada treino de corrida/natação.

| coluna | tipo | o que é |
|---|---|---|
| `workout_id` | TEXT | → o treino |
| `idx` | INTEGER | posição (0, 1, 2…) |
| `kind` | TEXT | tipo |
| `dur_type` | TEXT |  |
| `dur_value` | REAL |  |
| `lo` | REAL |  |
| `hi` | REAL |  |
| `cue` | TEXT |  |

## `endurance_workouts`

Treinos de corrida e natação.

| coluna | tipo | o que é |
|---|---|---|
| `id` | TEXT | chave |
| `sport` | TEXT | desporto |
| `name` | TEXT | nome |
| `description` | TEXT |  |
| `mode` | TEXT |  |
| `builtin` | INTEGER | 1 = vem com a Perennia |
| `created_at` | TEXT | quando foi criado |
| `sort` | INTEGER | ordem |
| `status` | TEXT | estado (recording, completed, aborted… ou active/deleted) |

## `equipment_items`

O teu inventário (equipamento, quantidades, compra).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `name` | TEXT | nome |
| `kind` | TEXT | tipo |
| `qty` | INTEGER |  |
| `weight_kg` | REAL | quilogramas |
| `notes` | TEXT | notas |
| `created_at` | TEXT | quando foi criado |
| `purchase_date` | TEXT |  |
| `purchase_price` | REAL |  |

## `exercise_complex_parts`

As partes de um exercício complexo.

| coluna | tipo | o que é |
|---|---|---|
| `complex_id` | INTEGER |  |
| `idx` | INTEGER | posição (0, 1, 2…) |
| `exercise_id` | INTEGER | → exercises.id |
| `reps` | INTEGER |  |

## `exercise_equipment`

O equipamento de cada exercício.

| coluna | tipo | o que é |
|---|---|---|
| `exercise_id` | INTEGER | → exercises.id |
| `kind` | TEXT | tipo |

## `exercise_modalities`

As modalidades de cada exercício (força, mobilidade, HIIT…).

| coluna | tipo | o que é |
|---|---|---|
| `exercise_id` | INTEGER | → exercises.id |
| `modality` | TEXT |  |

## `exercises`

O catálogo de exercícios (categoria, medida, peso do corpo, subgrupo muscular).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `name` | TEXT | nome |
| `category` | TEXT |  |
| `fit_category` | INTEGER |  |
| `bodyweight` | REAL |  |
| `measure` | TEXT |  |
| `custom` | INTEGER | 1 = criado por ti |
| `created_at` | TEXT | quando foi criado |
| `subgroup_id` | INTEGER |  |
| `description` | TEXT |  |
| `notes` | TEXT | notas |
| `archived` | INTEGER |  |
| `complex` | INTEGER |  |

## `fitness_tests`

Os testes de condição física (incluindo os de longevidade).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `sport` | TEXT | desporto |
| `name` | TEXT | nome |
| `unit` | TEXT |  |
| `better` | TEXT |  |
| `duration_s` | INTEGER | segundos |
| `protocol` | TEXT |  |
| `instructions` | TEXT |  |
| `custom` | INTEGER | 1 = criado por ti |
| `active` | INTEGER |  |
| `sort` | INTEGER | ordem |

## `ftp_tests`

Testes de FTP feitos e o FTP que deram.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `ride_id` | TEXT | → rides.id |
| `protocol` | TEXT |  |
| `tested_at` | TEXT | data e hora (ISO) |
| `raw_value_w` | REAL | watts |
| `ftp_w` | INTEGER | watts |
| `accepted` | INTEGER |  |

## `game_results`

Resultados dos jogos (desafios dentro das sessões).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `ride_id` | TEXT | → rides.id |
| `game` | TEXT |  |
| `score` | REAL |  |
| `rank` | INTEGER |  |
| `total` | INTEGER |  |
| `won` | INTEGER |  |
| `seconds` | INTEGER |  |
| `details` | TEXT |  |
| `created_at` | TEXT | quando foi criado |

## `glossary`

O glossário geral.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `builtin_key` | TEXT |  |
| `tab` | TEXT |  |
| `term` | TEXT |  |
| `definition` | TEXT |  |
| `deleted` | INTEGER |  |
| `updated_at` | TEXT | última alteração |

## `gym_disciplines`

Disciplinas do ginásio.

| coluna | tipo | o que é |
|---|---|---|
| `key` | TEXT |  |
| `name_pt` | TEXT |  |
| `name_en` | TEXT |  |
| `icon` | TEXT |  |
| `description` | TEXT |  |
| `sort` | INTEGER | ordem |

## `health_tab_notes`

As notas dos separadores da Saúde.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `tab_key` | TEXT |  |
| `day` | TEXT | dia (AAAA-MM-DD) |
| `title` | TEXT |  |
| `text` | TEXT |  |
| `updated_at` | TEXT | última alteração |

## `health_tabs`

Os separadores personalizados da Saúde.

| coluna | tipo | o que é |
|---|---|---|
| `key` | TEXT |  |
| `name` | TEXT | nome |
| `sort` | INTEGER | ordem |
| `created_at` | TEXT | quando foi criado |

## `lab_glossary`

O glossário das análises (o que é, sobe/desce, bom/mau).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `builtin_key` | TEXT |  |
| `category` | TEXT |  |
| `name` | TEXT | nome |
| `aliases` | TEXT |  |
| `summary` | TEXT |  |
| `what` | TEXT |  |
| `up` | TEXT |  |
| `down` | TEXT |  |
| `good` | TEXT |  |
| `bad` | TEXT |  |
| `act` | TEXT |  |
| `deleted` | INTEGER |  |
| `updated_at` | TEXT | última alteração |

## `lab_parameters`

O catálogo dos parâmetros das análises.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `name` | TEXT | nome |
| `short_name` | TEXT | nome |
| `unit` | TEXT |  |
| `area` | TEXT |  |
| `panel` | TEXT |  |
| `subpanel` | TEXT |  |
| `reference_text` | TEXT |  |
| `ref_low` | REAL |  |
| `ref_high` | REAL |  |
| `ideal_low` | REAL |  |
| `ideal_high` | REAL |  |
| `ref_source` | TEXT |  |
| `ref_manual` | INTEGER |  |
| `ext_id` | INTEGER |  |
| `sort` | INTEGER | ordem |

## `lab_reports`

Análises clínicas: cada colheita.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `done_on` | TEXT | data (AAAA-MM-DD) |
| `lab` | TEXT |  |
| `notes` | TEXT | notas |
| `doctor_feedback` | TEXT |  |
| `created_at` | TEXT | quando foi criado |
| `kind` | TEXT | tipo |

## `lab_results`

Análises clínicas: cada resultado (valor, referências).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `report_id` | INTEGER |  |
| `marker` | TEXT |  |
| `value` | REAL |  |
| `value_text` | TEXT |  |
| `unit` | TEXT |  |
| `ref_low` | REAL |  |
| `ref_high` | REAL |  |
| `comment` | TEXT |  |
| `sort` | INTEGER | ordem |
| `parameter_id` | INTEGER |  |
| `area` | TEXT |  |
| `panel` | TEXT |  |
| `subpanel` | TEXT |  |
| `value_pct` | REAL | percentagem |
| `qualifier` | TEXT |  |
| `doctor_comment` | TEXT |  |

## `lap_plans`

Planos de voltas guardados.

| coluna | tipo | o que é |
|---|---|---|
| `id` | TEXT | chave |
| `name` | TEXT | nome |
| `mode` | TEXT |  |
| `items` | TEXT |  |
| `hidden` | INTEGER | 1 = escondido |
| `created_at` | TEXT | quando foi criado |

## `laps`

Ciclismo: as voltas de cada sessão (manuais, por bloco ou automáticas).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `ride_id` | TEXT | → rides.id |
| `lap_no` | INTEGER |  |
| `trigger` | TEXT |  |
| `start_t_s` | INTEGER | segundos |
| `end_t_s` | INTEGER | segundos |
| `start_dist_m` | REAL | metros |
| `end_dist_m` | REAL | metros |
| `avg_power_w` | REAL | watts |
| `np_w` | REAL | watts |
| `max_power_w` | INTEGER | watts |
| `avg_hr` | REAL | frequência cardíaca |
| `max_hr` | INTEGER | frequência cardíaca |
| `avg_cadence` | REAL |  |
| `avg_speed_mps` | REAL | metros por segundo |
| `ascent_m` | REAL | metros |
| `avg_balance_left` | REAL |  |
| `avg_te_left` | REAL |  |
| `avg_te_right` | REAL |  |
| `avg_ps_left` | REAL |  |
| `avg_ps_right` | REAL |  |
| `avg_ps_combined` | REAL |  |

## `metric_defs`

As métricas do diário de saúde (nome, tipo, unidade, grupo, ativa).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `key` | TEXT |  |
| `name` | TEXT | nome |
| `kind` | TEXT | tipo |
| `unit` | TEXT |  |
| `grp` | TEXT |  |
| `choices` | TEXT |  |
| `active` | INTEGER |  |
| `sort` | INTEGER | ordem |
| `custom` | INTEGER | 1 = criado por ti |
| `source` | TEXT |  |
| `parent_key` | TEXT |  |
| `parent_value` | TEXT |  |
| `discontinued_on` | TEXT | data (AAAA-MM-DD) |

## `muscle_groups`

Grupos musculares.

| coluna | tipo | o que é |
|---|---|---|
| `key` | TEXT |  |
| `name_pt` | TEXT |  |
| `name_en` | TEXT |  |
| `sort` | INTEGER | ordem |

## `muscle_subgroups`

Subgrupos musculares.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `group_key` | TEXT |  |
| `name_pt` | TEXT |  |
| `name_en` | TEXT |  |
| `sort` | INTEGER | ordem |

## `perennia_segments`

Segmentos definidos por ti numa rota (km de início e fim).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `route_id` | TEXT | → routes.id |
| `name` | TEXT | nome |
| `start_m` | REAL | metros |
| `end_m` | REAL | metros |
| `created_at` | TEXT | quando foi criado |

## `program_days`

Os dias de cada plano em curso.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `run_id` | INTEGER |  |
| `idx` | INTEGER | posição (0, 1, 2…) |
| `week` | INTEGER |  |
| `day` | TEXT | dia (AAAA-MM-DD) |
| `session_key` | TEXT |  |
| `title` | TEXT |  |
| `workout_id` | TEXT | → o treino |
| `plan_id` | TEXT |  |

## `program_runs`

Planos de treino em curso.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `program_key` | TEXT |  |
| `name` | TEXT | nome |
| `start_day` | TEXT | dia (AAAA-MM-DD) |
| `weekdays` | TEXT |  |
| `loads` | TEXT |  |
| `status` | TEXT | estado (recording, completed, aborted… ou active/deleted) |
| `data` | TEXT |  |
| `created_at` | TEXT | quando foi criado |
| `ended_at` | TEXT | data e hora (ISO) |

## `programs`

Planos de treino (modelos) do ginásio.

| coluna | tipo | o que é |
|---|---|---|
| `key` | TEXT |  |
| `name` | TEXT | nome |
| `data` | TEXT |  |
| `created_at` | TEXT | quando foi criado |

## `ride_comparisons`

Ciclismo: comparação com o «fantasma» (outra sessão na mesma rota).

| coluna | tipo | o que é |
|---|---|---|
| `ride_id` | TEXT | → rides.id |
| `ghost_ride_id` | TEXT |  |
| `final_delta_s` | REAL | segundos |

## `ride_peaks`

Ciclismo: os picos de cada sessão (melhor potência/FC/cadência em cada duração).

| coluna | tipo | o que é |
|---|---|---|
| `ride_id` | TEXT | → rides.id |
| `metric` | TEXT |  |
| `duration_s` | INTEGER | segundos |
| `value` | REAL |  |
| `version` | INTEGER |  |

## `ride_power_curve`

Ciclismo: a curva de potência de cada sessão.

| coluna | tipo | o que é |
|---|---|---|
| `ride_id` | TEXT | → rides.id |
| `duration_s` | INTEGER | segundos |
| `max_avg_w` | REAL | watts |

## `ride_samples`

Ciclismo: uma amostra por segundo (potência, cadência, FC, velocidade, distância, equilíbrio).

| coluna | tipo | o que é |
|---|---|---|
| `ride_id` | TEXT | → rides.id |
| `t_s` | INTEGER | segundos |
| `dist_m` | REAL | metros |
| `speed_mps` | REAL | metros por segundo |
| `power_w` | INTEGER | watts |
| `cadence_rpm` | INTEGER | rotações por minuto |
| `hr_bpm` | INTEGER | batimentos por minuto |
| `balance_left` | REAL |  |
| `torque_nm` | REAL |  |
| `grade_pct` | REAL | percentagem |
| `ele_m` | REAL | metros |
| `target_power_w` | INTEGER | watts |
| `resistance_sent` | REAL |  |
| `lap_no` | INTEGER |  |
| `te_left` | REAL |  |
| `te_right` | REAL |  |
| `ps_left` | REAL |  |
| `ps_right` | REAL |  |
| `ps_combined` | REAL |  |

## `rides`

Sessões de ciclismo: início/fim, tempos, distância, potência média/NP/TSS/IF, FC, estado, ficheiro .fit.

| coluna | tipo | o que é |
|---|---|---|
| `id` | TEXT | chave |
| `route_id` | TEXT | → routes.id |
| `workout_id` | TEXT | → o treino |
| `kind` | TEXT | tipo |
| `mode` | TEXT |  |
| `erg_enabled` | INTEGER |  |
| `status` | TEXT | estado (recording, completed, aborted… ou active/deleted) |
| `started_at` | TEXT | data e hora (ISO) |
| `ended_at` | TEXT | data e hora (ISO) |
| `elapsed_s` | INTEGER | segundos |
| `moving_s` | INTEGER | segundos |
| `distance_m` | REAL | metros |
| `ascent_m` | REAL | metros |
| `completed_route` | INTEGER |  |
| `route_loops` | INTEGER |  |
| `best_loop_s` | INTEGER | segundos |
| `paused_s` | INTEGER | segundos |
| `avg_power_w` | REAL | watts |
| `max_power_w` | INTEGER | watts |
| `np_w` | REAL | watts |
| `intensity_factor` | REAL |  |
| `tss` | REAL | Training Stress Score |
| `work_kj` | REAL |  |
| `avg_hr` | REAL | frequência cardíaca |
| `max_hr` | INTEGER | frequência cardíaca |
| `avg_cadence` | REAL |  |
| `avg_speed_mps` | REAL | metros por segundo |
| `avg_balance_left` | REAL |  |
| `ftp_at_ride_w` | INTEGER | watts |
| `weight_at_ride_kg` | REAL | quilogramas |
| `trainer_difficulty` | REAL |  |
| `extra_resistance_pct` | REAL | percentagem |
| `render_preset` | TEXT |  |
| `fit_path` | TEXT |  |
| `notes` | TEXT | notas |
| `avg_te_left` | REAL |  |
| `avg_te_right` | REAL |  |
| `avg_ps_left` | REAL |  |
| `avg_ps_right` | REAL |  |
| `avg_ps_combined` | REAL |  |
| `name` | TEXT | nome |

## `route_bakes`

Cache 3D das rotas (estado da preparação gráfica).

| coluna | tipo | o que é |
|---|---|---|
| `route_id` | TEXT | → routes.id |
| `preset` | TEXT |  |
| `status` | TEXT | estado (recording, completed, aborted… ou active/deleted) |
| `baker_ver` | INTEGER |  |
| `cache_path` | TEXT |  |
| `baked_at` | TEXT | data e hora (ISO) |

## `route_efforts`

Esforços completos numa rota (tempo, potência, FC).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `route_id` | TEXT | → routes.id |
| `ride_id` | TEXT | → rides.id |
| `elapsed_s` | INTEGER | segundos |
| `avg_power_w` | REAL | watts |
| `avg_hr` | REAL | frequência cardíaca |
| `avg_cadence` | REAL |  |
| `np_w` | REAL | watts |

## `route_points`

Os pontos de cada rota (reamostrados): posição, elevação, inclinação, rumo.

| coluna | tipo | o que é |
|---|---|---|
| `route_id` | TEXT | → routes.id |
| `idx` | INTEGER | posição (0, 1, 2…) |
| `dist_m` | REAL | metros |
| `lat` | REAL |  |
| `lon` | REAL |  |
| `x_m` | REAL | metros |
| `y_m` | REAL | metros |
| `ele_m` | REAL | metros |
| `grade_pct` | REAL | percentagem |
| `heading_deg` | REAL | graus |

## `routes`

Rotas importadas (.gpx): distância, subida, inclinações, elevação.

| coluna | tipo | o que é |
|---|---|---|
| `id` | TEXT | chave |
| `name` | TEXT | nome |
| `source_filename` | TEXT | nome |
| `distance_m` | REAL | metros |
| `ascent_m` | REAL | metros |
| `descent_m` | REAL | metros |
| `max_grade_pct` | REAL | percentagem |
| `min_ele_m` | REAL | metros |
| `max_ele_m` | REAL | metros |
| `bbox_json` | TEXT | JSON |
| `origin_lat` | REAL |  |
| `origin_lon` | REAL |  |
| `point_count` | INTEGER |  |
| `imported_at` | TEXT | data e hora (ISO) |
| `times_ridden` | INTEGER |  |
| `favorite` | INTEGER |  |

## `row_laps`

Remo: as voltas de cada sessão.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `session_id` | TEXT | → a sessão |
| `lap_no` | INTEGER |  |
| `trigger` | TEXT |  |
| `start_t` | REAL |  |
| `end_t` | REAL |  |
| `distance_m` | REAL | metros |
| `strokes` | INTEGER |  |
| `avg_pace_s` | REAL | segundos |
| `avg_power_w` | REAL | watts |
| `avg_spm` | REAL |  |
| `avg_hr` | REAL | frequência cardíaca |
| `max_hr` | INTEGER | frequência cardíaca |
| `step_idx` | INTEGER | posição (0, 1, 2…) |

## `row_samples`

Remo: uma amostra por segundo.

| coluna | tipo | o que é |
|---|---|---|
| `session_id` | TEXT | → a sessão |
| `t_s` | INTEGER | segundos |
| `dist_m` | REAL | metros |
| `pace_s` | REAL | segundos |
| `power_w` | INTEGER | watts |
| `spm` | REAL |  |
| `hr_bpm` | INTEGER | batimentos por minuto |
| `resistance` | INTEGER |  |
| `strokes` | INTEGER |  |

## `row_sessions`

Sessões de remo: tempos, distância, voltas de pá, potência, ritmo, carga (TSS), FC.

| coluna | tipo | o que é |
|---|---|---|
| `id` | TEXT | chave |
| `kind` | TEXT | tipo |
| `name` | TEXT | nome |
| `status` | TEXT | estado (recording, completed, aborted… ou active/deleted) |
| `workout_id` | TEXT | → o treino |
| `protocol` | TEXT |  |
| `game` | TEXT |  |
| `started_at` | TEXT | data e hora (ISO) |
| `ended_at` | TEXT | data e hora (ISO) |
| `elapsed_s` | INTEGER | segundos |
| `moving_s` | INTEGER | segundos |
| `paused_s` | INTEGER | segundos |
| `distance_m` | REAL | metros |
| `strokes` | INTEGER |  |
| `avg_spm` | REAL |  |
| `avg_pace_s` | REAL | segundos |
| `best_pace_s` | REAL | segundos |
| `avg_power_w` | REAL | watts |
| `max_power_w` | INTEGER | watts |
| `np_w` | REAL | watts |
| `kcal` | REAL |  |
| `avg_hr` | REAL | frequência cardíaca |
| `max_hr` | INTEGER | frequência cardíaca |
| `load` | REAL | carga (escala TSS) |
| `load_source` | TEXT |  |
| `hr_zone_s` | TEXT | segundos |
| `ftp_w` | INTEGER | watts |
| `fit_path` | TEXT |  |
| `result` | REAL |  |
| `device` | TEXT |  |

## `row_workout_steps`

Os blocos de cada treino de remo.

| coluna | tipo | o que é |
|---|---|---|
| `workout_id` | TEXT | → o treino |
| `idx` | INTEGER | posição (0, 1, 2…) |
| `kind` | TEXT | tipo |
| `dur_type` | TEXT |  |
| `dur_value` | REAL |  |
| `target` | TEXT |  |
| `lo` | REAL |  |
| `hi` | REAL |  |
| `resistance` | INTEGER |  |
| `cue` | TEXT |  |

## `row_workouts`

Treinos de remo.

| coluna | tipo | o que é |
|---|---|---|
| `id` | TEXT | chave |
| `name` | TEXT | nome |
| `description` | TEXT |  |
| `builtin` | INTEGER | 1 = vem com a Perennia |
| `created_at` | TEXT | quando foi criado |
| `sort` | INTEGER | ordem |
| `status` | TEXT | estado (recording, completed, aborted… ou active/deleted) |

## `schema_version`

A versão do esquema (migrações aplicadas).

| coluna | tipo | o que é |
|---|---|---|
| `version` | INTEGER |  |
| `applied_at` | TEXT | data e hora (ISO) |

## `segment_efforts`

Os teus tempos nos segmentos (Perennia e Strava), por sessão.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `source` | TEXT |  |
| `segment_id` | INTEGER |  |
| `session_kind` | TEXT | tipo |
| `session_id` | TEXT | → a sessão |
| `sport` | TEXT | desporto |
| `elapsed_s` | INTEGER | segundos |
| `created_at` | TEXT | quando foi criado |

## `session_checkpoints`

O estado de uma sessão a decorrer (para a retomar se a app fechar).

| coluna | tipo | o que é |
|---|---|---|
| `session_id` | TEXT | → a sessão |
| `sport` | TEXT | desporto |
| `saved_at` | TEXT | data e hora (ISO) |
| `config` | TEXT |  |
| `state` | TEXT |  |

## `session_feedback`

O feedback de cada sessão (RPE, dores, sensação, comentário) e a análise automática (veredito e secções). kind: ride|row|endurance|strength|imported.

| coluna | tipo | o que é |
|---|---|---|
| `kind` | TEXT | a sessão (ride, row, endurance, strength ou imported) |
| `session_id` | TEXT | a sessão (ride, row, endurance, strength ou imported) |
| `sport` | TEXT | desporto |
| `workout_id` | TEXT | → o treino |
| `day` | TEXT | dia (AAAA-MM-DD) |
| `rpe` | INTEGER | o teu feedback (vazio = só análise automática) |
| `pain` | INTEGER | o teu feedback (vazio = só análise automática) |
| `feel` | INTEGER | o teu feedback (vazio = só análise automática) |
| `goal_met` | TEXT | o teu feedback (vazio = só análise automática) |
| `comment` | TEXT | o teu feedback (vazio = só análise automática) |
| `useful` | TEXT | o veredito da análise |
| `verdict` | TEXT | o veredito da análise |
| `analysis` | TEXT | a análise completa (JSON: secções, execução, objetivo) |
| `created_at` | TEXT | quando foi criado |
| `updated_at` | TEXT | última alteração |

## `session_tags`

As etiquetas de cada sessão (tipo de treino, Indoor…, livres).

| coluna | tipo | o que é |
|---|---|---|
| `sport` | TEXT | desporto |
| `session_id` | TEXT | → a sessão |
| `tag` | TEXT |  |
| `kind` | TEXT | tipo |

## `session_workouts`

A cópia do treino guardada com cada sessão (como foi feito).

| coluna | tipo | o que é |
|---|---|---|
| `kind` | TEXT | tipo |
| `session_id` | TEXT | → a sessão |
| `sport` | TEXT | desporto |
| `workout_id` | TEXT | → o treino |
| `copy_id` | TEXT |  |
| `origin` | TEXT |  |
| `source` | TEXT |  |
| `name` | TEXT | nome |
| `created_at` | TEXT | quando foi criado |

## `settings`

Todas as opções e definições (chave → valor em JSON): Definições, Avançado, ligações, estado.

| coluna | tipo | o que é |
|---|---|---|
| `key` | TEXT | nome da opção |
| `value` | TEXT | valor em JSON |

## `strava_efforts`

Os teus tempos nos segmentos do Strava durante as sessões da Perennia.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `ride_id` | TEXT | → rides.id |
| `segment_id` | INTEGER |  |
| `elapsed_s` | INTEGER | segundos |
| `created_at` | TEXT | quando foi criado |

## `strava_library`

A biblioteca de segmentos importados do Strava (ficam neste computador).

| coluna | tipo | o que é |
|---|---|---|
| `segment_id` | INTEGER |  |
| `name` | TEXT | nome |
| `activity_type` | TEXT |  |
| `distance_m` | REAL | metros |
| `avg_grade` | REAL |  |
| `max_grade` | REAL |  |
| `elev_gain_m` | REAL | metros |
| `climb_cat` | INTEGER |  |
| `start_lat` | REAL |  |
| `start_lon` | REAL |  |
| `end_lat` | REAL |  |
| `end_lon` | REAL |  |
| `polyline` | TEXT |  |
| `city` | TEXT |  |
| `country` | TEXT |  |
| `private` | INTEGER |  |
| `starred` | INTEGER |  |
| `pr_s` | INTEGER | segundos |
| `pr_date` | TEXT |  |
| `effort_count` | INTEGER |  |
| `kom` | TEXT |  |
| `origin` | TEXT |  |
| `fetched_at` | TEXT | data e hora (ISO) |
| `efforts_at` | TEXT | data e hora (ISO) |

## `strava_library_efforts`

Os teus esforços históricos nos segmentos da biblioteca (do Strava).

| coluna | tipo | o que é |
|---|---|---|
| `effort_id` | INTEGER |  |
| `segment_id` | INTEGER |  |
| `start_date` | TEXT |  |
| `elapsed_s` | INTEGER | segundos |
| `moving_s` | INTEGER | segundos |
| `avg_watts` | REAL |  |
| `avg_hr` | REAL | frequência cardíaca |
| `activity_id` | INTEGER |  |

## `strava_segments`

Segmentos do Strava ligados a cada rota (com o teu PR).

| coluna | tipo | o que é |
|---|---|---|
| `route_id` | TEXT | → routes.id |
| `segment_id` | INTEGER |  |
| `name` | TEXT | nome |
| `distance_m` | REAL | metros |
| `avg_grade` | REAL |  |
| `climb_cat` | INTEGER |  |
| `start_m` | REAL | metros |
| `end_m` | REAL | metros |
| `pr_s` | INTEGER | segundos |
| `pr_date` | TEXT |  |
| `effort_count` | INTEGER |  |
| `kom` | TEXT |  |
| `fetched_at` | TEXT | data e hora (ISO) |

## `strength_hr`

Ginásio: a FC ao longo da sessão.

| coluna | tipo | o que é |
|---|---|---|
| `session_id` | TEXT | → a sessão |
| `t_s` | INTEGER | segundos |
| `hr_bpm` | INTEGER | batimentos por minuto |

## `strength_laps`

Ginásio: as voltas da sessão por voltas (séries, descansos, cardio).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `session_id` | TEXT | → a sessão |
| `lap_no` | INTEGER |  |
| `kind` | TEXT | tipo |
| `start_t_s` | INTEGER | segundos |
| `end_t_s` | INTEGER | segundos |
| `exercise_id` | INTEGER | → exercises.id |
| `reps` | INTEGER |  |
| `load_kg` | REAL | quilogramas |
| `rpe` | REAL |  |
| `odometer_km` | REAL |  |
| `distance_km` | REAL |  |
| `speed_kmh` | REAL |  |
| `incline_pct` | REAL | percentagem |
| `notes` | TEXT | notas |
| `avg_hr` | REAL | frequência cardíaca |
| `max_hr` | INTEGER | frequência cardíaca |
| `set_id` | INTEGER |  |
| `row_spm` | REAL |  |
| `row_pace_s` | REAL | segundos |
| `row_resistance` | INTEGER |  |

## `strength_sessions`

Sessões de ginásio: tempos, séries, volume, carga.

| coluna | tipo | o que é |
|---|---|---|
| `id` | TEXT | chave |
| `workout_id` | TEXT | → o treino |
| `name` | TEXT | nome |
| `status` | TEXT | estado (recording, completed, aborted… ou active/deleted) |
| `started_at` | TEXT | data e hora (ISO) |
| `ended_at` | TEXT | data e hora (ISO) |
| `elapsed_s` | INTEGER | segundos |
| `paused_s` | INTEGER | segundos |
| `total_sets` | INTEGER |  |
| `total_reps` | INTEGER |  |
| `volume_kg` | REAL | quilogramas |
| `avg_rpe` | REAL |  |
| `avg_hr` | REAL | frequência cardíaca |
| `max_hr` | INTEGER | frequência cardíaca |
| `load` | REAL | carga (escala TSS) |
| `load_source` | TEXT |  |
| `hr_zone_s` | TEXT | segundos |
| `lthr_at_session` | INTEGER |  |
| `weight_at_session_kg` | REAL | quilogramas |
| `fit_path` | TEXT |  |
| `modality` | TEXT |  |
| `mode` | TEXT |  |
| `distance_km` | REAL |  |

## `strength_set_parts`

Ginásio: as partes de uma série composta (complexos).

| coluna | tipo | o que é |
|---|---|---|
| `set_id` | INTEGER |  |
| `idx` | INTEGER | posição (0, 1, 2…) |
| `exercise_id` | INTEGER | → exercises.id |
| `reps` | INTEGER |  |

## `strength_sets`

Ginásio: cada série feita (exercício, reps, carga, RPE, tempos).

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `session_id` | TEXT | → a sessão |
| `item_idx` | INTEGER | posição (0, 1, 2…) |
| `exercise_id` | INTEGER | → exercises.id |
| `set_no` | INTEGER |  |
| `reps` | INTEGER |  |
| `load_kg` | REAL | quilogramas |
| `rpe` | REAL |  |
| `start_t_s` | INTEGER | segundos |
| `end_t_s` | INTEGER | segundos |
| `avg_hr` | REAL | frequência cardíaca |
| `max_hr` | INTEGER | frequência cardíaca |
| `planned_reps` | INTEGER |  |
| `planned_load_kg` | REAL | quilogramas |
| `logged_reps` | INTEGER |  |
| `logged_load_kg` | REAL | quilogramas |
| `edited_at` | TEXT | data e hora (ISO) |

## `strength_structures`

A estrutura (superséries, circuitos) de cada treino de ginásio.

| coluna | tipo | o que é |
|---|---|---|
| `workout_id` | TEXT | → o treino |
| `data` | TEXT |  |
| `updated_at` | TEXT | última alteração |

## `strength_workout_items`

Os exercícios de cada treino de ginásio (séries, reps, carga, descanso).

| coluna | tipo | o que é |
|---|---|---|
| `workout_id` | TEXT | → o treino |
| `idx` | INTEGER | posição (0, 1, 2…) |
| `exercise_id` | INTEGER | → exercises.id |
| `sets` | INTEGER |  |
| `reps` | INTEGER |  |
| `load_kg` | REAL | quilogramas |
| `rpe` | REAL |  |
| `rest_s` | INTEGER | segundos |
| `notes` | TEXT | notas |

## `strength_workouts`

Treinos de ginásio.

| coluna | tipo | o que é |
|---|---|---|
| `id` | TEXT | chave |
| `name` | TEXT | nome |
| `description` | TEXT |  |
| `created_at` | TEXT | quando foi criado |
| `updated_at` | TEXT | última alteração |
| `modality` | TEXT |  |
| `hidden` | INTEGER | 1 = escondido |

## `synced_activities`

Atividades importadas: GarminDB, TrainingPeaks, histórico do Strava/Garmin Connect, upload manual.

| coluna | tipo | o que é |
|---|---|---|
| `id` | TEXT | chave: «garmin:<id>», «tp:<hash>», «up:<sha>», … |
| `source` | TEXT | de onde veio: garmindb | trainingpeaks | strava | garmin | upload |
| `sport` | TEXT | cycling | running | swimming | rowing | gym | other |
| `source_sport` | TEXT | o desporto como a fonte o escreveu |
| `name` | TEXT | nome |
| `started_at` | TEXT | início (texto ISO; o Garmin em hora local) |
| `elapsed_s` | REAL | tempo total / em movimento (s) |
| `moving_s` | REAL | tempo total / em movimento (s) |
| `distance_m` | REAL | metros |
| `ascent_m` | REAL | metros |
| `avg_hr` | REAL | frequência cardíaca |
| `max_hr` | REAL | frequência cardíaca |
| `calories` | REAL |  |
| `training_load` | REAL | a carga que o Garmin calculou (informativa) |
| `imported_at` | TEXT | data e hora (ISO) |
| `tss` | REAL | carga e intensidade como o TrainingPeaks (sem dados: vazio) |
| `if_value` | REAL | carga e intensidade como o TrainingPeaks (sem dados: vazio) |
| `avg_power_w` | REAL | potência média / normalizada (W) |
| `np_w` | REAL | potência média / normalizada (W) |
| `fit_file` | TEXT | o .fit lido (com «!» à frente: não se conseguiu ler) |
| `tss_source` | TEXT | de onde veio a TSS: file | power | rtss | stss | trainingpeaks |
| `hr_zone_s` | TEXT | segundos em cada zona (JSON), para a longevidade |
| `power_zone_s` | TEXT | segundos em cada zona (JSON), para a longevidade |
| `description` | TEXT | o que o TrainingPeaks traz escrito |
| `coach_comments` | TEXT | o que o TrainingPeaks traz escrito |
| `athlete_comments` | TEXT | o que o TrainingPeaks traz escrito |

## `tag_catalog`

As etiquetas que existem.

| coluna | tipo | o que é |
|---|---|---|
| `tag` | TEXT |  |
| `kind` | TEXT | tipo |

## `test_results`

Os resultados de cada teste.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `test_id` | INTEGER |  |
| `done_on` | TEXT | data (AAAA-MM-DD) |
| `value` | REAL |  |
| `notes` | TEXT | notas |
| `ride_id` | TEXT | → rides.id |
| `extra` | TEXT |  |
| `created_at` | TEXT | quando foi criado |

## `trainer_calibrations`

As calibrações do rolo.

| coluna | tipo | o que é |
|---|---|---|
| `id` | INTEGER | chave |
| `device_id` | TEXT |  |
| `performed_at` | TEXT | data e hora (ISO) |
| `method` | TEXT |  |
| `detail` | TEXT |  |
| `success` | INTEGER |  |

## `training_plan`

O calendário: treinos planeados por dia.

| coluna | tipo | o que é |
|---|---|---|
| `id` | TEXT | chave |
| `day` | TEXT | dia (AAAA-MM-DD) |
| `sport` | TEXT | desporto |
| `workout_id` | TEXT | → o treino |
| `title` | TEXT |  |
| `notes` | TEXT | notas |
| `created_at` | TEXT | quando foi criado |

## `workout_goals`

O objetivo escrito de cada treino.

| coluna | tipo | o que é |
|---|---|---|
| `sport` | TEXT | desporto |
| `workout_id` | TEXT | → o treino |
| `goal` | TEXT |  |
| `blocks` | TEXT |  |
| `updated_at` | TEXT | última alteração |

## `workout_meta`

O tipo de controlo e o modo de cada treino (ERG/manual, potência/FC…).

| coluna | tipo | o que é |
|---|---|---|
| `sport` | TEXT | desporto |
| `workout_id` | TEXT | → o treino |
| `control` | TEXT |  |
| `mode` | TEXT |  |
| `blocks` | TEXT |  |

## `workout_step_results`

Ciclismo: o resultado de cada bloco de um treino (média, alvo, % no alvo).

| coluna | tipo | o que é |
|---|---|---|
| `ride_id` | TEXT | → rides.id |
| `step_idx` | INTEGER | posição (0, 1, 2…) |
| `avg_power_w` | REAL | watts |
| `target_avg_w` | REAL | watts |
| `pct_in_target` | REAL |  |
| `avg_hr` | REAL | frequência cardíaca |
| `avg_cadence` | REAL |  |

## `workout_steps`

Os blocos de cada treino de ciclismo (duração, alvo, cadência).

| coluna | tipo | o que é |
|---|---|---|
| `workout_id` | TEXT | → o treino |
| `idx` | INTEGER | posição (0, 1, 2…) |
| `kind` | TEXT | tipo |
| `duration_s` | INTEGER | segundos |
| `target_type` | TEXT |  |
| `target_lo` | REAL |  |
| `target_hi` | REAL |  |
| `cadence_lo` | INTEGER |  |
| `cadence_hi` | INTEGER |  |
| `text_cue` | TEXT |  |

## `workout_tags`

As etiquetas de cada treino.

| coluna | tipo | o que é |
|---|---|---|
| `sport` | TEXT | desporto |
| `workout_id` | TEXT | → o treino |
| `tag` | TEXT |  |

## `workout_types`

O tipo de cada treino (resistência, limiar, VO2máx…).

| coluna | tipo | o que é |
|---|---|---|
| `sport` | TEXT | desporto |
| `workout_id` | TEXT | → o treino |
| `wtype` | TEXT |  |

## `workouts`

Treinos de ciclismo (lista): nome, origem, descrição, duração, TSS estimada, estado.

| coluna | tipo | o que é |
|---|---|---|
| `id` | TEXT | chave |
| `name` | TEXT | nome |
| `source_format` | TEXT |  |
| `description` | TEXT |  |
| `total_seconds` | INTEGER |  |
| `est_tss` | REAL | Training Stress Score |
| `imported_at` | TEXT | data e hora (ISO) |
| `status` | TEXT | estado (recording, completed, aborted… ou active/deleted) |
