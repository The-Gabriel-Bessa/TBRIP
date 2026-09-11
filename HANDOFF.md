# HANDOFF — TibiaRIP Bot

## Resumo Rápido
- **Janela**: `Tibia - Rafaelkrosa` (título) — `hwnd` via `find_window("Tibia -")`
- **Área client**: 1282×709 px — usa `WDA_MONITOR` (todos métodos padrão de captura retornam preto)
- **Captura primaria**: `OBS Virtual Camera` via FFmpeg/DirectShow; screenshot interno e fallback
- **Execução**: `C:\Users\bessa\Documents\YiffyRip\TibiaRIP` — `python hunt_bot.py --capture-source obs` (adm)
- **GitHub**: `https://github.com/The-Gabriel-Bessa/TBRIP`
- **Character**: Rafaelkrosa, HP 320/320, Mana 900/900, Amazon camp cave

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
├── iniciar_bot.bat          # Script de inicialização com defaults
├── capture/                 # Abstração de captura (WDA via COM)
├── vision/                  # Processamento de imagem OpenCV
├── detectors/               # Detectores visuais
├── state/                   # Gerenciamento de estado
├── gui/                     # Interface OpenCV
├── config/                  # Configurações
├── utils/                   # Utilidades
├── movement/
│   ├── pathfinding.py       # A* + cardinal WASD, combat_retreat_step, attack_range_approach
│   ├── safe_walk.py         # execute_sequence (interrupt_check, stop_on_enemies)
│   ├── world_model.py       # localize_in_reference, merge_observation
│   └── zoom_minimap.py      # Crop/zoom do minimapa
├── runtime/
│   ├── coordinator.py       # ActionCoordinator (decide/heal/combat/move)
│   ├── frame_pipeline.py    # FramePipeline com OCR readers
│   ├── frame_source.py      # Stream OBS sincronizado + fallback de screenshot
│   ├── capture_store.py     # store_generated_screenshot
│   └── chat_state.py        # Chat Off OCR
├── autoloot/
│   ├── detect_corpses.py    # Detecta corpos por template matching
│   ├── mapped_loot.py       # Alt+Q autoloot com re-detecção de corpos
│   └── read_world_targets.py # Detecta targets no mundo
├── movement/amazon_camp_cave_reference.json  # Mapa de referência (A*)
├── runs/                    # Logs JSON de cada execução
└── runtime/captures/        # Screenshots da sessão
```

---

## O que foi feito nesta sessão (11/09/2026)

### 1. F2 (Mana Restore) — REMOVIDO COMPLETAMENTE
- **Problema**: OCR lia mana como 80/900 (8.9%) quando na realidade era 900/900. Verificação duplia também lia 80/900 (falso positivo consistente). F2 disparava sem necessidade e interrompia autoloot.
- **Solução**: Removido F2 de todos os arquivos: `combat_until_clear.py`, `hunt_bot.py`, `safe_walk.py`, `mapped_loot.py`, `coordinator.py`, `iniciar_bot.bat`. Removido `--mana-below` CLI arg, `mana_below` parameter, `restore_mana` do coordinator.
- **Commits**: `175d72f`

### 2. Retreat Loop — CORRIGIDO
- **Problema**: Com 4+ inimigos, retreat era acionado ANTES do ataque. Retreat sempre retornava `completed: false` (movimento falhava), fazia `continue`, e o bot nunca chegava ao código de ataque. Loop infinito de 31 retreats em 60 segundos.
- **Solução**: Se retreat falha (`exit_code != 0`), não fazer `continue` — cair direto no ataque.
- **Commits**: `52bf3a8`

### 3. Autoloot não dispara com entries não-whitelisted — CORRIGIDO
- **Problema**: Autoloot só dispara quando `battle["empty"]` (visible_entries == 0). QuandoNPC não-whitelisted ficava na battle list (entries > 0 mas enemies vazio), o bot entrava em `entries_not_whitelisted` sem lootear.
- **Solução**: Reestruturada lógica de fim-de-combate. Autoloot agora dispara quando `battle["empty"]` OU `(not enemies and attacks > 0)`. Unmatched scans incrementam para 2 antes de quebrar.
- **Commits**: `52bf3a8`

### 4. Target Chase Failure — NON-FATAL + TRY OTHERS
- **Problema**: Chase failure retornava exit code 2 (fatal), crashando o hunt.此外, quando um inimigo fugia da tela, o bot tentava o mesmo inimigo indefinidamente.
- **Solução**: `target_chase_failed` e `all_targets_chase_failed` adicionados ao `non_fatal` set (exit code 0). Implementado `chase_failed_indices` para rastrear inimigos que falharam chase, tentar outros inimigos primeiro, e quebrar quando todos falharem (deixa patrulha continuar e reencontrar o inimigo).
- **Commits**: `52bf3a8`, `5a11d39`

### 5. Movimento mais rápido — REDUZIDO DELAYS
- **Problema**: Cada passo de movimento levava ~0.71s (0.25 focus + 0.06 key hold + 0.4 delay).
- **Solução**: Delay entre teclas reduzido de 0.4s → 0.2s. Pre-group delay reduzido de 0.25s → 0.15s. Agora ~0.41s por passo (~40% mais rápido).
- **Commits**: `3db36d4`

### 6. Sempre clicar battle list antes de P — CORRIGIDO
- **Problema**: Quando 3 Amazons na battle list e uma morria, outra com HP full substituía. Bot precisava re-clicar para selecionar novo alvo.
- **Solução**: Sempre clicar no slot da battle list antes de cada ataque.
- **Commits**: `23e130d`

### 7. Chase mais largo — CORRIGIDO
- **Problema**: Chase com range=1 e max_steps=2 não alcancava inimigos que fugiam.
- **Solução**: Chase usa range=3 com max_steps=12, 3 teclas de chase em vez de 2, tolerância aumentada de 3→5 antes de desistir.
- **Commits**: `3818988`

### 8. Autoloot re-detecção de corpos — CORRIGIDO
- **Problema**: Autoloot tentava lootebar corpos que já tinham sido looteados ou que sumiram.
- **Solução**: Após cada loot bem-sucedido, `detect_corpses()` re-detecta corpos na screenshot atual. Offsets recalculados. Max 6 tentativas por encounter. Exit code 3 (interrupted_for_resource) pula corpse ao invés de quebrar loop.
- **Commits**: `87670d1`

---

## O que FUNCIONA agora

1. ✅ **Combate**: Ataca, cura (O heal < 90%, F1 emergência < 300HP), retreat quando 4+ inimigos
2. ✅ **Autoloot**: Detecta corpos, se aproxima, usa Alt+Q, re-detecta, looteia múltiplos corpos
3. ✅ **Chase**: Persegue inimigos que fogem (range 3, 12 steps), tenta outros se um falha
4. ✅ **Retreat**: Sai de situações com muitos inimigos, cai no ataque se retreat falhar
5. ✅ **Captura OBS**: 29 FPS, funcional para patrulha, combate, chase e autoloot
6. ✅ **Não-fatal errors**: Muitos exit codes agora são non-fatal (0), permitindo que o bot continue
7. ✅ **Movimento rápido**: ~0.41s por passo (antes ~0.71s)

---

## GAPS / Problemas Restantes

### CRÍTICO: Localização do minimapa pula posições
- **Problema**: Após autoloot mover o personagem, a localização às vezes pula posições. Ex: pressionou A em [4,-1,0] esperando [3,-1,0], mas observou [4,-1,0] (não moveu) ou [2,-1,0] (pulou).
- **Impacto**: Crash com `RuntimeError: Grupo A: esperado [X], observado [Y]`. Bot não consegue retornar ao ponto 0 após loot.
- **Causa provável**: Minimap tile matching usando template/static comparison falha quando há obstáculos, mudanças de iluminação, ou quando o personagem está em posição intermediária entre tiles.
- **Solução proposta pelo usuário**: Usar **OpenCV + YOLO/Ultralytics ou Detectron2** para detecção robusta de posição no minimapa. Modelos de detecção de objetos treinados seriam muito mais robustos que o matching atual.

### MÉDIO: OCR de status às vezes falha
- **Problema**: `status_read_failed` acontece várias vezes seguidas. Quando OCR falha, HP é lido como `null` e o fallback leva ~1s extra.
- **Impacto**: HP caiu para 6.9% (22 HP!) numa ocasião porque o OCR não leu o HP por vários scans while o personagem estava tomando dano.
- **Causa**: Barras do personagem (character bars) não são detectadas confiavelmente. Fallback para numeric HUD funciona na maioria das vezes mas às vezes também falha.

### MÉDIO: Autoloot timeout com múltiplos corpos espalhados
- **Problema**: 3+ corpos espalhados → autoloot excede 60s de `combat_max_seconds`.
- **Impacto**: Exit code 124 (timeout), corpos não looteados.
- **Solução**: Aumentar `combat_max_seconds` ou tornar autoloot mais rápido (reduzir delays entre loots).

### BAIXO: Autoloot detecta poucos corpos
- **Problema**: Espera 3 corpos, detecta apenas 1-2. Corpos podem sumir ou ficar fora do viewport.
- **Impacto**: Loot incompleto.

### BAIXO: reference.json se degrada
- **Problema**: `merge_observation` atualiza o reference JSON durante movimento. Algumas atualizações podem introduzir erros.
- **Impacto**: Localização pode piorar ao longo do tempo.

---

## Configuração de Execução

```bash
# Padrão (recomendado)
python hunt_bot.py --max-moves 30 --segment-steps 10 --verify-every 1 --autoloot --heal-below 90 --emergency-hp 300 --retreat-enemies 4

# Sem autoloot
python hunt_bot.py --max-moves 30 --segment-steps 10 --verify-every 1 --no-autoloot --heal-below 90 --emergency-hp 300 --retreat-enemies 4
```

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `--max-moves` | 30 | Total de passos de movimento |
| `--segment-steps` | 10 | Passos por segmento de patrulha |
| `--verify-every` | 1 | Frames entre verificações de movimento |
| `--heal-below` | 90 | HP% para curar com O |
| `--emergency-hp` | 300 | HP absoluto para F1 emergência |
| `--retreat-enemies` | 4 | Número de inimigos para trigger retreat |
| `--combat-max-seconds` | 60 | Timeout do combate (inclui autoloot) |
| `--capture-source` | auto | OBS com fallback; `obs` para exigir stream |

---

## Comandos Úteis

```bash
# Rodar o bot
python hunt_bot.py --max-moves 30 --segment-steps 10 --verify-every 1 --autoloot --heal-below 90 --emergency-hp 300 --retreat-enemies 4

# Rodar testes
python -m pytest movement/test_pathfinding.py runtime/test_runtime.py movement/test_world_model.py autoloot/test_mapped_loot.py -q

# Verificar pyflakes
python -m pyflakes combat_until_clear.py hunt_bot.py movement/safe_walk.py autoloot/mapped_loot.py runtime/coordinator.py

# Iniciar via bat
iniciar_bot.bat
```

---

## Notas para Próxima IA

- **O bot NÃO usa áudio para nada** — combate é 100% frame visual/OCR
- WGC, PrintWindow e dxcam continuam bloqueados pelo WDA; OBS Game Capture + Virtual Camera funciona
- A Camera Virtual deve estar iniciada e a fonte do Tibia em `Fit to screen`, sem stretch/crop manual
- O reference JSON (`amazon_camp_cave_reference.json`) é o mapa de navegação para A*
- `capture_state()` retorna `{"position": [x,y,z], "battle_empty": bool, "localized": bool}`
- O bot solicita um frame posterior a cada passo durante movimento (`verify_every=1` por padrao)
- `execute_sequence` retorna `({"steps": [...], "error": ...}, exit_code)`
- **PRIORIDADE DE AÇÃO**: emergency_heal (F1) > heal (O) > retreat > combat > loot > move
- **F2 foi removido** — mana 900/900 nunca precisa de potion, OCR tinha false positives
- **Known targets**: `LOOTABLE_CREATURES = {"Amazon", "Witch", "Valkyrie"}`
- **PRÓXIMO PASSO SUGERIDO**: Substituir localização do minimapa (atual: tile matching estático) por **YOLO/Ultralytics ou Detectron2** treinado para detectar posição do personagem no minimapa. O usuário especificamente pediu isso.
