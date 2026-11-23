"""O glossário de origem das análises clínicas, nos dois idiomas.

Cada componente tem uma chave estável (é por ela que uma edição tua se liga ao de origem — nunca
a mudes), uma categoria, o nome, os nomes alternativos por que aparece nos boletins dos
laboratórios (`aliases`, sem acentos nem maiúsculas) e, em cada idioma:

* `s`    — a descrição sumária (a que aparece ao passar o rato por cima de um resultado);
* `w`    — o que é;
* `up`   — o que faz subir os valores;
* `down` — o que faz descer os valores;
* `good` — no geral, o que é bom para este componente;
* `bad`  — no geral, o que é mau;
* `act`  — estratégias para o pôr (ou manter) dentro do intervalo.

É informação geral, para perceberes os teus resultados — não substitui o médico, que conhece o
teu caso. Os componentes que acrescentas (ou as tuas edições) ficam na base de dados, na tabela
`lab_glossary`, e não aqui.
"""
from __future__ import annotations

# categoria: (chave, pt, en) — pela ordem em que aparecem no separador
CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("blood", "Hemograma", "Blood count"),
    ("iron", "Ferro e vitaminas", "Iron and vitamins"),
    ("glucose", "Açúcar no sangue", "Blood sugar"),
    ("lipids", "Gorduras no sangue (lípidos)", "Blood fats (lipids)"),
    ("kidney", "Rim", "Kidney"),
    ("liver", "Fígado e proteínas", "Liver and proteins"),
    ("inflammation", "Inflamação", "Inflammation"),
    ("thyroid", "Tiroide", "Thyroid"),
    ("hormones", "Hormonas", "Hormones"),
    ("minerals", "Minerais e eletrólitos", "Minerals and electrolytes"),
    ("muscle", "Músculo e esforço", "Muscle and effort"),
    ("other", "Outros", "Other"),
)

MARKERS: list[dict] = []


def _m(key: str, cat: str, names: tuple[str, str], aliases: tuple[str, ...],
       pt: tuple[str, str, str, str, str, str, str],
       en: tuple[str, str, str, str, str, str, str]) -> None:
    fields = ("s", "w", "up", "down", "good", "bad", "act")
    MARKERS.append({"key": key, "cat": cat, "name": names, "aliases": aliases,
                    "pt": dict(zip(fields, pt)), "en": dict(zip(fields, en))})


# ===================================================================== hemograma

_m("rbc", "blood", ("Eritrócitos (glóbulos vermelhos)", "Red blood cells"),
   ("eritrocitos", "globulos vermelhos", "hemacias", "rbc", "red blood cells", "erythrocytes"),
   ("As células que levam o oxigénio dos pulmões aos músculos.",
    "Contagem de glóbulos vermelhos por volume de sangue. Transportam o oxigénio (através da "
    "hemoglobina) e são a base da capacidade aeróbia.",
    "Altitude, desidratação (o sangue fica concentrado), tabaco, testosterona/EPO, apneia do "
    "sono.",
    "Falta de ferro, B12 ou ácido fólico, perdas de sangue, doença crónica, excesso de água "
    "(hemodiluição) — e a «pseudo-anemia» dos atletas de resistência, que é normal.",
    "Ferro, B12 e folato suficientes; dormir bem; treino de resistência bem doseado.",
    "Perdas de sangue, dietas muito restritivas, tabaco, sobretreino.",
    "Baixo: rever ferro, B12 e folato com o médico e comer as fontes (carne, peixe, ovos, "
    "leguminosas, folhas verdes). Alto: hidratar bem antes da colheita e falar com o médico se "
    "persistir."),
   ("The cells that carry oxygen from the lungs to the muscles.",
    "Red blood cell count per blood volume. They carry oxygen (through haemoglobin) and are "
    "the basis of aerobic capacity.",
    "Altitude, dehydration, smoking, testosterone/EPO, sleep apnoea.",
    "Low iron, B12 or folate, blood loss, chronic disease, endurance athletes' normal "
    "dilution.",
    "Enough iron, B12 and folate; good sleep; well-dosed endurance training.",
    "Blood loss, very restrictive diets, smoking, overtraining.",
    "Low: check iron, B12 and folate with the doctor. High: hydrate well before the test and "
    "see the doctor if it persists."))

_m("hgb", "blood", ("Hemoglobina", "Haemoglobin"),
   ("hemoglobina", "hgb", "hb", "haemoglobin", "hemoglobin"),
   ("A proteína dos glóbulos vermelhos que agarra o oxigénio; baixa = anemia.",
    "Proteína com ferro dentro dos glóbulos vermelhos que transporta o oxigénio. É o valor que "
    "define a anemia e pesa diretamente no VO2máx.",
    "Altitude, desidratação, tabaco, testosterona, doenças pulmonares.",
    "Falta de ferro (a causa mais comum), de B12 ou de folato, perdas de sangue (menstruação, "
    "intestino, doação), doença crónica, hemodiluição do treino de resistência.",
    "Carne vermelha magra, peixe, ovos, leguminosas e folhas verdes com vitamina C na mesma "
    "refeição; dormir e recuperar.",
    "Chá/café às refeições (prendem o ferro), dietas pobres, perdas de sangue não vigiadas.",
    "Baixa: ver a ferritina; se faltar ferro, reforçar fontes de ferro (+ vitamina C) e, com o "
    "médico, suplementar. Espaçar doações de sangue. Alta: hidratar e confirmar."),
   ("The iron protein in red cells that holds oxygen; low = anaemia.",
    "Iron-containing protein inside red cells that carries oxygen. It defines anaemia and "
    "directly affects VO2max.",
    "Altitude, dehydration, smoking, testosterone, lung disease.",
    "Low iron (most common), B12 or folate, blood loss, chronic disease, endurance dilution.",
    "Lean red meat, fish, eggs, legumes and greens with vitamin C; sleep and recovery.",
    "Tea/coffee with meals (block iron), poor diets, unchecked blood loss.",
    "Low: check ferritin and, with the doctor, supplement iron. Space out blood donations. "
    "High: hydrate and recheck."))

_m("hct", "blood", ("Hematócrito", "Haematocrit"),
   ("hematocrito", "hct", "ht", "haematocrit", "hematocrit", "pcv"),
   ("A percentagem do sangue ocupada por glóbulos vermelhos.",
    "Fração do volume de sangue feita de glóbulos vermelhos. Acompanha a hemoglobina; muito "
    "alto torna o sangue mais espesso.",
    "Desidratação, altitude, tabaco, testosterona/EPO.",
    "Anemia (ferro, B12, folato), perdas de sangue, muita água ou expansão do plasma com o "
    "treino.",
    "Boa hidratação, ferro e vitaminas suficientes.",
    "Desidratação crónica (sobe), perdas de sangue (desce).",
    "Alto: beber água regularmente e fazer a colheita bem hidratado; se persistir, médico "
    "(pode justificar doar sangue). Baixo: tratar a causa da anemia."),
   ("The share of blood volume taken by red cells.",
    "Fraction of blood volume made of red cells. Follows haemoglobin; very high makes blood "
    "thicker.",
    "Dehydration, altitude, smoking, testosterone/EPO.",
    "Anaemia, blood loss, plasma expansion from training.",
    "Good hydration, enough iron and vitamins.",
    "Chronic dehydration (raises), blood loss (lowers).",
    "High: hydrate; if it persists see the doctor (donating blood may help). Low: treat the "
    "anaemia cause."))

_m("mcv", "blood", ("VGM (volume globular médio)", "MCV (mean cell volume)"),
   ("vgm", "volume globular medio", "volume corpuscular medio", "vcm", "mcv", "mean corpuscular volume", "mean cell volume"),
   ("O tamanho médio dos glóbulos vermelhos: pequenos = ferro, grandes = B12/folato.",
    "Tamanho médio de cada glóbulo vermelho. Ajuda a perceber a causa de uma anemia.",
    "Falta de B12 ou de ácido fólico, álcool, alguns medicamentos, fígado, tiroide lenta.",
    "Falta de ferro, talassemia (traço genético), doença crónica.",
    "Ferro, B12 e folato equilibrados; pouco álcool.",
    "Álcool em excesso (sobe), dieta pobre em ferro (desce).",
    "Alto: ver B12 e folato, reduzir álcool. Baixo: ver ferritina e ferro; se o ferro estiver "
    "bem, perguntar ao médico por talassemia."),
   ("Average red cell size: small = iron, large = B12/folate.",
    "Average size of each red cell. Helps find the cause of anaemia.",
    "Low B12 or folate, alcohol, some drugs, liver, slow thyroid.",
    "Low iron, thalassaemia trait, chronic disease.",
    "Balanced iron, B12 and folate; little alcohol.",
    "Excess alcohol (raises), iron-poor diet (lowers).",
    "High: check B12/folate, cut alcohol. Low: check ferritin and iron."))

_m("mch", "blood", ("HGM (hemoglobina globular média)", "MCH (mean cell haemoglobin)"),
   ("hgm", "hemoglobina globular media", "hemoglobina corpuscular media", "hcm", "mch", "mean corpuscular hemoglobin"),
   ("A quantidade de hemoglobina em cada glóbulo vermelho.",
    "Hemoglobina média por glóbulo vermelho. Anda a par do VGM.",
    "Falta de B12/folato (glóbulos grandes).",
    "Falta de ferro, talassemia.",
    "Ferro, B12 e folato suficientes.",
    "Dieta pobre em ferro; álcool.",
    "Ler junto com o VGM e a ferritina: baixo → ferro; alto → B12/folato."),
   ("Haemoglobin amount in each red cell.",
    "Average haemoglobin per red cell. Moves with MCV.",
    "Low B12/folate (large cells).", "Low iron, thalassaemia.",
    "Enough iron, B12 and folate.", "Iron-poor diet; alcohol.",
    "Read with MCV and ferritin: low → iron; high → B12/folate."))

_m("mchc", "blood", ("CHGM (concentração de hemoglobina)", "MCHC"),
   ("chgm", "concentracao de hemoglobina globular media", "chcm",
    "concentracao de hemoglobina corpuscular media", "mchc"),
   ("A concentração de hemoglobina dentro dos glóbulos vermelhos.",
    "Quão «cheios» de hemoglobina estão os glóbulos vermelhos.",
    "Desidratação da amostra, esferocitose (rara).",
    "Falta de ferro.",
    "Ferro suficiente.", "Falta de ferro prolongada.",
    "Baixa: ver ferritina e ferro. Alta isolada: normalmente repetir a análise."),
   ("Haemoglobin concentration inside red cells.",
    "How «full» of haemoglobin the red cells are.",
    "Sample issues, spherocytosis (rare).", "Low iron.",
    "Enough iron.", "Long-term low iron.",
    "Low: check ferritin and iron. Isolated high: usually repeat the test."))

_m("rdw", "blood", ("RDW (variação do tamanho)", "RDW"),
   ("rdw", "amplitude de distribuicao eritrocitaria", "red cell distribution width",
    "indice de anisocitose"),
   ("Quão diferentes são os glóbulos vermelhos entre si; alto = falta de algo em curso.",
    "Mede a variação de tamanho dos glóbulos vermelhos. Sobe cedo quando começa a faltar ferro, "
    "B12 ou folato.",
    "Falta de ferro, B12 ou folato a instalar-se, recuperação de uma anemia, inflamação.",
    "Raramente baixa (sem significado).",
    "Alimentação variada com ferro, B12 e folato.",
    "Défices nutricionais, inflamação crónica.",
    "Alto: ver ferritina, B12 e ácido fólico — muitas vezes é o primeiro sinal."),
   ("How different red cells are from each other; high = something running low.",
    "Variation in red cell size. Rises early when iron, B12 or folate start to run low.",
    "Developing iron/B12/folate deficit, anaemia recovery, inflammation.",
    "Rarely low (no meaning).", "Varied diet with iron, B12 and folate.",
    "Nutrient deficits, chronic inflammation.",
    "High: check ferritin, B12 and folate — often the first sign."))

_m("wbc", "blood", ("Leucócitos (glóbulos brancos)", "White blood cells"),
   ("leucocitos", "globulos brancos", "wbc", "white blood cells", "leukocytes"),
   ("As células de defesa do corpo (sistema imunitário).",
    "Total de glóbulos brancos: neutrófilos, linfócitos, monócitos, eosinófilos e basófilos. "
    "Mostram infeções, inflamação e o estado do sistema imunitário.",
    "Infeção (sobretudo bacteriana), inflamação, stress, treino muito intenso nas horas antes, "
    "tabaco, corticoides.",
    "Algumas infeções virais, sobretreino, falta de B12/folato, alguns medicamentos, e em "
    "muitos atletas é só ligeiramente baixo (normal).",
    "Dormir 7–9 h, energia suficiente, vitamina D e proteína adequadas, gerir o stress.",
    "Sobretreino, pouco sono, défice calórico grande, tabaco.",
    "Fazer a colheita longe de um treino duro (24–48 h). Alto: ver se há infeção. Baixo e "
    "persistente: aliviar a carga, dormir mais e falar com o médico."),
   ("The body's defence cells (immune system).",
    "Total white cells: neutrophils, lymphocytes, monocytes, eosinophils, basophils. Show "
    "infection, inflammation and immune state.",
    "Infection, inflammation, stress, hard training in the hours before, smoking, steroids.",
    "Some viral infections, overtraining, low B12/folate, some drugs; slightly low is common "
    "in athletes.",
    "7–9 h of sleep, enough energy, vitamin D and protein, stress management.",
    "Overtraining, little sleep, large calorie deficit, smoking.",
    "Test 24–48 h after hard training. High: look for infection. Persistently low: reduce "
    "load, sleep more, see the doctor."))

_m("neut", "blood", ("Neutrófilos", "Neutrophils"),
   ("neutrofilos", "neutrofilos segmentados", "neut", "neutrophils"),
   ("Os glóbulos brancos da primeira linha contra bactérias.",
    "O tipo mais comum de glóbulo branco; respondem às infeções bacterianas e à inflamação.",
    "Infeção bacteriana, inflamação, exercício intenso recente, stress, corticoides, tabaco.",
    "Infeções virais, sobretreino, falta de B12/folato, alguns medicamentos; ligeiramente "
    "baixos em algumas pessoas saudáveis.",
    "Recuperação adequada, sono, alimentação completa.",
    "Sobretreino, stress crónico.",
    "Alto: procurar infeção/inflamação. Baixo persistente: médico; reduzir a carga."),
   ("First-line white cells against bacteria.",
    "Most common white cell; respond to bacterial infection and inflammation.",
    "Bacterial infection, inflammation, recent hard exercise, stress, steroids, smoking.",
    "Viral infections, overtraining, low B12/folate, some drugs.",
    "Adequate recovery, sleep, complete diet.", "Overtraining, chronic stress.",
    "High: look for infection. Persistently low: doctor; reduce load."))

_m("lymph", "blood", ("Linfócitos", "Lymphocytes"),
   ("linfocitos", "lymph", "lymphocytes"),
   ("Os glóbulos brancos da defesa contra vírus e da memória imunitária.",
    "Incluem as células T e B: defesa contra vírus e anticorpos.",
    "Infeções virais (mononucleose, gripe), recuperação de infeções.",
    "Stress, sobretreino, corticoides, pouco sono, infeções graves.",
    "Sono, vitamina D, zinco e proteína suficientes.",
    "Stress crónico, sobretreino, défice de sono.",
    "Baixos: dormir e recuperar; ver vitamina D e zinco. Altos: normalmente uma virose recente."),
   ("White cells against viruses and for immune memory.",
    "Include T and B cells: antiviral defence and antibodies.",
    "Viral infections, recovery from infections.",
    "Stress, overtraining, steroids, poor sleep, severe infections.",
    "Sleep, vitamin D, zinc and protein.", "Chronic stress, overtraining, sleep debt.",
    "Low: sleep and recover; check vitamin D and zinc. High: usually a recent virus."))

_m("mono", "blood", ("Monócitos", "Monocytes"),
   ("monocitos", "mono", "monocytes"),
   ("Glóbulos brancos que «limpam» e reparam tecidos.",
    "Transformam-se em macrófagos: limpam restos, combatem infeções crónicas e ajudam a "
    "reparar.",
    "Infeções crónicas, inflamação, recuperação de uma infeção, treino muito pesado.",
    "Corticoides, alguns problemas da medula (raro).",
    "Recuperação adequada.", "Inflamação crónica.",
    "Alto ligeiro e isolado: normalmente sem importância; repetir. Persistente: médico."),
   ("White cells that clean up and repair tissue.",
    "Become macrophages: clear debris, fight chronic infection, help repair.",
    "Chronic infection, inflammation, infection recovery, very heavy training.",
    "Steroids, rare marrow problems.", "Adequate recovery.", "Chronic inflammation.",
    "Mildly high and isolated: usually harmless; repeat. Persistent: doctor."))

_m("eos", "blood", ("Eosinófilos", "Eosinophils"),
   ("eosinofilos", "eos", "eosinophils"),
   ("Glóbulos brancos das alergias e dos parasitas.",
    "Sobem nas reações alérgicas (asma, rinite, pele) e nas parasitoses.",
    "Alergias, asma, eczema, parasitas, alguns medicamentos.",
    "Stress agudo, corticoides (sem significado em geral).",
    "Controlar as alergias.", "Alergias mal controladas.",
    "Altos: ver alergias/asma; se muito altos, o médico pode pedir pesquisa de parasitas."),
   ("White cells of allergies and parasites.",
    "Rise with allergic reactions (asthma, rhinitis, skin) and parasites.",
    "Allergies, asthma, eczema, parasites, some drugs.",
    "Acute stress, steroids (usually meaningless).", "Allergy control.",
    "Poorly controlled allergies.",
    "High: check allergies/asthma; very high: the doctor may test for parasites."))

_m("baso", "blood", ("Basófilos", "Basophils"),
   ("basofilos", "baso", "basophils"),
   ("Os glóbulos brancos mais raros; ligados às alergias.",
    "Libertam histamina nas reações alérgicas.",
    "Alergias, inflamação crónica, tiroide lenta.",
    "Sem significado clínico habitual.",
    "Controlar as alergias.", "Alergias mal controladas.",
    "Isoladamente quase nunca é relevante; ler com o resto do hemograma."),
   ("The rarest white cells; tied to allergies.",
    "Release histamine in allergic reactions.",
    "Allergies, chronic inflammation, slow thyroid.", "Usually no clinical meaning.",
    "Allergy control.", "Poorly controlled allergies.",
    "Rarely relevant on its own; read with the rest of the count."))

_m("plt", "blood", ("Plaquetas", "Platelets"),
   ("plaquetas", "plt", "trombocitos", "platelets"),
   ("As células que fazem o sangue coagular.",
    "Fragmentos que fecham feridas e iniciam a coagulação.",
    "Falta de ferro, inflamação, infeção, depois de exercício intenso, remoção do baço.",
    "Infeções virais, álcool, alguns medicamentos, doenças autoimunes, falta de B12/folato.",
    "Ferro, B12 e folato suficientes; pouco álcool.",
    "Álcool em excesso.",
    "Altas: ver ferritina e inflamação. Baixas: médico (pode ser uma virose passageira)."),
   ("The cells that make blood clot.",
    "Fragments that seal wounds and start clotting.",
    "Low iron, inflammation, infection, after hard exercise, no spleen.",
    "Viral infections, alcohol, some drugs, autoimmune disease, low B12/folate.",
    "Enough iron, B12 and folate; little alcohol.", "Excess alcohol.",
    "High: check ferritin and inflammation. Low: doctor (often a passing virus)."))

# ============================================================= ferro e vitaminas

_m("iron", "iron", ("Ferro sérico", "Serum iron"),
   ("ferro", "ferro serico", "iron", "serum iron", "fe"),
   ("O ferro a circular no sangue neste momento (varia muito ao longo do dia).",
    "Ferro em trânsito no sangue. Oscila com a refeição anterior e a hora; o depósito vê-se "
    "pela ferritina.",
    "Refeição rica em ferro ou suplementos nas horas antes, carne vermelha frequente, "
    "hemocromatose, transfusões.",
    "Falta de ferro, inflamação/infeção (o corpo «esconde» o ferro), perdas de sangue, colheita "
    "à tarde.",
    "Carne vermelha magra, fígado, mariscos, leguminosas, espinafres e brócolos com vitamina C "
    "(citrinos, pimento).",
    "Chá, café, cacau e cálcio às refeições principais; muitos cereais integrais com fitatos.",
    "Fazer a colheita de manhã, em jejum, sem suplementos na véspera. Baixo: reforçar fontes "
    "de ferro + vitamina C e afastar o café/chá das refeições. Alto: ver ferritina e saturação."),
   ("Iron circulating in the blood right now (varies a lot during the day).",
    "Iron in transit. Swings with the last meal and time of day; stores show in ferritin.",
    "Iron-rich meal or supplements before, frequent red meat, haemochromatosis, transfusions.",
    "Iron deficit, inflammation/infection, blood loss, afternoon sampling.",
    "Lean red meat, liver, shellfish, legumes, spinach and broccoli with vitamin C.",
    "Tea, coffee, cocoa and calcium with main meals.",
    "Test in the morning, fasting, no supplements the day before. Low: more iron + vitamin C, "
    "coffee/tea away from meals. High: check ferritin and saturation."))

_m("ferritin", "iron", ("Ferritina", "Ferritin"),
   ("ferritina", "ferritin"),
   ("O depósito de ferro do corpo; baixa = reservas vazias, alta = ferro a mais ou inflamação.",
    "Proteína que guarda o ferro. É o melhor indicador das reservas. Nos atletas de "
    "resistência, abaixo de ~30–50 ng/mL já pode baixar o rendimento mesmo sem anemia.",
    "Muito ferro na dieta (muita carne vermelha, suplementos), álcool, hemocromatose "
    "(genética), fígado gordo, inflamação ou infeção (sobe sem haver mais ferro), excesso de "
    "peso.",
    "Pouca ingestão de ferro (dietas vegetarianas mal planeadas), perdas de sangue "
    "(menstruação, intestino, doação de sangue), muito treino de corrida (pequenas perdas), "
    "absorção fraca.",
    "Ferro na medida certa: carne vermelha 1–2×/semana, peixe, leguminosas, folhas verdes; "
    "vitamina C com as refeições.",
    "Excesso de carne vermelha e de suplementos sem necessidade (sobe); café/chá às refeições, "
    "perdas de sangue (desce).",
    "Alta: reduzir carne vermelha e suplementos de ferro, moderar o álcool, confirmar com a "
    "saturação da transferrina e a PCR; se o ferro estiver mesmo a mais, doar sangue "
    "regularmente é a forma mais eficaz de o baixar (com o médico). Baixa: reforçar o ferro da "
    "dieta, separar café/chá das refeições, adiar doações e, com o médico, suplementar."),
   ("The body's iron store; low = empty reserves, high = too much iron or inflammation.",
    "Iron storage protein — the best marker of reserves. Endurance athletes may lose "
    "performance below ~30–50 ng/mL even without anaemia.",
    "Lots of dietary iron (much red meat, supplements), alcohol, haemochromatosis, fatty "
    "liver, inflammation or infection, excess weight.",
    "Low iron intake, blood loss (menstruation, gut, donation), lots of running, poor "
    "absorption.",
    "Balanced iron: red meat 1–2×/week, fish, legumes, greens; vitamin C with meals.",
    "Too much red meat/supplements (raises); coffee/tea with meals, blood loss (lowers).",
    "High: cut red meat and iron supplements, moderate alcohol, confirm with transferrin "
    "saturation and CRP; if iron is truly high, regular blood donation lowers it best (with the "
    "doctor). Low: more dietary iron, coffee/tea away from meals, delay donations, supplement "
    "with the doctor."))

_m("transferrin", "iron", ("Transferrina", "Transferrin"),
   ("transferrina", "transferrin", "ctfe", "capacidade total de fixacao do ferro", "tibc"),
   ("O «camião» que leva o ferro no sangue; sobe quando falta ferro.",
    "Proteína que transporta o ferro. Quando as reservas estão vazias o fígado fabrica mais.",
    "Falta de ferro, gravidez, pílula.",
    "Inflamação, má nutrição proteica, doença do fígado, ferro a mais.",
    "Ferro e proteína suficientes.", "Dieta pobre em proteína.",
    "Ler com a ferritina e a saturação: transferrina alta + ferritina baixa = falta de ferro."),
   ("The «truck» that carries iron; rises when iron is low.",
    "Iron transport protein. When stores are empty the liver makes more.",
    "Iron deficit, pregnancy, the pill.",
    "Inflammation, low protein intake, liver disease, iron overload.",
    "Enough iron and protein.", "Low-protein diet.",
    "Read with ferritin and saturation: high transferrin + low ferritin = iron deficit."))

_m("tsat", "iron", ("Saturação da transferrina", "Transferrin saturation"),
   ("saturacao da transferrina", "saturacao transferrina", "ist", "tsat",
    "transferrin saturation", "indice de saturacao da transferrina"),
   ("Que parte dos «camiões» do ferro vai cheia; alta = ferro a mais.",
    "Percentagem da transferrina ocupada com ferro. Acima de ~45 % pede para ver se há "
    "acumulação de ferro.",
    "Suplementos ou muita carne vermelha, hemocromatose, álcool, fígado.",
    "Falta de ferro, inflamação.",
    "Ferro na medida certa.", "Excesso de ferro (sobe), perdas de sangue (desce).",
    "Alta repetida: reduzir ferro da dieta e suplementos, moderar o álcool, médico "
    "(hemocromatose); doar sangue ajuda. Baixa: reforçar o ferro."),
   ("How full the iron «trucks» are; high = too much iron.",
    "Percentage of transferrin carrying iron. Above ~45 % warrants checking for iron overload.",
    "Supplements or much red meat, haemochromatosis, alcohol, liver.",
    "Iron deficit, inflammation.", "Balanced iron.",
    "Excess iron (raises), blood loss (lowers).",
    "Repeatedly high: cut dietary iron and supplements, moderate alcohol, see the doctor; "
    "donating blood helps. Low: more iron."))

_m("b12", "iron", ("Vitamina B12", "Vitamin B12"),
   ("vitamina b12", "b12", "cobalamina", "cianocobalamina", "vitamin b12", "cobalamin"),
   ("Vitamina dos nervos e dos glóbulos vermelhos; só existe em alimentos de origem animal.",
    "Necessária para fabricar glóbulos vermelhos e para os nervos. Falta → anemia de glóbulos "
    "grandes, cansaço, formigueiros.",
    "Suplementos, fígado, carne e marisco frequentes (raramente é um problema).",
    "Dieta vegetariana/vegana sem suplemento, gastrite, metformina, antiácidos (omeprazol), "
    "idade, álcool.",
    "Carne, peixe (sardinha, salmão, atum), marisco, ovos, lacticínios.",
    "Antiácidos prolongados, álcool, dieta sem produtos animais.",
    "Baixa: mais peixe, ovos e lacticínios; nos vegetarianos, suplemento. Com antiácidos ou "
    "metformina, vigiar com o médico. Alta sem suplementos: falar com o médico."),
   ("Nerve and red-cell vitamin; only in animal foods.",
    "Needed to make red cells and for nerves. Lack → large-cell anaemia, tiredness, tingling.",
    "Supplements, liver, frequent meat and shellfish.",
    "Vegetarian/vegan diet without supplement, gastritis, metformin, antacids, age, alcohol.",
    "Meat, fish, shellfish, eggs, dairy.", "Long-term antacids, alcohol, no animal foods.",
    "Low: more fish, eggs, dairy; vegetarians supplement. High without supplements: doctor."))

_m("folate", "iron", ("Ácido fólico (folato)", "Folate (folic acid)"),
   ("acido folico", "folato", "folatos", "b9", "vitamina b9", "folate", "folic acid"),
   ("Vitamina das folhas verdes; faz glóbulos vermelhos e baixa a homocisteína.",
    "Vitamina B9: precisa-se dela para dividir células (glóbulos vermelhos, intestino) e para "
    "baixar a homocisteína.",
    "Suplementos, cereais fortificados, muitos vegetais verdes.",
    "Poucos vegetais, álcool, alguns medicamentos (metotrexato, antiepiléticos), problemas de "
    "absorção.",
    "Legumes de folha escura e crucíferas (brócolos, espinafres, couves, espargos), leguminosas "
    "(grão, lentilhas, feijão), abacate, citrinos, fígado.",
    "Álcool, dieta pobre em vegetais, cozer demais os legumes (destrói o folato).",
    "Baixo: brócolos, espinafres, leguminosas e citrinos todos os dias, cozinhados ao vapor ou "
    "pouco tempo; reduzir o álcool; suplemento se o médico achar. Ver também a B12."),
   ("The leafy-greens vitamin; makes red cells and lowers homocysteine.",
    "Vitamin B9: needed to divide cells (red cells, gut) and to lower homocysteine.",
    "Supplements, fortified cereals, lots of greens.",
    "Few vegetables, alcohol, some drugs, poor absorption.",
    "Dark leafy greens and crucifers (broccoli, spinach, kale, asparagus), legumes, avocado, "
    "citrus, liver.", "Alcohol, vegetable-poor diet, overcooking greens.",
    "Low: broccoli, spinach, legumes and citrus daily, lightly cooked; cut alcohol; supplement "
    "if the doctor agrees. Check B12 too."))

_m("vitd", "iron", ("Vitamina D", "Vitamin D"),
   ("vitamina d", "25 hidroxivitamina d", "25-oh vitamina d", "25(oh)d", "calcidiol",
    "vitamin d", "25-hydroxyvitamin d"),
   ("A vitamina do sol: ossos, músculo e imunidade.",
    "Formada na pele com o sol. Ossos (absorção de cálcio), força muscular, imunidade. Muito "
    "comum estar baixa no inverno e em quem treina dentro de casa.",
    "Suplementos, exposição solar regular.",
    "Pouco sol (inverno, treino indoor, protetor sempre), pele escura, excesso de peso, idade.",
    "15–30 min de sol nos braços/pernas nos meses de sol, peixe gordo (sardinha, cavala, "
    "salmão), gema de ovo.",
    "Viver e treinar sempre dentro de casa.",
    "Baixa: mais sol e peixe gordo; no inverno é comum suplementar (dose com o médico). "
    "Repetir 3 meses depois. Muito alta: só acontece com suplementos — reduzir."),
   ("The sunshine vitamin: bones, muscle and immunity.",
    "Made in the skin with sun. Bones, muscle strength, immunity. Often low in winter and in "
    "indoor athletes.",
    "Supplements, regular sun.",
    "Little sun (winter, indoor training), dark skin, excess weight, age.",
    "15–30 min of sun on arms/legs in sunny months, oily fish, egg yolk.",
    "Always living and training indoors.",
    "Low: more sun and oily fish; winter supplements are common (dose with the doctor). "
    "Recheck after 3 months. Very high: only from supplements — reduce."))

# ======================================================================= glicose

_m("glucose", "glucose", ("Glicose em jejum", "Fasting glucose"),
   ("glicose", "glicemia", "glucose", "glicose em jejum", "glicemia em jejum",
    "fasting glucose"),
   ("O açúcar no sangue em jejum.",
    "Açúcar no sangue depois de 8–12 h sem comer. Mostra como o corpo controla o açúcar.",
    "Comer antes da colheita, stress, sono curto, corticoides, resistência à insulina, "
    "sedentarismo, excesso de peso abdominal.",
    "Jejum prolongado, treino longo na véspera sem repor, alguns medicamentos.",
    "Atividade física regular (incluindo força), fibra, leguminosas, legumes, dormir bem.",
    "Açúcares e farinhas refinadas, bebidas açucaradas, álcool, sono curto, sedentarismo.",
    "Alta: mais fibra e legumes, menos açúcar e farinhas, caminhar depois das refeições, "
    "treino de força, dormir bem; ver a HbA1c. Baixa com sintomas: médico."),
   ("Blood sugar while fasting.",
    "Blood sugar after 8–12 h without food. Shows sugar control.",
    "Eating before the test, stress, short sleep, steroids, insulin resistance, inactivity, "
    "belly fat.", "Long fasting, long training the day before, some drugs.",
    "Regular exercise (including strength), fibre, legumes, vegetables, good sleep.",
    "Refined sugar and flour, sugary drinks, alcohol, short sleep, inactivity.",
    "High: more fibre and vegetables, less sugar, walk after meals, strength training, sleep; "
    "check HbA1c. Low with symptoms: doctor."))

_m("hba1c", "glucose", ("Hemoglobina glicada (HbA1c)", "HbA1c"),
   ("hemoglobina glicada", "hba1c", "a1c", "glycated hemoglobin", "hemoglobina a1c"),
   ("A média do açúcar no sangue dos últimos 2–3 meses.",
    "Percentagem de hemoglobina com açúcar agarrado. Reflete os últimos ~3 meses; não depende "
    "do jejum.",
    "Açúcar alto de forma continuada, resistência à insulina; falta de ferro pode subir "
    "falsamente.",
    "Perdas de sangue ou glóbulos vermelhos novos (falsamente baixa).",
    "Movimento diário, força, fibra, sono, peso estável.",
    "Dieta rica em açúcares e refinados, sedentarismo, sono curto.",
    "Alta: as mesmas estratégias da glicose; repetir 3 meses depois."),
   ("Average blood sugar over the last 2–3 months.",
    "Share of haemoglobin with sugar attached. Reflects ~3 months; fasting not needed.",
    "Persistently high sugar, insulin resistance; low iron can falsely raise it.",
    "Blood loss or new red cells (falsely low).",
    "Daily movement, strength, fibre, sleep, stable weight.",
    "High-sugar diet, inactivity, short sleep.",
    "High: same strategies as glucose; recheck after 3 months."))

_m("insulin", "glucose", ("Insulina", "Insulin"),
   ("insulina", "insulin", "insulina em jejum"),
   ("A hormona que mete o açúcar nas células; alta em jejum = resistência à insulina.",
    "Hormona do pâncreas que baixa o açúcar no sangue. Em jejum alta mostra que o corpo "
    "precisa de mais insulina para o mesmo efeito.",
    "Resistência à insulina, gordura abdominal, sedentarismo, comer antes da colheita.",
    "Treino regular, jejum, diabetes tipo 1.",
    "Atividade física, força, sono, perder gordura abdominal.",
    "Sedentarismo, açúcares, sono curto, stress.",
    "Alta: treino de força e aeróbio, menos açúcar e refinados, dormir bem; ver o HOMA-IR."),
   ("The hormone that moves sugar into cells; high fasting = insulin resistance.",
    "Pancreatic hormone that lowers blood sugar. High when fasting means more insulin is needed.",
    "Insulin resistance, belly fat, inactivity, eating before the test.",
    "Regular training, fasting, type 1 diabetes.",
    "Exercise, strength, sleep, losing belly fat.", "Inactivity, sugar, short sleep, stress.",
    "High: strength and aerobic training, less sugar, sleep; check HOMA-IR."))

_m("homa", "glucose", ("HOMA-IR", "HOMA-IR"),
   ("homa-ir", "homa ir", "homa", "indice de resistencia a insulina"),
   ("Índice de resistência à insulina (glicose × insulina em jejum).",
    "Calculado a partir da glicose e da insulina em jejum. Acima de ~2–2,5 sugere resistência "
    "à insulina.",
    "Gordura abdominal, sedentarismo, sono curto, açúcares.",
    "Treino regular, peso saudável.",
    "Treino (aeróbio + força), sono, dieta com fibra.", "Sedentarismo, refinados.",
    "Alto: mais movimento diário, força 2–3×/semana, menos açúcar e refinados."),
   ("Insulin resistance index (fasting glucose × insulin).",
    "Calculated from fasting glucose and insulin. Above ~2–2.5 suggests insulin resistance.",
    "Belly fat, inactivity, short sleep, sugars.", "Regular training, healthy weight.",
    "Training (aerobic + strength), sleep, fibre.", "Inactivity, refined foods.",
    "High: more daily movement, strength 2–3×/week, less sugar."))

# ======================================================================== lípidos

_m("chol", "lipids", ("Colesterol total", "Total cholesterol"),
   ("colesterol total", "colesterol", "total cholesterol", "cholesterol"),
   ("A soma do colesterol «bom» (HDL) e do «mau» (LDL e outros).",
    "Gordura que o corpo usa para membranas e hormonas. Sozinho diz pouco: interessa o LDL, o "
    "HDL e os triglicerídeos.",
    "Genética, gorduras saturadas e trans, excesso de peso, tiroide lenta, sedentarismo.",
    "Treino, fibra solúvel, peso saudável, estatinas.",
    "Azeite, frutos secos, peixe gordo, aveia, leguminosas, fruta e legumes, exercício.",
    "Gorduras saturadas (enchidos, manteiga, natas), trans (bolos, fritos industriais), tabaco.",
    "Alto: ver o LDL e o HDL; trocar gorduras saturadas por azeite e frutos secos, mais fibra "
    "(aveia, leguminosas), exercício."),
   ("The sum of «good» (HDL) and «bad» (LDL and others) cholesterol.",
    "Fat used for membranes and hormones. Alone it says little: LDL, HDL and triglycerides "
    "matter.",
    "Genetics, saturated and trans fats, excess weight, slow thyroid, inactivity.",
    "Training, soluble fibre, healthy weight, statins.",
    "Olive oil, nuts, oily fish, oats, legumes, fruit and vegetables, exercise.",
    "Saturated fats (processed meat, butter, cream), trans fats, smoking.",
    "High: check LDL and HDL; swap saturated fats for olive oil and nuts, more fibre, exercise."))

_m("hdl", "lipids", ("Colesterol HDL («bom»)", "HDL cholesterol («good»)"),
   ("colesterol hdl", "hdl", "hdl colesterol", "hdl-c", "hdl cholesterol"),
   ("O colesterol «bom», que retira gordura das artérias; alto é melhor.",
    "Transporta o colesterol das artérias de volta ao fígado. Valores altos protegem.",
    "Exercício aeróbio regular, azeite, perder peso, deixar de fumar, algum álcool (não se "
    "recomenda por isso).",
    "Sedentarismo, tabaco, excesso de peso, açúcares, triglicerídeos altos, testosterona/"
    "anabolizantes.",
    "Treino aeróbio, azeite e frutos secos, peixe gordo, peso saudável.",
    "Tabaco, sedentarismo, açúcares e refinados.",
    "Baixo: mais treino aeróbio, gorduras boas (azeite, frutos secos, peixe), menos açúcar, "
    "deixar de fumar."),
   ("The «good» cholesterol that removes fat from arteries; higher is better.",
    "Carries cholesterol from arteries back to the liver. High values protect.",
    "Regular aerobic exercise, olive oil, weight loss, quitting smoking.",
    "Inactivity, smoking, excess weight, sugar, high triglycerides, anabolic steroids.",
    "Aerobic training, olive oil and nuts, oily fish, healthy weight.",
    "Smoking, inactivity, sugar and refined foods.",
    "Low: more aerobic training, good fats, less sugar, quit smoking."))

_m("ldl", "lipids", ("Colesterol LDL («mau»)", "LDL cholesterol («bad»)"),
   ("colesterol ldl", "ldl", "ldl colesterol", "ldl-c", "ldl cholesterol"),
   ("O colesterol «mau», que se deposita nas artérias; mais baixo é melhor.",
    "Leva o colesterol do fígado aos tecidos; em excesso deposita-se nas artérias. É o "
    "principal alvo para o risco cardiovascular.",
    "Gorduras saturadas e trans, genética (hipercolesterolemia familiar), excesso de peso, "
    "tiroide lenta.",
    "Fibra solúvel (aveia, leguminosas), fitoesteróis, exercício, estatinas.",
    "Aveia, cevada, leguminosas, frutos secos, azeite, soja, fruta e legumes.",
    "Enchidos, carnes processadas, manteiga, natas, fritos e bolos industriais.",
    "Alto: menos gordura saturada (carne processada, manteiga, queijos gordos), mais fibra "
    "solúvel (aveia diária, leguminosas), frutos secos e azeite; se muito alto ou com "
    "familiares com enfarte cedo, médico (genética)."),
   ("The «bad» cholesterol that builds up in arteries; lower is better.",
    "Carries cholesterol to tissues; in excess it deposits in arteries. Main cardiovascular "
    "target.",
    "Saturated and trans fats, genetics, excess weight, slow thyroid.",
    "Soluble fibre (oats, legumes), plant sterols, exercise, statins.",
    "Oats, barley, legumes, nuts, olive oil, soy, fruit and vegetables.",
    "Processed meat, butter, cream, industrial fried food and pastries.",
    "High: less saturated fat, daily oats and legumes, nuts and olive oil; very high or early "
    "family heart disease: doctor."))

_m("tg", "lipids", ("Triglicerídeos", "Triglycerides"),
   ("trigliceridos", "triglicerideos", "triglicerides", "triglycerides", "tg"),
   ("A gordura do sangue que vem do açúcar e do álcool a mais.",
    "Gordura em circulação; sobe com o excesso de açúcares, refinados e álcool.",
    "Açúcares e farinhas refinadas, álcool, comer antes da colheita, excesso de peso, "
    "sedentarismo, diabetes.",
    "Exercício (sobretudo aeróbio), ómega-3, perder peso, menos açúcar e álcool.",
    "Treino regular, peixe gordo, legumes, frutos secos.",
    "Bebidas açucaradas, doces, pão branco em excesso, álcool.",
    "Altos: cortar açúcar e álcool, mais peixe gordo e treino aeróbio; fazer a colheita em "
    "jejum de 12 h."),
   ("Blood fat that comes from excess sugar and alcohol.",
    "Circulating fat; rises with excess sugars, refined carbs and alcohol.",
    "Refined sugar and flour, alcohol, eating before the test, excess weight, inactivity.",
    "Exercise, omega-3, weight loss, less sugar and alcohol.",
    "Regular training, oily fish, vegetables, nuts.", "Sugary drinks, sweets, alcohol.",
    "High: cut sugar and alcohol, more oily fish and aerobic training; test after 12 h "
    "fasting."))

_m("lpa", "lipids", ("Lipoproteína (a)", "Lipoprotein (a)"),
   ("lipoproteina a", "lipoproteina (a)", "lp(a)", "lpa", "lipoprotein a"),
   ("Uma partícula de colesterol de risco, quase toda genética.",
    "Parecida com o LDL e ligada ao risco cardiovascular. É definida pelos genes: basta medir "
    "uma vez na vida.",
    "Genética (sobretudo), doença renal.",
    "Pouco muda com o estilo de vida.",
    "Controlar todos os outros fatores (LDL, tensão, tabaco).", "Tabaco, LDL alto.",
    "Alta: não há dieta que a baixe — controlar bem o LDL, a tensão e o tabaco, e falar com o "
    "médico."),
   ("A risky cholesterol particle, almost entirely genetic.",
    "Similar to LDL and linked to cardiovascular risk. Set by genes: measure once in life.",
    "Genetics, kidney disease.", "Little changes with lifestyle.",
    "Control every other factor (LDL, blood pressure, smoking).", "Smoking, high LDL.",
    "High: no diet lowers it — control LDL, blood pressure and smoking, see the doctor."))

_m("apob", "lipids", ("Apolipoproteína B", "Apolipoprotein B"),
   ("apolipoproteina b", "apo b", "apob", "apolipoprotein b"),
   ("O número de partículas de colesterol «mau» no sangue.",
    "Cada partícula aterogénica (LDL, VLDL) tem uma ApoB: contá-las mede o risco melhor do que o "
    "LDL em algumas pessoas.",
    "As mesmas do LDL: gorduras saturadas, genética, excesso de peso, resistência à insulina.",
    "Fibra, exercício, perder peso, estatinas.",
    "Como no LDL.", "Como no LDL.", "Alta: as mesmas estratégias do LDL."),
   ("The number of «bad» cholesterol particles.",
    "Each atherogenic particle carries one ApoB: counting them measures risk better than LDL "
    "in some people.",
    "As LDL: saturated fats, genetics, excess weight, insulin resistance.",
    "Fibre, exercise, weight loss, statins.", "As LDL.", "As LDL.",
    "High: same strategies as LDL."))

# ============================================================================ rim

_m("creat", "kidney", ("Creatinina", "Creatinine"),
   ("creatinina", "creatinine", "creat"),
   ("Resíduo do músculo eliminado pelo rim; mostra como o rim filtra.",
    "Produto do metabolismo muscular, eliminado pelos rins. Sobe quando o rim filtra menos — mas "
    "também em quem tem muito músculo.",
    "Muita massa muscular, treino intenso nas 24–48 h antes, muita carne, suplementos de "
    "creatina, desidratação, doença renal, alguns medicamentos (anti-inflamatórios).",
    "Pouca massa muscular, gravidez.",
    "Boa hidratação, tensão controlada, moderação nos anti-inflamatórios.",
    "Desidratação, anti-inflamatórios frequentes (ibuprofeno), tensão e açúcar altos.",
    "Ligeiramente alta num atleta musculado ou a tomar creatina é comum: repetir hidratado, "
    "sem treino duro na véspera e sem creatina 1 semana; ver a TFG/cistatina C com o médico."),
   ("Muscle waste removed by the kidney; shows kidney filtering.",
    "By-product of muscle metabolism, cleared by the kidneys. Rises when filtering drops — and "
    "in very muscular people.",
    "Lots of muscle, hard training in the 24–48 h before, lots of meat, creatine supplements, "
    "dehydration, kidney disease, NSAIDs.", "Low muscle mass, pregnancy.",
    "Good hydration, controlled blood pressure, sparing NSAIDs.",
    "Dehydration, frequent NSAIDs, high blood pressure and sugar.",
    "Mildly high in a muscular athlete or on creatine is common: recheck hydrated, no hard "
    "training the day before and no creatine for a week; ask about eGFR/cystatin C."))

_m("urea", "kidney", ("Ureia", "Urea"),
   ("ureia", "urea", "bun", "azoto ureico"),
   ("Resíduo da proteína que o rim elimina.",
    "Produto da degradação das proteínas. Depende da proteína que comes, da hidratação e do "
    "rim.",
    "Muita proteína, desidratação, treino muito intenso, doença renal, sangramento intestinal.",
    "Pouca proteína, muita água, doença do fígado.",
    "Hidratação, proteína adequada.", "Desidratação.",
    "Alta: beber mais água, ver se a proteína é exagerada; ler com a creatinina."),
   ("Protein waste removed by the kidney.",
    "Breakdown product of protein. Depends on protein intake, hydration and kidney.",
    "Lots of protein, dehydration, very hard training, kidney disease, gut bleeding.",
    "Low protein, lots of water, liver disease.", "Hydration, adequate protein.",
    "Dehydration.", "High: drink more, check protein isn't excessive; read with creatinine."))

_m("egfr", "kidney", ("Taxa de filtração glomerular (TFG)", "eGFR"),
   ("taxa de filtracao glomerular", "tfg", "tfge", "egfr", "ckd-epi", "filtracao glomerular"),
   ("Quanto sangue os rins filtram por minuto (calculado da creatinina).",
    "Estimativa da função renal a partir da creatinina, idade e sexo. Pode subestimar a função "
    "em quem tem muito músculo.",
    "Boa função renal, pouca massa muscular.",
    "Doença renal, desidratação, muita massa muscular/creatina (falso baixo).",
    "Hidratação, tensão e açúcar controlados.", "Anti-inflamatórios frequentes, tabaco.",
    "Baixa: repetir em boas condições; num atleta musculado pedir a cistatina C ao médico."),
   ("How much blood the kidneys filter per minute (from creatinine).",
    "Kidney function estimate from creatinine, age and sex. May underestimate in muscular "
    "people.", "Good kidney function, low muscle mass.",
    "Kidney disease, dehydration, lots of muscle/creatine (falsely low).",
    "Hydration, controlled blood pressure and sugar.", "Frequent NSAIDs, smoking.",
    "Low: recheck in good conditions; muscular athletes can ask for cystatin C."))

_m("uric", "kidney", ("Ácido úrico", "Uric acid"),
   ("acido urico", "urato", "uric acid", "urate"),
   ("Resíduo das purinas; em excesso dá gota.",
    "Produto das purinas (carnes, marisco, cerveja). Em excesso forma cristais (gota) e pedras.",
    "Carne vermelha e vísceras, marisco, cerveja e bebidas com frutose, desidratação, jejum, "
    "excesso de peso, alguns diuréticos.",
    "Muita água, café, vitamina C, cerejas, lacticínios magros.",
    "Água, lacticínios magros, café, cerejas, legumes.",
    "Cerveja, refrigerantes, vísceras, marisco e carne vermelha em excesso.",
    "Alto: beber mais água, cortar cerveja e refrigerantes, menos carne vermelha e marisco, "
    "perder peso devagar."),
   ("Purine waste; too much causes gout.",
    "Product of purines (meat, shellfish, beer). In excess it crystallises (gout) and forms "
    "stones.",
    "Red meat and offal, shellfish, beer and fructose drinks, dehydration, fasting, excess "
    "weight, some diuretics.", "Lots of water, coffee, vitamin C, cherries, low-fat dairy.",
    "Water, low-fat dairy, coffee, cherries, vegetables.",
    "Beer, soft drinks, offal, too much shellfish and red meat.",
    "High: drink more water, cut beer and soft drinks, less red meat and shellfish."))

# ======================================================================== fígado

_m("ast", "liver", ("AST (TGO)", "AST (SGOT)"),
   ("ast", "tgo", "aspartato aminotransferase", "aspartato transaminase", "sgot"),
   ("Enzima do fígado e do músculo; sobe depois de treinos duros.",
    "Existe no fígado e nos músculos. Num atleta sobe muitas vezes só pelo treino.",
    "Treino intenso nas 48–72 h antes (músculo), álcool, fígado gordo, hepatite, alguns "
    "medicamentos e suplementos.",
    "Sem significado.",
    "Pouco álcool, peso saudável, colheita longe de treinos duros.",
    "Álcool, fígado gordo, suplementos sem controlo.",
    "Alta: repetir depois de 3 dias sem treino duro; se a ALT e a GGT também subirem, é o "
    "fígado — menos álcool e açúcar; se só a AST e a CK, é o músculo."),
   ("Liver and muscle enzyme; rises after hard training.",
    "Found in liver and muscle. In athletes it often rises from training alone.",
    "Hard training in the 48–72 h before, alcohol, fatty liver, hepatitis, some drugs and "
    "supplements.", "No meaning.",
    "Little alcohol, healthy weight, test away from hard training.",
    "Alcohol, fatty liver, unchecked supplements.",
    "High: recheck after 3 days without hard training; if ALT and GGT also rise it's the "
    "liver, if only AST and CK it's muscle."))

_m("alt", "liver", ("ALT (TGP)", "ALT (SGPT)"),
   ("alt", "tgp", "alanina aminotransferase", "alanina transaminase", "sgpt"),
   ("A enzima mais específica do fígado.",
    "Sobe sobretudo quando as células do fígado sofrem (fígado gordo, álcool, vírus, "
    "medicamentos); o treino sobe-a menos que a AST.",
    "Fígado gordo (excesso de peso, açúcares), álcool, hepatites, medicamentos e suplementos, "
    "treino muito intenso.",
    "Sem significado.",
    "Peso saudável, pouco açúcar e álcool, café (protege o fígado), exercício.",
    "Álcool, refrigerantes e açúcares, excesso de peso, suplementos «milagrosos».",
    "Alta: menos álcool e açúcar, perder gordura abdominal, rever suplementos; repetir; médico "
    "se persistir."),
   ("The most liver-specific enzyme.",
    "Rises mainly when liver cells suffer (fatty liver, alcohol, viruses, drugs).",
    "Fatty liver, alcohol, hepatitis, drugs and supplements, very hard training.",
    "No meaning.", "Healthy weight, little sugar and alcohol, coffee, exercise.",
    "Alcohol, soft drinks and sugar, excess weight, «miracle» supplements.",
    "High: less alcohol and sugar, lose belly fat, review supplements; recheck."))

_m("ggt", "liver", ("GGT (gama-GT)", "GGT"),
   ("ggt", "gama gt", "gama-gt", "gama glutamil transferase", "gamma gt",
    "gamma-glutamyl transferase"),
   ("Enzima do fígado muito sensível ao álcool.",
    "Sobe com o álcool, o fígado gordo e problemas da vesícula/vias biliares.",
    "Álcool (mesmo moderado e frequente), fígado gordo, alguns medicamentos, tabaco.",
    "Sem significado.", "Pouco ou nenhum álcool, peso saudável.", "Álcool, tabaco.",
    "Alta: cortar o álcool 4–6 semanas e repetir — costuma descer."),
   ("Liver enzyme very sensitive to alcohol.",
    "Rises with alcohol, fatty liver and bile duct problems.",
    "Alcohol (even moderate and frequent), fatty liver, some drugs, smoking.",
    "No meaning.", "Little or no alcohol, healthy weight.", "Alcohol, smoking.",
    "High: stop alcohol for 4–6 weeks and recheck — it usually drops."))

_m("alp", "liver", ("Fosfatase alcalina", "Alkaline phosphatase"),
   ("fosfatase alcalina", "fa", "alp", "alkaline phosphatase"),
   ("Enzima do fígado e do osso.",
    "Vem do fígado (vias biliares) e dos ossos em crescimento ou remodelação.",
    "Problemas das vias biliares, crescimento, fraturas a consolidar, falta de vitamina D.",
    "Falta de zinco ou magnésio, má nutrição.",
    "Vitamina D e zinco suficientes.", "Álcool.",
    "Alta: ver vitamina D e o resto das enzimas do fígado; médico se persistir."),
   ("Liver and bone enzyme.",
    "Comes from the bile ducts and from growing or remodelling bone.",
    "Bile duct problems, growth, healing fractures, low vitamin D.",
    "Low zinc or magnesium, malnutrition.", "Enough vitamin D and zinc.", "Alcohol.",
    "High: check vitamin D and the other liver enzymes."))

_m("bili", "liver", ("Bilirrubina", "Bilirubin"),
   ("bilirrubina", "bilirrubina total", "bilirubin", "total bilirubin"),
   ("Pigmento amarelo da destruição dos glóbulos vermelhos.",
    "Formada quando os glóbulos vermelhos velhos se desfazem; o fígado elimina-a. Ligeiramente "
    "alta em jejum é muitas vezes a síndrome de Gilbert (benigna).",
    "Jejum, síndrome de Gilbert, destruição de glóbulos vermelhos (corrida longa, hemólise), "
    "fígado, vias biliares.",
    "Sem significado.", "Comer regularmente.", "Jejum prolongado, álcool.",
    "Ligeiramente alta isolada com o resto normal: costuma ser Gilbert; repetir sem jejum "
    "longo. Alta com enzimas alteradas: médico."),
   ("Yellow pigment from broken-down red cells.",
    "Made when old red cells break down; the liver clears it. Mildly high when fasting is often "
    "Gilbert's syndrome (benign).",
    "Fasting, Gilbert's, red-cell breakdown (long runs), liver, bile ducts.",
    "No meaning.", "Regular meals.", "Long fasting, alcohol.",
    "Mildly high alone: often Gilbert's; recheck. High with abnormal enzymes: doctor."))

_m("albumin", "liver", ("Albumina", "Albumin"),
   ("albumina", "albumin"),
   ("A principal proteína do sangue, feita no fígado.",
    "Segura água dentro dos vasos e transporta hormonas, vitaminas e medicamentos. Mostra o "
    "estado nutricional e do fígado.",
    "Desidratação.",
    "Pouca proteína ou energia, inflamação, doença do fígado ou do rim.",
    "Proteína e energia suficientes.", "Dietas muito restritivas.",
    "Baixa: rever proteína e calorias (sobretudo em fases de muito treino)."),
   ("The main blood protein, made in the liver.",
    "Holds water in vessels and carries hormones, vitamins and drugs. Shows nutrition and "
    "liver state.", "Dehydration.",
    "Low protein or energy intake, inflammation, liver or kidney disease.",
    "Enough protein and energy.", "Very restrictive diets.",
    "Low: review protein and calories (especially in heavy training)."))

_m("protein", "liver", ("Proteínas totais", "Total protein"),
   ("proteinas totais", "proteinas", "total protein"),
   ("Todas as proteínas do sangue (albumina + globulinas).",
    "Soma da albumina com as globulinas (anticorpos e outras).",
    "Desidratação, inflamação crónica.", "Má nutrição, doença do fígado ou do rim.",
    "Alimentação completa.", "Dietas muito restritivas.",
    "Ler com a albumina; alta isolada costuma ser desidratação."),
   ("All blood proteins (albumin + globulins).", "Albumin plus globulins (antibodies etc.).",
    "Dehydration, chronic inflammation.", "Malnutrition, liver or kidney disease.",
    "Complete diet.", "Very restrictive diets.",
    "Read with albumin; isolated high is often dehydration."))

# ==================================================================== inflamação

_m("crp", "inflammation", ("Proteína C reativa (PCR)", "C-reactive protein (CRP)"),
   ("proteina c reativa", "pcr", "crp", "pcr-us", "hs-crp", "proteina c reactiva",
    "c-reactive protein"),
   ("O alarme de inflamação do corpo.",
    "Proteína feita pelo fígado quando há inflamação ou infeção. A PCR ultrassensível mostra "
    "inflamação de baixo grau (risco cardiovascular).",
    "Infeção, lesão, treino muito duro ou prova longa nos dias antes, excesso de peso, tabaco, "
    "sono curto, doenças inflamatórias.",
    "Exercício regular moderado, perder gordura, dieta mediterrânica, ómega-3.",
    "Dieta mediterrânica (azeite, peixe, legumes, fruta, frutos secos), sono, treino bem "
    "doseado.",
    "Ultraprocessados, açúcar, tabaco, gordura abdominal, sobretreino.",
    "Alta: repetir longe de provas/treinos duros e de infeções; se continuar, reduzir "
    "ultraprocessados, perder gordura, dormir mais e falar com o médico."),
   ("The body's inflammation alarm.",
    "Liver protein made during inflammation or infection. High-sensitivity CRP shows low-grade "
    "inflammation (heart risk).",
    "Infection, injury, very hard training or long race in the days before, excess weight, "
    "smoking, short sleep, inflammatory disease.",
    "Regular moderate exercise, fat loss, Mediterranean diet, omega-3.",
    "Mediterranean diet, sleep, well-dosed training.",
    "Ultra-processed food, sugar, smoking, belly fat, overtraining.",
    "High: recheck away from races/hard training and infections; if it stays high, cut "
    "processed food, lose fat, sleep more, see the doctor."))

_m("esr", "inflammation", ("Velocidade de sedimentação (VS)", "ESR"),
   ("velocidade de sedimentacao", "vs", "vhs", "esr", "erythrocyte sedimentation rate"),
   ("Um marcador lento de inflamação.",
    "Quão depressa os glóbulos vermelhos assentam num tubo. Sobe com inflamação, mas devagar e "
    "com pouca especificidade.",
    "Inflamação, infeção, anemia, idade, gravidez.", "Sem significado habitual.",
    "Como na PCR.", "Como na PCR.", "Alta: ler com a PCR; repetir se isolada."),
   ("A slow inflammation marker.",
    "How fast red cells settle in a tube. Rises with inflammation, slowly and unspecifically.",
    "Inflammation, infection, anaemia, age, pregnancy.", "Usually no meaning.",
    "As CRP.", "As CRP.", "High: read with CRP; recheck if isolated."))

_m("homocys", "inflammation", ("Homocisteína", "Homocysteine"),
   ("homocisteina", "homocysteine", "hcy"),
   ("Aminoácido que sobe quando faltam B12, folato ou B6; alto agride os vasos.",
    "Produto do metabolismo das proteínas. Alta está associada a risco cardiovascular e "
    "costuma refletir falta de vitaminas B.",
    "Falta de ácido fólico, B12 ou B6, tabaco, café em excesso, álcool, genética (MTHFR), "
    "rim.",
    "Folato, B12 e B6 suficientes.",
    "Folhas verdes, brócolos, leguminosas (folato), peixe, ovos (B12), banana e grão (B6).",
    "Tabaco, álcool, dieta pobre em vegetais.",
    "Alta: mais vegetais verdes e leguminosas, ver B12 e folato; suplementar com o médico se "
    "faltarem."),
   ("Amino acid that rises when B12, folate or B6 are low; high harms vessels.",
    "Protein metabolism by-product. High is linked to heart risk and usually reflects low B "
    "vitamins.",
    "Low folate, B12 or B6, smoking, too much coffee, alcohol, genetics (MTHFR), kidney.",
    "Enough folate, B12 and B6.",
    "Greens, broccoli, legumes (folate), fish, eggs (B12), banana and chickpeas (B6).",
    "Smoking, alcohol, vegetable-poor diet.",
    "High: more greens and legumes, check B12 and folate; supplement with the doctor."))

# ======================================================================== tiroide

_m("tsh", "thyroid", ("TSH", "TSH"),
   ("tsh", "tirotrofina", "hormona estimulante da tiroide", "thyroid stimulating hormone"),
   ("A ordem do cérebro à tiroide; alta = tiroide lenta, baixa = tiroide acelerada.",
    "Hormona da hipófise que manda a tiroide trabalhar. Funciona ao contrário: tiroide lenta → "
    "TSH alta.",
    "Tiroide lenta (hipotiroidismo, Hashimoto), falta de iodo, défice energético grande, "
    "recuperação de doença.",
    "Tiroide acelerada, excesso de hormona tiroideia (medicação), corticoides.",
    "Iodo suficiente (peixe, sal iodado, lacticínios), selénio (castanha-do-pará), energia "
    "suficiente.",
    "Comer muito menos do que gastas (défice energético relativo), excesso de iodo em "
    "suplementos.",
    "Fora do intervalo: ler com a T4 livre e falar com o médico. Num atleta, garantir que come "
    "o suficiente para o treino."),
   ("The brain's order to the thyroid; high = slow thyroid, low = overactive.",
    "Pituitary hormone driving the thyroid. Works in reverse: slow thyroid → high TSH.",
    "Slow thyroid, low iodine, large energy deficit, recovery from illness.",
    "Overactive thyroid, thyroid medication excess, steroids.",
    "Enough iodine (fish, iodised salt, dairy), selenium (Brazil nuts), enough energy.",
    "Eating far less than you burn, excess iodine supplements.",
    "Out of range: read with free T4 and see the doctor. Athletes: make sure you eat enough."))

_m("ft4", "thyroid", ("T4 livre", "Free T4"),
   ("t4 livre", "ft4", "tiroxina livre", "free t4", "free thyroxine"),
   ("A hormona da tiroide disponível no sangue.",
    "Principal hormona produzida pela tiroide (convertida em T3 nos tecidos).",
    "Tiroide acelerada, medicação em excesso.",
    "Tiroide lenta, défice energético grande.",
    "Iodo e selénio suficientes.", "Défice energético grande.",
    "Ler com a TSH; fora do intervalo: médico."),
   ("The thyroid hormone available in the blood.",
    "Main thyroid hormone (converted to T3 in tissues).",
    "Overactive thyroid, too much medication.", "Slow thyroid, large energy deficit.",
    "Enough iodine and selenium.", "Large energy deficit.",
    "Read with TSH; out of range: doctor."))

_m("ft3", "thyroid", ("T3 livre", "Free T3"),
   ("t3 livre", "ft3", "triiodotironina livre", "free t3"),
   ("A forma ativa da hormona da tiroide.",
    "Controla o metabolismo. Desce quando se come pouco para o treino (o corpo poupa energia).",
    "Tiroide acelerada.", "Défice energético, sobretreino, doença, tiroide lenta.",
    "Energia e hidratos de carbono suficientes para o treino.",
    "Dietas muito restritivas, sobretreino.",
    "Baixa com TSH normal num atleta: comer mais (sobretudo hidratos) e descansar."),
   ("The active thyroid hormone.",
    "Controls metabolism. Falls when you eat too little for your training.",
    "Overactive thyroid.", "Energy deficit, overtraining, illness, slow thyroid.",
    "Enough energy and carbs for training.", "Very restrictive diets, overtraining.",
    "Low with normal TSH in an athlete: eat more (especially carbs) and rest."))

# ======================================================================== hormonas

_m("testo", "hormones", ("Testosterona total", "Total testosterone"),
   ("testosterona total", "testosterona", "total testosterone", "testosterone"),
   ("A principal hormona masculina: músculo, recuperação, energia e libido.",
    "Hormona anabólica (também nas mulheres, em menor quantidade). Ajuda a construir músculo e "
    "a recuperar. É mais alta de manhã.",
    "Sono suficiente, treino de força, peso saudável, energia e gordura alimentar adequadas, "
    "zinco e vitamina D suficientes; colheita de manhã cedo.",
    "Sono curto, sobretreino e treino de resistência muito volumoso, défice calórico, excesso "
    "de gordura corporal, álcool, stress crónico, alguns medicamentos (opiáceos), idade.",
    "Dormir 7–9 h, força 2–3×/semana, comer o suficiente (incluindo gorduras boas), sol/"
    "vitamina D, zinco (carne, marisco, sementes).",
    "Sono curto, álcool, excesso de volume sem recuperação, dietas muito restritivas, gordura "
    "abdominal.",
    "Fazer a colheita entre as 7 h e as 10 h, descansado. Baixa: dormir mais, aliviar o volume, "
    "garantir energia, treino de força, ver vitamina D e zinco, menos álcool; médico se "
    "persistir. Não usar testosterona por conta própria."),
   ("The main male hormone: muscle, recovery, energy and libido.",
    "Anabolic hormone (also in women, less). Builds muscle and aids recovery. Higher in the "
    "morning.",
    "Enough sleep, strength training, healthy weight, enough energy and dietary fat, zinc and "
    "vitamin D; early-morning sampling.",
    "Short sleep, overtraining and very high endurance volume, calorie deficit, excess fat, "
    "alcohol, chronic stress, some drugs, age.",
    "7–9 h sleep, strength 2–3×/week, eat enough (good fats too), sun/vitamin D, zinc.",
    "Short sleep, alcohol, volume without recovery, very restrictive diets, belly fat.",
    "Test 7–10 am, rested. Low: sleep more, reduce volume, eat enough, lift, check vitamin D "
    "and zinc, less alcohol; doctor if it persists. Never self-medicate."))

_m("freetesto", "hormones", ("Testosterona livre", "Free testosterone"),
   ("testosterona livre", "free testosterone", "testosterona biodisponivel"),
   ("A testosterona que não está «presa» e atua nos tecidos.",
    "Pequena fração da testosterona que não está ligada à SHBG e à albumina — é a que atua.",
    "As mesmas da total; SHBG baixa.",
    "As mesmas da total; SHBG alta (treino de resistência muito volumoso, défice energético).",
    "Como na testosterona total.", "Como na testosterona total.",
    "Ler com a total e a SHBG; estratégias como na testosterona total."),
   ("Testosterone that isn't bound and acts in tissues.",
    "Small fraction not bound to SHBG and albumin — the active part.",
    "Same as total; low SHBG.", "Same as total; high SHBG (high endurance volume, energy "
    "deficit).", "As total testosterone.", "As total testosterone.",
    "Read with total and SHBG; same strategies as total."))

_m("shbg", "hormones", ("SHBG", "SHBG"),
   ("shbg", "globulina de ligacao as hormonas sexuais", "sex hormone binding globulin"),
   ("A proteína que «prende» a testosterona e o estradiol.",
    "Transporta as hormonas sexuais; quanto mais alta, menos testosterona livre.",
    "Treino de resistência muito volumoso, défice energético, idade, tiroide acelerada, "
    "álcool.",
    "Excesso de peso, resistência à insulina, tiroide lenta.",
    "Energia suficiente, peso saudável.", "Défice energético prolongado.",
    "Alta num atleta: comer o suficiente para o volume de treino."),
   ("The protein that binds testosterone and oestradiol.",
    "Carries sex hormones; the higher, the less free testosterone.",
    "Very high endurance volume, energy deficit, age, overactive thyroid, alcohol.",
    "Excess weight, insulin resistance, slow thyroid.",
    "Enough energy, healthy weight.", "Long energy deficit.",
    "High in an athlete: eat enough for the training volume."))

_m("estradiol", "hormones", ("Estradiol", "Oestradiol"),
   ("estradiol", "e2", "oestradiol"),
   ("A principal hormona feminina (também presente nos homens).",
    "Nas mulheres regula o ciclo; nos homens vem da conversão da testosterona e protege osso e "
    "coração.",
    "Excesso de gordura (converte testosterona), álcool, fígado, fase do ciclo.",
    "Défice energético (amenorreia da atleta), menopausa.",
    "Peso saudável, energia suficiente.", "Défice energético, excesso de gordura.",
    "Nas mulheres ler com a fase do ciclo. Baixo numa atleta com ciclos irregulares: comer "
    "mais e falar com o médico (RED-S)."),
   ("The main female hormone (also in men).",
    "In women it drives the cycle; in men it comes from testosterone and protects bone and "
    "heart.", "Excess fat, alcohol, liver, cycle phase.",
    "Energy deficit (athlete amenorrhoea), menopause.", "Healthy weight, enough energy.",
    "Energy deficit, excess fat.",
    "Women: read with the cycle phase. Low in an athlete with irregular cycles: eat more, see "
    "the doctor (RED-S)."))

_m("cortisol", "hormones", ("Cortisol", "Cortisol"),
   ("cortisol", "cortisol matinal", "cortisol serico"),
   ("A hormona do stress; alta de manhã é normal.",
    "Mobiliza energia e controla a inflamação. Tem pico de manhã e desce ao longo do dia.",
    "Stress, sono curto, treino intenso, jejum, doença, colheita com nervos, corticoides.",
    "Doença das suprarrenais (rara), corticoides tomados há muito tempo.",
    "Sono regular, gestão do stress, recuperação entre treinos.",
    "Sono curto, stress crónico, sobretreino, cafeína em excesso.",
    "Alto: ver hora da colheita e o contexto; dormir mais, aliviar a carga. Valores extremos: "
    "médico."),
   ("The stress hormone; high in the morning is normal.",
    "Mobilises energy and controls inflammation. Peaks in the morning and falls during the day.",
    "Stress, short sleep, hard training, fasting, illness, anxious sampling, steroids.",
    "Adrenal disease (rare), long-term steroids.",
    "Regular sleep, stress management, recovery between sessions.",
    "Short sleep, chronic stress, overtraining, too much caffeine.",
    "High: check sampling time and context; sleep more, reduce load. Extreme values: doctor."))

_m("lh", "hormones", ("LH", "LH"),
   ("lh", "hormona luteinizante", "luteinizing hormone"),
   ("A ordem do cérebro aos testículos/ovários para fazerem hormonas.",
    "Hormona da hipófise que estimula a produção de testosterona (homens) e a ovulação "
    "(mulheres).",
    "Falha dos testículos/ovários, menopausa, ovulação.",
    "Défice energético, stress, anabolizantes ou testosterona externa, prolactina alta.",
    "Energia e sono suficientes.", "Testosterona externa, défice energético.",
    "Ler com a testosterona/estradiol: baixa com testosterona baixa → ver energia e sono; "
    "médico."),
   ("The brain's signal to the gonads to make hormones.",
    "Pituitary hormone driving testosterone (men) and ovulation (women).",
    "Gonad failure, menopause, ovulation.",
    "Energy deficit, stress, external testosterone/anabolics, high prolactin.",
    "Enough energy and sleep.", "External testosterone, energy deficit.",
    "Read with testosterone/oestradiol; low with low testosterone → check energy and sleep."))

_m("fsh", "hormones", ("FSH", "FSH"),
   ("fsh", "hormona foliculo estimulante", "follicle stimulating hormone"),
   ("Hormona da fertilidade (esperma e óvulos).",
    "Estimula a produção de espermatozoides e o desenvolvimento dos óvulos.",
    "Menopausa, falha dos testículos/ovários.",
    "Défice energético, testosterona externa.",
    "Energia suficiente.", "Défice energético.", "Fora do intervalo: médico."),
   ("Fertility hormone (sperm and eggs).", "Drives sperm production and egg development.",
    "Menopause, gonad failure.", "Energy deficit, external testosterone.",
    "Enough energy.", "Energy deficit.", "Out of range: doctor."))

_m("prolactin", "hormones", ("Prolactina", "Prolactin"),
   ("prolactina", "prolactin", "prl"),
   ("Hormona do leite; sobe com stress e com o exercício recente.",
    "Produzida na hipófise. Alta pode baixar a testosterona e o estradiol.",
    "Stress, exercício recente, sono curto, alguns medicamentos, tumor benigno da hipófise "
    "(raro).", "Sem significado habitual.",
    "Colheita em repouso.", "Stress, sono curto.",
    "Alta: repetir em repouso, sem exercício antes; se continuar, médico."),
   ("Milk hormone; rises with stress and recent exercise.",
    "Made in the pituitary. High can lower testosterone and oestradiol.",
    "Stress, recent exercise, short sleep, some drugs, benign pituitary tumour (rare).",
    "Usually no meaning.", "Rested sampling.", "Stress, short sleep.",
    "High: recheck rested with no exercise before; if it persists, doctor."))

_m("dheas", "hormones", ("DHEA-S", "DHEA-S"),
   ("dhea-s", "dhea s", "dheas", "sulfato de dehidroepiandrosterona", "dhea"),
   ("Hormona das suprarrenais, precursora das hormonas sexuais.",
    "Desce com a idade; usada como marcador de «vitalidade» hormonal.",
    "Stress agudo, alguns tumores (raro), suplementos de DHEA.",
    "Idade, stress crónico, sobretreino, corticoides.",
    "Sono, recuperação, gestão do stress.", "Stress crónico, sobretreino.",
    "Baixa para a idade: dormir e recuperar; não suplementar sem o médico."),
   ("Adrenal hormone, precursor of sex hormones.",
    "Falls with age; used as a marker of hormonal «vitality».",
    "Acute stress, rare tumours, DHEA supplements.",
    "Age, chronic stress, overtraining, steroids.", "Sleep, recovery, stress management.",
    "Chronic stress, overtraining.", "Low for age: sleep and recover; don't self-supplement."))

_m("igf1", "hormones", ("IGF-1", "IGF-1"),
   ("igf-1", "igf1", "somatomedina c", "insulin-like growth factor"),
   ("O mensageiro da hormona de crescimento: reparação e músculo.",
    "Produzido no fígado sob ordem da hormona de crescimento; reflete-a ao longo do dia.",
    "Proteína e energia abundantes, treino de força, sono profundo.",
    "Défice energético ou proteico, idade, sono fraco, doença do fígado.",
    "Proteína e energia suficientes, sono, treino de força.",
    "Dietas muito restritivas, sono curto.",
    "Baixo: rever energia e proteína, dormir mais. Muito alto: médico."),
   ("Growth hormone's messenger: repair and muscle.",
    "Made in the liver on growth-hormone orders; reflects it across the day.",
    "Plenty of protein and energy, strength training, deep sleep.",
    "Energy or protein deficit, age, poor sleep, liver disease.",
    "Enough protein and energy, sleep, strength training.", "Very restrictive diets, short "
    "sleep.", "Low: review energy and protein, sleep more. Very high: doctor."))

# ============================================================ minerais e eletrólitos

_m("sodium", "minerals", ("Sódio", "Sodium"),
   ("sodio", "sodium", "na", "na+"),
   ("O sal do sangue; controla a água do corpo.",
    "Principal eletrólito fora das células: equilíbrio de água, nervos e músculos.",
    "Desidratação, pouca água, muito sal.",
    "Beber água a mais em provas longas sem repor sal (hiponatremia), diuréticos, vómitos/"
    "diarreia.",
    "Em treinos longos e calor, repor água e sal (bebida isotónica).",
    "Beber só água em grandes quantidades em provas longas.",
    "Baixo depois de prova longa: perigoso — beber pela sede e com sal. Alto: hidratar."),
   ("Blood salt; controls body water.",
    "Main electrolyte outside cells: water balance, nerves and muscles.",
    "Dehydration, little water, lots of salt.",
    "Overdrinking water in long events without salt, diuretics, vomiting/diarrhoea.",
    "In long sessions and heat, replace water and salt.",
    "Drinking only plain water in large amounts in long events.",
    "Low after a long event: dangerous — drink to thirst with salt. High: hydrate."))

_m("potassium", "minerals", ("Potássio", "Potassium"),
   ("potassio", "potassium", "k", "k+"),
   ("O mineral do coração e dos músculos.",
    "Eletrólito dentro das células; essencial ao ritmo do coração e à contração muscular.",
    "Amostra hemolisada (o mais comum — tubo agitado ou demorado), doença renal, alguns "
    "medicamentos, exercício intenso antes.",
    "Diuréticos, vómitos/diarreia, pouca fruta e legumes, muito suor.",
    "Fruta e legumes (banana, batata, laranja, espinafres, leguminosas).",
    "Dieta pobre em vegetais, diuréticos.",
    "Alto isolado: costuma ser da amostra — repetir. Baixo: mais fruta e legumes; médico se "
    "muito baixo."),
   ("The heart and muscle mineral.",
    "Electrolyte inside cells; essential for heart rhythm and muscle contraction.",
    "Haemolysed sample (most common), kidney disease, some drugs, hard exercise before.",
    "Diuretics, vomiting/diarrhoea, few fruits and vegetables, heavy sweating.",
    "Fruit and vegetables (banana, potato, orange, spinach, legumes).",
    "Vegetable-poor diet, diuretics.",
    "Isolated high: usually the sample — recheck. Low: more fruit and vegetables."))

_m("calcium", "minerals", ("Cálcio", "Calcium"),
   ("calcio", "calcium", "ca", "calcio total"),
   ("O mineral dos ossos, também dos músculos e nervos.",
    "99 % está nos ossos; o do sangue é mantido estável pelas hormonas (paratiroide, vitamina "
    "D).",
    "Paratiroide hiperativa, excesso de vitamina D/suplementos, desidratação.",
    "Falta de vitamina D, magnésio baixo, albumina baixa (falso baixo).",
    "Lacticínios, sardinha com espinhas, couves, amêndoas, vitamina D.",
    "Excesso de sal e de refrigerantes de cola, pouca vitamina D.",
    "Fora do intervalo: ler com a albumina e a vitamina D; médico se persistir."),
   ("The bone mineral, also for muscles and nerves.",
    "99 % is in bone; blood calcium is kept stable by hormones (parathyroid, vitamin D).",
    "Overactive parathyroid, excess vitamin D/supplements, dehydration.",
    "Low vitamin D, low magnesium, low albumin (falsely low).",
    "Dairy, sardines with bones, kale, almonds, vitamin D.",
    "Excess salt and cola drinks, little vitamin D.",
    "Out of range: read with albumin and vitamin D; doctor if it persists."))

_m("magnesium", "minerals", ("Magnésio", "Magnesium"),
   ("magnesio", "magnesium", "mg"),
   ("Mineral de centenas de reações: energia, músculo, sono.",
    "Participa na produção de energia, na contração muscular e no sistema nervoso. O valor no "
    "sangue pode estar normal com reservas baixas.",
    "Suplementos em excesso, doença renal.",
    "Muito suor, álcool, diuréticos, antiácidos (omeprazol), dieta pobre em vegetais e "
    "integrais.",
    "Frutos secos e sementes (abóbora, amêndoa), leguminosas, cacau, folhas verdes, integrais.",
    "Álcool, ultraprocessados, antiácidos prolongados.",
    "Baixo: mais frutos secos, sementes, leguminosas e verdes; suplemento se o médico achar "
    "(cãibras, sono)."),
   ("Mineral in hundreds of reactions: energy, muscle, sleep.",
    "Involved in energy production, muscle contraction and nerves. Blood level can be normal "
    "with low stores.", "Excess supplements, kidney disease.",
    "Heavy sweating, alcohol, diuretics, antacids, diet poor in vegetables and wholegrains.",
    "Nuts and seeds, legumes, cocoa, greens, wholegrains.",
    "Alcohol, ultra-processed food, long-term antacids.",
    "Low: more nuts, seeds, legumes and greens; supplement if the doctor agrees."))

_m("phosphorus", "minerals", ("Fósforo", "Phosphorus"),
   ("fosforo", "fosfato", "phosphorus", "phosphate"),
   ("Mineral dos ossos e da energia (ATP).",
    "Com o cálcio forma o osso; também faz parte do ATP.",
    "Doença renal, excesso de vitamina D, crescimento.",
    "Má nutrição, alcoolismo, falta de vitamina D.",
    "Alimentação completa.", "Refrigerantes em excesso.", "Fora do intervalo: médico."),
   ("Bone and energy (ATP) mineral.", "Builds bone with calcium; part of ATP.",
    "Kidney disease, excess vitamin D, growth.", "Malnutrition, alcoholism, low vitamin D.",
    "Complete diet.", "Excess soft drinks.", "Out of range: doctor."))

_m("zinc", "minerals", ("Zinco", "Zinc"),
   ("zinco", "zinc", "zn"),
   ("Mineral da imunidade, da cicatrização e da testosterona.",
    "Necessário a centenas de enzimas, à imunidade, à cicatrização e às hormonas.",
    "Suplementos.",
    "Dieta vegetariana, muito suor, álcool, problemas intestinais, cereais integrais em "
    "excesso (fitatos).",
    "Carne, marisco (ostras), ovos, sementes de abóbora, leguminosas demolhadas.",
    "Álcool, dieta pobre em proteína animal sem compensação.",
    "Baixo: mais marisco, carne e sementes; demolhar as leguminosas; suplemento com o médico."),
   ("Mineral for immunity, healing and testosterone.",
    "Needed by hundreds of enzymes, immunity, healing and hormones.", "Supplements.",
    "Vegetarian diet, heavy sweating, alcohol, gut problems, phytates.",
    "Meat, shellfish (oysters), eggs, pumpkin seeds, soaked legumes.",
    "Alcohol, low-animal-protein diet without compensation.",
    "Low: more shellfish, meat and seeds; soak legumes; supplement with the doctor."))

# ============================================================== músculo e esforço

_m("ck", "muscle", ("CK (creatina quinase)", "CK (creatine kinase)"),
   ("ck", "cpk", "creatina quinase", "creatina cinase", "creatinofosfoquinase",
    "creatine kinase"),
   ("Enzima que sai do músculo quando é danificado; sobe muito depois de treinos duros.",
    "Marcador de dano muscular. Num atleta pode estar várias vezes acima do intervalo "
    "durante dias depois de força, descidas ou provas longas.",
    "Treino de força ou excêntrico, provas longas, descidas a correr, quedas, injeções, "
    "estatinas, raramente doença muscular.",
    "Pouca massa muscular, inatividade.",
    "Progressão gradual da carga, recuperação.",
    "Treinos duros seguidos sem recuperação, desidratação.",
    "Alta: repetir depois de 5–7 dias sem treino duro. Muito alta com urina escura ou dor "
    "intensa: urgência (rabdomiólise)."),
   ("Enzyme that leaks from damaged muscle; jumps after hard training.",
    "Muscle damage marker. In athletes it can sit several times above range for days after "
    "strength work, downhill running or long races.",
    "Strength or eccentric training, long races, downhill running, falls, injections, statins, "
    "rarely muscle disease.", "Low muscle mass, inactivity.",
    "Gradual load progression, recovery.", "Back-to-back hard sessions, dehydration.",
    "High: recheck after 5–7 days without hard training. Very high with dark urine or severe "
    "pain: emergency (rhabdomyolysis)."))

_m("ldh", "muscle", ("LDH (desidrogenase láctica)", "LDH"),
   ("ldh", "desidrogenase lactica", "lactato desidrogenase", "lactate dehydrogenase"),
   ("Enzima presente em quase todas as células; sobe com dano de tecidos.",
    "Pouco específica: sobe com dano muscular, destruição de glóbulos vermelhos, fígado.",
    "Treino intenso recente, hemólise (amostra ou corrida longa), fígado.",
    "Sem significado.", "Recuperação.", "Treinos duros seguidos.",
    "Alta isolada num atleta: repetir em repouso; ler com a CK e as enzimas do fígado."),
   ("Enzyme in almost every cell; rises with tissue damage.",
    "Unspecific: muscle damage, red cell breakdown, liver.",
    "Recent hard training, haemolysis, liver.", "No meaning.", "Recovery.",
    "Back-to-back hard sessions.",
    "Isolated high in an athlete: recheck rested; read with CK and liver enzymes."))

# =========================================================================== outros

_m("psa", "other", ("PSA", "PSA"),
   ("psa", "antigenio especifico da prostata", "psa total", "prostate specific antigen"),
   ("Marcador da próstata (homens).",
    "Proteína da próstata. Sobe com o crescimento benigno, a inflamação e o cancro.",
    "Idade, próstata aumentada, prostatite, andar de bicicleta ou ejaculação nas 48 h antes, "
    "toque retal.",
    "Alguns medicamentos para a próstata.",
    "Colheita sem bicicleta nem ejaculação nas 48 h antes.",
    "Pedalar muito nas horas antes (falso alto).",
    "Num ciclista: não pedalar 48 h antes da colheita. Alto: repetir e médico."),
   ("Prostate marker (men).", "Prostate protein. Rises with benign growth, inflammation and "
    "cancer.",
    "Age, enlarged prostate, prostatitis, cycling or ejaculation in the 48 h before.",
    "Some prostate drugs.", "No cycling or ejaculation 48 h before the test.",
    "Lots of cycling in the hours before (falsely high).",
    "Cyclists: don't ride 48 h before the test. High: recheck and see the doctor."))
