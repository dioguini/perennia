# O formato de um plano Perennia

Um plano é um ficheiro de texto **JSON** com o nome a acabar em `.perennia-plan.json`
(o formato completo), **ou uma tabela CSV** com o nome a acabar em `.perennia-plan.csv`
(a via fácil, feita no Excel/LibreOffice; ver `plano-modelo.perennia-plan.csv`: uma linha por
exercício de cada sessão, as linhas `# nome: …`, `# semanas: …`, `# rotacao: A,B` no topo, e
`70|75|80` numa célula para um valor por semana). O CSV não tem séries com valores diferentes
umas das outras: para isso usa o JSON.
Põe-no na pasta `workouts` (ao lado da aplicação), em Transferências ou em Documentos, e em
**Ginásio → Lista de treinos → Planos de X semanas → Importar plano…** escolhe-o. Se alguma
coisa não obedecer ao formato, a Perennia diz o campo e a razão, e não importa nada.

O ficheiro `plano-modelo.perennia-plan.json` é um plano pequeno, que funciona, com quase tudo
o que o formato tem: copia-o e muda-o. Também podes **exportar** qualquer plano que venha com
a Perennia (botão «Exportar (.json)» na ficha do plano) e partir daí.

## Campos de topo

| Campo | Obrigatório | O que é |
|---|---|---|
| `format` | sim | sempre `"perennia-plan"` |
| `version` | não | `1` |
| `name` | sim | o nome do plano (até 80 letras) |
| `description`, `author`, `source` | não | texto livre |
| `category` | não | `strength`, `powerlifting`, `bodybuilding`, `strongman`, `grip`, `longevity`, `general`, `conditioning`, `athletic`, `glutes`, `other` |
| `level` | não | `beginner`, `intermediate`, `advanced` |
| `weeks` | sim | número de semanas (1 a 104) |
| `exercises` | sim | os exercícios que o plano usa (ver abaixo) |
| `sessions` | sim | as sessões-tipo: «Treino A», «Treino B»… |
| `rotation` **ou** `schedule` | sim | a ordem das sessões (ver abaixo) |
| `days_per_week` | com `rotation` | sessões por semana (1 a 7) |
| `weekdays` | não | os dias por omissão: 1 = segunda … 7 = domingo. Ao começar o plano podes escolher outros |
| `equipment` | não | material, além do que os exercícios já pedem |

## `exercises`

Um objeto `chave → exercício`. A chave (letras, números, `_`, `-`) é o que as sessões usam.

```json
"squat": {"name": "Agachamento com barra", "group": "legs", "measure": "reps",
          "bodyweight": 0, "equipment": ["barbell", "plates", "rack"],
          "modality": "strength", "aliases": ["Back squat", "Squat"]}
```

- `name` — obrigatório. Se já existir um exercício com esse nome (ou com um dos `aliases`),
  sem contar acentos nem maiúsculas, usa-se esse; **se não existir, é criado** quando
  começares o plano.
- `group` — `legs`, `hips`, `chest`, `back`, `shoulders`, `arms`, `core`, `full`, `mobility`.
- `measure` — `reps` (por omissão) ou `time` (segundos).
- `bodyweight` — fração do peso do corpo que conta como carga (0 a 1; elevações = 1).
- `equipment` — tipos de material do Inventário: `barbell`, `plates`, `dumbbell`,
  `kettlebell`, `sandbag`, `rack`, `bench`, `pullup_bar`, `cable`, `bands`, `box`, `rings`,
  `leg_press`, `trap_bar`, `sled`, `gripper`, `fat_grips`, `wrist_roller`, `ab_wheel`…
- `modality` — a modalidade do ginásio onde fica (`strength`, `kettlebell`, `calisthenics`,
  `plyometrics`, `tendons`, `isometric`, `mobility`, `cardio`…).

## `sessions`

Um objeto `chave → sessão`. Cada sessão tem `name`, `notes` (opcional) e `blocks`.

Um bloco é **um exercício**:

```json
{"exercise": "squat", "sets": 5, "reps": 5, "rest": 180}
```

ou **um grupo** (`kind`: `superset`, `circuit`, `warmup`, `cooldown`) com `exercises`,
`rounds` (voltas do circuito) e `rest` (descanso entre voltas, em segundos):

```json
{"kind": "circuit", "rounds": 4, "rest": 90, "exercises": [
   {"exercise": "swing", "sets": 1, "reps": 10},
   {"exercise": "plank", "sets": 1, "time": 30}]}
```

### Campos de um exercício numa sessão

| Campo | O que é |
|---|---|
| `sets` | número de séries iguais, **ou** a lista das séries (cada uma com os campos abaixo) |
| `reps` | `5`, `"8-12"` (intervalo), `"5+"` (cinco ou mais: o máximo que der) ou `"max"` |
| `load` | carga em kg (fixa) |
| `pct1rm` | % da tua 1RM estimada: a carga calcula-se no momento da sessão |
| `rpe`, `rir` | esforço (1–10) ou repetições em reserva |
| `time` | segundos (para exercícios por tempo) |
| `distance` | metros |
| `rest` | descanso em segundos |
| `notes` | texto que aparece no exercício |

**Um valor por semana.** Qualquer número pode ser uma lista com um valor por semana:
`"pct1rm": [70, 75, 80, 60]`. Se a lista for mais curta do que o plano, o último repete-se.
`sets` também: `"sets": [3, 3, 4, 4]`.

**Séries diferentes na mesma sessão.**

```json
{"exercise": "squat", "sets": [
   {"reps": 5, "pct1rm": 65}, {"reps": 5, "pct1rm": 75}, {"reps": "5+", "pct1rm": 85}]}
```

**Progressão linear.** `"add_kg": 2.5` soma essa carga de cada vez que o exercício volta
(`"per": "session"`, por omissão) ou de semana a semana (`"per": "week"`). A **carga inicial**
pede-se quando começas o plano; `"start_pct": 50` sugere 50 % da tua 1RM estimada. Dentro de
uma lista de séries, `"of_top": 0.75` é a fração da carga principal (séries em rampa e de
recuo). Se o mesmo exercício tiver duas progressões diferentes no plano (uma pesada e uma de
volume), dá a cada uma um `"track"` próprio: `"track": "squat_volume"`.

## A ordem das sessões

- **`rotation`** — as sessões alternam por esta ordem ao longo de todos os dias do plano.
  Com `"rotation": ["A", "B"]` e `"days_per_week": 3`: semana 1 = A, B, A; semana 2 = B, A, B.
- **`schedule`** — a lista das sessões de cada semana. Com uma só semana, repete-se sempre:
  `"schedule": [["A", "B", "C"]]`. Com várias, segue-as por ordem (e volta ao princípio se o
  plano tiver mais semanas): `"schedule": [["V", "V", "V"], ["H1", "H2", "H3"]]`.

## Limites

Até 104 semanas, 60 sessões-tipo, 30 blocos por sessão, 12 exercícios por bloco, 30 séries por
exercício e 200 exercícios. O ficheiro não pode passar do tamanho definido em Definições →
Avançado → Planos de treino (512 kB por omissão). Só se lê JSON: um plano não pode trazer
código.

## Traduzir um plano que já existe

1. Copia `plano-modelo.perennia-plan.json` e muda `name`, `weeks` e `description`.
2. Lista os exercícios em `exercises` (usa os nomes da Perennia quando existirem; os outros
   são criados).
3. Escreve cada treino-tipo em `sessions`.
4. Se o plano alterna treinos (A/B), usa `rotation`; se cada semana tem dias fixos, usa
   `schedule`.
5. O que muda de semana para semana vai em listas (`[70, 75, 80]`); o que soma carga de cada
   vez vai em `add_kg`.
6. Importa. Se houver um erro, a mensagem diz o campo.
