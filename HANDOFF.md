# HANDOFF — TibiaRIP Bot

## Resumo Rápido
- **Janela**: `Tibia - Rafaelkrosa` (título) — `hwnd` via `find_window("Tibia -")`
- **Área client**: 1282×709 px — usa `WDA_MONITOR` (todos métodos padrão de captura retornam preto)
- **Execução**: `C:\Users\bessa\Documents\YiffyRip\TibiaRIP` — `python hunt_bot.py` (adm)
- **GitHub**: `https://github.com/The-Gabriel-Bessa/TBRIP`

---

## Estrutura do Projeto

```
TibiaRIP/
├── hunt_bot.py              # Orquestrador principal (loop de patrulha)
├── combat_until_clear.py    # Subprocesso de combate (scan de frame via OCR)
├── fast_attack.py           # FastAttackGuard (DISPONÍVEL mas NÃO USADO)
├── capture_internal.py      # find_window, press_key, capture_with_retry
├── read_battle_list.py      # OCR da battle list (1ª slot calibrado)
├── read_status_bars.py      # OCR HP/Mana/Level
├── read_combat_feedback.py  # OCR "destination out of range" etc
├── attack_once.py           # screenshot_to_screen, POINT
├── capture/                 # Abstração de captura (WDA via COM)
│   ├── __init__.py
│   ├── d3d11.py
│   ├── region.py
│   └── wda.py
├── vision/                  # Processamento de imagem OpenCV
│   ├── __init__.py
│   ├── preprocess.py
│   └── text_overlay.py
├── detectors/               # Detectores visuais
│   ├── __init__.py
│   ├── hp_bar.py
│   ├── mana_bar.py
│   ├── party_members.py
│   └── status_bar.py
├── state/                   # Gerenciamento de estado
│   ├── __init__.py
│   ├── hp_state.py
│   └── world_state.py
├── gui/                     # Interface OpenCV
│   ├── __init__.py
│   ├── camera.py
│   ├── overlay.py
│   └── status_hud.py
├── config/                  # Configurações
│   ├── __init__.py
│   └── settings.py
├── utils/                   # Utilidades
│   ├── __init__.py
│   ├── crop.py
│   └── windows.py
├── movement/
│   ├── pathfinding.py       # A* + cardinal WASD, DWWAA
│   ├── safe_walk.py         # execute_sequence (interrupt_check, stop_on_enemies)
│   └── world_model.py       # localize_in_reference, merge_observation
├── runtime/
│   ├── coordinator.py       # ActionCoordinator (decide/heal/combat/move)
│   ├── frame_pipeline.py    # FramePipeline com OCR readers
│   └── capture_store.py     # store_generated_screenshot
├── autoloot/
│   ├── detect_corpses.py    # Detecta corpos por cor na imagem
│   ├── mapped_loot.py       # Alt+Q autoloot
│   └── read_world_targets.py # Detecta targets no mundo
├── movement/amazon_camp_cave_reference.json  # Mapa de referência
├── runs/                    # Logs JSON de cada execução
└── runtime/captures/        # Screenshots da sessão
```

---

## Configuração da Battle List

```python
BATTLE_FIRST_REL_X = 0.905   # 90.5% da largura
BATTLE_FIRST_REL_Y = 0.605   # 60.5% da altura
BATTLE_FIRST_Y_OFFSET = 16   # pixels abaixo do centro da barra verde
```

- Barra verde detectada em: x=87.8%, y=66.7% (relativo ao frame)
- Slot 1 calibrado: x=90.5%, y=60.5% com offset +16

```python
LOOTABLE_CREATURES = {"Amazon", "Witch", "Valkyrie"}
```

---

## Parâmetros de Execução

```bash
python hunt_bot.py --max-moves 30 --segment-steps 15 --heal-below 70
python hunt_bot.py --no-autoloot
```

- `segment_steps=15`: cada segmento de movimento pode ter até 15 passos
- `verify_every=2`: screenshot a cada 2 passos durante movimento

---

## COMO COMBATE FUNCIONA (atualizado — SEM áudio)

1. `hunt_bot.py` detecta inimigo via screenshot + OCR (read_battle_list)
2. Entra em `combat_until_clear.py` como subprocesso
3. Subprocesso faz scan de frame → battle list OCR → detecta `matched_enemies`
4. Clica no 1º slot da battle list + P (attack_once)
5. Loop repete P por 2.5s, depois volta ao scan
6. Sai quando `battle["empty"]` = true por 2 scans consecutivos
7. Autoloot: detecta corpos por cor → Alt+Q
8. Retorna ao hunt_bot.py com checkpoint salvo

---

## Movimento

- **Direções**: WASD cardinais apenas
- **Diagonais**: QEZC (usadas para aproximação de corpse)
- **INITIAL_DEPARTURE**: `"DWWAA"` (desce, direita, esquerda, cima)
- **interrupt_check**: passado como `None` (sem interrupção por áudio)

---

## Criaturas / Loot

| Creature  | Drops desejados                          |
|-----------|------------------------------------------|
| Amazon    | Protective Charm                         |
| Witch     | Witch Broom, Protective Charm            |
| Valkyrie  | Girlish Hair Decoration, Protective Charm |

---

## Arquivos Importantes

| Arquivo                          | Função                                              |
|----------------------------------|-----------------------------------------------------|
| `hunt_bot.py`                   | Loop principal: decide move/combat/heal              |
| `combat_until_clear.py`         | Scan de frame + OCR + ataque + autoloot              |
| `fast_attack.py`                | FastAttackGuard (disponível, não usado)             |
| `movement/pathfinding.py`       | A* no reference JSON, retorna sequência WASD        |
| `movement/safe_walk.py`         | Executa sequência de teclas com interrupt_check      |
| `movement/world_model.py`       | Localiza posição no mapa de referência               |
| `read_battle_list.py`           # OCR battle list — retorna matched_enemies       |
| `read_status_bars.py`           | OCR HP/Mana/Level                                    |
| `runtime/frame_pipeline.py`     # FramePipeline com todos os OCR readers          |
| `runtime/coordinator.py`        # ActionCoordinator — decide estado               |
| `autoloot/detect_corpses.py`    | Detecta corpos por cor na imagem                     |
| `autoloot/mapped_loot.py`       | Executa Alt+Q autoloot                               |

---

## Alterações Recentes (esta sessão)

1. **Battle list Y offset** — calibrado de -10 → -22 → +22 → +16 pixels
2. **INITIAL_DEPARTURE** — alterado de "DDWAA" para "DWWAA"
3. **AudioTracker** — removido de hunt_bot.py e combat_until_clear.py
4. **FastAttackGuard** — removido de hunt_bot.py e combat_until_clear.py
5. **segment_steps** — aumentado de 10 para 15
6. **audio interrupt** — removido (interrupt_check=None)
7. **LOOTABLE_CREATURES** — filtro aplicado em combat_until_clear.py
8. **Supressão de áudio** — toda removida (era 1.0s após cada P)

---

## Notas para Próxima IA

- **O bot NÃO usa áudio para nada** — combate é 100% screenshot/OCR
- O `fast_attack.py` existe mas não é importado em nenhum lugar ativo
- O WDA captura retorna sempre preto — não adianta tentar其他 métodos de captura
- O reference JSON (`amazon_camp_cave_reference.json`) é o mapa de navegação
- `capture_state()` retorna `{"position": [x,y,z], "battle_empty": bool, "localized": bool}`
- O bot faz `capture_state` a cada passo durante movimento (verify_every)
- `execute_sequence` retorna `({"steps": [...], "error": ...}, exit_code)`
