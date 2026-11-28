"""Gera o DB.md: as tabelas e colunas da base de dados da Perennia, com o que cada uma guarda.

    python tools/db_doc.py                      # usa uma base nova (só o esquema)
    python tools/db_doc.py data/perennia.db     # a tua base (também conta as linhas)

O esquema vem da própria base (PRAGMA table_info), por isso está sempre certo; as descrições
estão aqui em baixo (TABLES e COLUMNS)."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TABLES = {
    "athlete": "O atleta: nome, ano de nascimento, peso, FTP, FC máxima, LTHR, bicicleta (peso, CdA, Crr).",
    "settings": "Todas as opções e definições (chave → valor em JSON): Definições, Avançado, ligações, estado.",
    "schema_version": "A versão do esquema (migrações aplicadas).",
    "rides": "Sessões de ciclismo: início/fim, tempos, distância, potência média/NP/TSS/IF, FC, estado, ficheiro .fit.",
    "ride_samples": "Ciclismo: uma amostra por segundo (potência, cadência, FC, velocidade, distância, equilíbrio).",
    "laps": "Ciclismo: as voltas de cada sessão (manuais, por bloco ou automáticas).",
    "ride_peaks": "Ciclismo: os picos de cada sessão (melhor potência/FC/cadência em cada duração).",
    "ride_power_curve": "Ciclismo: a curva de potência de cada sessão.",
    "ride_comparisons": "Ciclismo: comparação com o «fantasma» (outra sessão na mesma rota).",
    "workout_step_results": "Ciclismo: o resultado de cada bloco de um treino (média, alvo, % no alvo).",
    "climb_efforts": "Ciclismo: os esforços em cada subida de uma rota.",
    "chase_efforts": "Ciclismo: o jogo da perseguição (quanto aguentaste).",
    "game_results": "Resultados dos jogos (desafios dentro das sessões).",
    "ftp_tests": "Testes de FTP feitos e o FTP que deram.",
    "route_efforts": "Esforços completos numa rota (tempo, potência, FC).",
    "routes": "Rotas importadas (.gpx): distância, subida, inclinações, elevação.",
    "route_points": "Os pontos de cada rota (reamostrados): posição, elevação, inclinação, rumo.",
    "route_bakes": "Cache 3D das rotas (estado da preparação gráfica).",
    "climbs": "As subidas detetadas em cada rota.",
    "perennia_segments": "Segmentos definidos por ti numa rota (km de início e fim).",
    "segment_efforts": "Os teus tempos nos segmentos (Perennia e Strava), por sessão.",
    "strava_segments": "Segmentos do Strava ligados a cada rota (com o teu PR).",
    "strava_efforts": "Os teus tempos nos segmentos do Strava durante as sessões da Perennia.",
    "strava_library": "A biblioteca de segmentos importados do Strava (ficam neste computador).",
    "strava_library_efforts": "Os teus esforços históricos nos segmentos da biblioteca (do Strava).",
    "workouts": "Treinos de ciclismo (lista): nome, origem, descrição, duração, TSS estimada, estado.",
    "workout_steps": "Os blocos de cada treino de ciclismo (duração, alvo, cadência).",
    "workout_meta": "O tipo de controlo e o modo de cada treino (ERG/manual, potência/FC…).",
    "workout_goals": "O objetivo de cada treino (e dos blocos) e as notas do treinador (pré-treino), de todos os desportos.",
    "workout_types": "O tipo de cada treino (resistência, limiar, VO2máx…).",
    "workout_tags": "As etiquetas de cada treino.",
    "session_workouts": "A cópia do treino guardada com cada sessão (como foi feito).",
    "row_sessions": "Sessões de remo: tempos, distância, voltas de pá, potência, ritmo, carga (TSS), FC.",
    "row_samples": "Remo: uma amostra por segundo.",
    "row_laps": "Remo: as voltas de cada sessão.",
    "row_workouts": "Treinos de remo.",
    "row_workout_steps": "Os blocos de cada treino de remo.",
    "endurance_sessions": "Sessões de corrida e natação: tempos, distância, ritmo, FC, carga (rTSS/sTSS) e de onde veio.",
    "endurance_samples": "Corrida/natação: uma amostra por segundo (velocidade, distância, FC, inclinação).",
    "endurance_laps": "Corrida/natação: as voltas (e piscinas).",
    "endurance_workouts": "Treinos de corrida e natação.",
    "endurance_steps": "Os blocos de cada treino de corrida/natação.",
    "conditioning_parts": "As partes de uma sessão de Conditioning (blocos mistos).",
    "strength_sessions": "Sessões de ginásio: tempos, séries, volume, carga.",
    "strength_sets": "Ginásio: cada série feita (exercício, reps, carga, RPE, tempos).",
    "strength_set_parts": "Ginásio: as partes de uma série composta (complexos).",
    "strength_laps": "Ginásio: as voltas da sessão por voltas (séries, descansos, cardio).",
    "strength_hr": "Ginásio: a FC ao longo da sessão.",
    "strength_workouts": "Treinos de ginásio.",
    "strength_workout_items": "Os exercícios de cada treino de ginásio (séries, reps, carga, descanso).",
    "strength_structures": "A estrutura (superséries, circuitos) de cada treino de ginásio.",
    "exercises": "O catálogo de exercícios (categoria, medida, peso do corpo, subgrupo muscular).",
    "exercise_modalities": "As modalidades de cada exercício (força, mobilidade, HIIT…).",
    "exercise_equipment": "O equipamento de cada exercício.",
    "exercise_complex_parts": "As partes de um exercício complexo.",
    "muscle_groups": "Grupos musculares.",
    "muscle_subgroups": "Subgrupos musculares.",
    "gym_disciplines": "Disciplinas do ginásio.",
    "equipment_items": "O teu inventário (equipamento, quantidades, compra).",
    "lap_plans": "Planos de voltas guardados.",
    "programs": "Planos de treino (modelos) do ginásio.",
    "program_runs": "Planos de treino em curso.",
    "program_days": "Os dias de cada plano em curso.",
    "training_plan": "O calendário: treinos planeados por dia.",
    "coach_events": "O Treinador: eventos (provas) e as respostas que deste.",
    "challenges": "Os desafios (metas com prazo).",
    "challenge_attempts": "As tentativas de cada desafio.",
    "fitness_tests": "Os testes de condição física (incluindo os de longevidade).",
    "test_results": "Os resultados de cada teste.",
    "session_feedback": "O feedback de cada sessão (RPE, dores, sensação, comentário) e a análise automática (veredito e secções). kind: ride|row|endurance|strength|imported.",
    "session_tags": "As etiquetas de cada sessão (tipo de treino, Indoor…, livres).",
    "tag_catalog": "As etiquetas que existem.",
    "session_checkpoints": "O estado de uma sessão a decorrer (para a retomar se a app fechar).",
    "block_events": "Alterações feitas aos blocos durante uma sessão (+/−).",
    "synced_activities": "Atividades importadas: GarminDB, TrainingPeaks, histórico do Strava/Garmin Connect, upload manual.",
    "metric_defs": "As métricas do diário de saúde (nome, tipo, unidade, grupo, ativa).",
    "daily_values": "O diário de saúde: o valor de cada métrica em cada dia (e a fonte).",
    "day_notes": "A nota de cada dia.",
    "health_tabs": "Os separadores personalizados da Saúde.",
    "health_tab_notes": "As notas dos separadores da Saúde.",
    "bp_readings": "Medições da pressão arterial.",
    "lab_reports": "Análises clínicas: cada colheita.",
    "lab_results": "Análises clínicas: cada resultado (valor, referências).",
    "lab_parameters": "O catálogo dos parâmetros das análises.",
    "lab_glossary": "O glossário das análises (o que é, sobe/desce, bom/mau).",
    "glossary": "O glossário geral.",
    "devices": "Os aparelhos conhecidos (Bluetooth/ANT+): nome, perfis, prioridade, ligação automática.",
    "trainer_calibrations": "As calibrações do rolo.",
}

COLUMNS = {
    "synced_activities": {
        "id": "chave: «garmin:<id>», «tp:<hash>», «up:<sha>», …",
        "source": "de onde veio: garmindb | trainingpeaks | strava | garmin | upload",
        "sport": "cycling | running | swimming | rowing | gym | other",
        "source_sport": "o desporto como a fonte o escreveu",
        "started_at": "início (texto ISO; o Garmin em hora local)",
        "elapsed_s / moving_s": "tempo total / em movimento (s)",
        "tss / if_value": "carga e intensidade como o TrainingPeaks (sem dados: vazio)",
        "tss_source": "de onde veio a TSS: file | power | rtss | stss | trainingpeaks",
        "avg_power_w / np_w": "potência média / normalizada (W)",
        "hr_zone_s / power_zone_s": "segundos em cada zona (JSON), para a longevidade",
        "training_load": "a carga que o Garmin calculou (informativa)",
        "fit_file": "o .fit lido (com «!» à frente: não se conseguiu ler)",
        "description / coach_comments / athlete_comments": "o que o TrainingPeaks traz escrito",
    },
    "session_feedback": {
        "kind / session_id": "a sessão (ride, row, endurance, strength ou imported)",
        "rpe / pain / feel / goal_met / comment": "o teu feedback (vazio = só análise automática)",
        "verdict / useful": "o veredito da análise",
        "analysis": "a análise completa (JSON: secções, execução, objetivo)",
    },
    "settings": {"key": "nome da opção", "value": "valor em JSON"},
    "workout_goals": {"sport": "cycling | rowing | running | swimming | gym | conditioning",
                      "goal": "o objetivo do treino (o que desenvolve)",
                      "blocks": "o objetivo de cada bloco (JSON)",
                      "notes": "as notas do treinador (pré-treino), à parte do objetivo"},
    "daily_values": {"day": "AAAA-MM-DD", "metric_id": "→ metric_defs.id",
                     "num / txt": "o valor (número ou texto)", "source": "de onde veio"},
}

COMMON = {"id": "chave", "created_at": "quando foi criado", "updated_at": "última alteração",
          "status": "estado (recording, completed, aborted… ou active/deleted)",
          "session_id": "→ a sessão", "ride_id": "→ rides.id", "route_id": "→ routes.id",
          "workout_id": "→ o treino", "exercise_id": "→ exercises.id"}


SUFFIX = (("_at", "data e hora (ISO)"), ("_on", "data (AAAA-MM-DD)"), ("_s", "segundos"),
          ("_m", "metros"), ("_mps", "metros por segundo"), ("_w", "watts"),
          ("_bpm", "batimentos por minuto"), ("_kg", "quilogramas"), ("_pct", "percentagem"),
          ("_rpm", "rotações por minuto"), ("_deg", "graus"), ("_json", "JSON"),
          ("day", "dia (AAAA-MM-DD)"), ("name", "nome"), ("notes", "notas"),
          ("sport", "desporto"), ("sort", "ordem"), ("idx", "posição (0, 1, 2…)"),
          ("kind", "tipo"), ("load", "carga (escala TSS)"), ("tss", "Training Stress Score"),
          ("hr", "frequência cardíaca"), ("custom", "1 = criado por ti"),
          ("builtin", "1 = vem com a Perennia"), ("hidden", "1 = escondido"))


def guess(col: str) -> str:
    for suf, text in SUFFIX:
        if col == suf or col.endswith(suf):
            return text
    return ""


def schema(path: Path | None) -> tuple[sqlite3.Connection, Path]:
    if path is not None:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True), path
    from tests import pyglet_stub
    pyglet_stub.install()
    from perennia.ui import app as app_mod
    from perennia.core import backup, feedback, garmin_sync
    a = app_mod.App(data_dir=Path(tempfile.mkdtemp()), width=1280, height=760)
    backup.prepare(a.db)
    garmin_sync.ensure(a.db)
    feedback.ensure(a.db)
    return a.db.conn, a.db.path


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else None
    conn, used = schema(path)
    out = ["# A base de dados da Perennia", "",
           "Gerado por `python tools/db_doc.py`. É uma base **SQLite** num só ficheiro: "
           "`data/perennia.db` (ver RUN.md, «A base de dados»). Ao lado ficam `perennia.db-wal` e "
           "`perennia.db-shm` (o modo WAL): para copiar a base, fecha a Perennia antes.", "",
           f"{len(TABLES)} tabelas descritas.", ""]
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"
                                        " AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for name in names:
        cols = conn.execute(f"PRAGMA table_info({name})").fetchall()
        n = ""
        if path is not None:
            try:
                n = f" · {conn.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]} linhas"
            except sqlite3.Error:
                n = ""
        out += [f"## `{name}`{n}", "", TABLES.get(name, "(sem descrição)"), "",
                "| coluna | tipo | o que é |", "|---|---|---|"]
        desc = {}
        for k, v in COLUMNS.get(name, {}).items():
            for part in k.split(" / "):
                desc[part.strip()] = v
        for c in cols:
            out.append(f"| `{c[1]}` | {c[2] or ''} | {desc.get(c[1], COMMON.get(c[1], guess(c[1])))} |")
        out.append("")
    (ROOT / "DB.md").write_text("\n".join(out), encoding="utf-8")
    print(f"DB.md: {len(names)} tabelas ({used})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
