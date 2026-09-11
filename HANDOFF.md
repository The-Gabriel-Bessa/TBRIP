# TibiaRIP - Handoff tecnico

Este documento registra o que foi descoberto e implementado em 10/09/2026. Ele permite que outra IA ou pessoa continue o projeto sem repetir a investigacao inicial.

## Objetivo

Construir um controlador visual para o cliente oficial do Tibia capaz de:

1. Observar HP, mana e Battle List.
2. Detectar atividade sonora somente do processo do Tibia.
3. Reconhecer inimigos permitidos.
4. Selecionar um alvo e executar a hotkey de ataque.
5. Curar abaixo de um limite.
6. Encerrar o combate quando a Battle List ficar vazia.

Movimentacao, caca por rotas e loot estao integrados em `hunt_bot.py`.

O autoloot esta isolado em `autoloot\` e foi reativado no fluxo integrado. `autoloot\mapped_loot.py` transforma corpos detectados em coordenadas globais, calcula aproximacao por tiles verdes com `WASD`, valida cada passo e so entao executa `Alt+Q`.

O modulo `movement\` localiza o minimapa por offsets da borda direita e ja validou cinco scrolls de zoom para cima em screenshots 1283x709 e 1600x900.

`movement\world_model.py` usa o ponto branco como origem local `(0,0,0)`, le tiles de 4x4 pixels no minimapa e classifica a cave atual: verde caminhavel, cinza/vermelho bloqueados e amarelo como subida clicavel. A grade logica da gameplay foi calibrada em 15x11 tiles de 44 pixels, com o personagem no centro.

Tres passos reais para leste foram validados individualmente nas coordenadas `(1,0,0)`, `(2,0,0)` e `(3,0,0)`, sempre com 100% de concordancia nos tiles comparados, HP/mana cheios e Battle List vazia. A escada da origem foi confirmada em `(0,0,0)`. A referencia agora contem 635 tiles e quatro observacoes, sem conflitos. Estado vivo ao terminar: `(3,0,0)`, Chat Off.

`movement\safe_walk.py` e `movement\pathfinding.py` adicionam execucao cardinal verificada e busca de caminhos verdes. No teste `S D D W W A A A`, os seis primeiros passos moveram o personagem e os dois ultimos confirmaram a parede em `(0,-1,0)`. O planejador contornou com `WAAAAA` e terminou em `(-4,-2,0)`. Cada passo foi relocalizado com 100% de concordancia e Battle List vazia. A referencia cresceu para 784 tiles (`x=-17..14`, `y=-15..9`). Estado vivo atual: `(-4,-2,0)`, Chat Off.

O usuario reposicionou manualmente o personagem em `(0,0,0)` depois desse teste.

`hunt_bot.py` coordena patrulha, combate e loot. `runtime\frame_pipeline.py` executa Battle List, HP/mana e mapa simultaneamente sobre o mesmo frame; `runtime\coordinator.py` serializa todas as acoes com prioridade `cura > combate > loot > movimento`. A leitura de HP/mana do ciclo de navegacao caiu de 11.37 s para 0.31 s e a Battle List vazia de 0.59 s para 0.05 s. Incluindo a captura interna de 5.94 s, o ciclo estimado caiu de 17.9 s para 6.7 s, reducao aproximada de 63%.

Probe vivo de `hunt_bot.py --max-moves 0` em 10/09/2026 22:07: posicao `(0,0,0)`, HP/mana 100%, uma Amazon na Battle List, analise paralela em 1.14 s e processo total em 7.87 s. Nenhuma acao foi enviada.

Teste integrado real de 22:11: duas Amazons eliminadas; corpos detectados em `[4,2]` e `[4,1]`; aproximacao `SDDD` validada de `(0,0,0)` ate `(3,1,0)`; duas tentativas de `Alt+Q` confirmadas pela aba Loot. A primeira registrou loot de 5 corpos e a segunda confirmou nenhum item restante em 4 corpos. Uma falha de encoding ao imprimir OCR foi corrigida com JSON ASCII-safe.

Depois da correcao, `hunt_bot.py --max-moves 4 --segment-steps 2` retomou a patrulha automaticamente com `SDWD`, passando por `(3,2)`, `(4,2)`, `(4,1)` e terminando em `(5,1,0)`. Todos os passos tiveram 100% de concordancia, Battle List vazia e leituras entre 0.57 e 0.62 s. A referencia atual contem 815 tiles (`x=-17..16`, `y=-15..9`). Estado vivo final: `(5,1,0)`, HP/mana 100%.

A saida inicial de patrulha foi padronizada como `DWWAA` quando a execucao comeca em `(0,0,0)`: `(1,0)`, `(1,-1)`, `(1,-2)`, `(0,-2)`, `(-1,-2)`, todos verdes. O planejador mantem uma janela de 20 posicoes e penaliza reversao imediata, caminhos recentes e destinos repetidos; retorno continua possivel em becos sem outra saida.

Capturas integradas novas usam um buffer rotativo de 100 arquivos em `runtime\captures`; a copia criada pelo hotkey na pasta do Tibia e removida depois de ser armazenada. Fixtures antigas permanecem intactas. `CAPTURE_ALTERNATIVES.md` registra as opcoes avaliadas, incluindo os assets locais `minimap-*.bmp.lzma`.

Otimizacao adicional: patrulha usa `--verify-every 2` e reaproveita o frame entre segmentos. Grupos de dois movimentos levaram cerca de 8 s, aproximadamente 4 s por tile contra 8 s anteriormente. Combate e autoloot continuam unitarios. A saida `DWWAA` foi iniciada ao vivo com `DW` e `WA`, mas uma Amazon apareceu antes do ultimo `A` e recebeu prioridade.

O loop de audio/rescan foi removido porque sons continuos impediam a patrulha. O audio permanece diagnostico e a Battle List inicia combate. `trigger_screenshot_with_retry()` agora protege captura, combate e loot contra timeout sem repetir movimentos.

`combat_feedback.py` detecta `Destination is out of range`; `read_world_targets.py` agora le nomes verdes e vermelhos. Somente com essa mensagem, o combate calcula uma perseguicao por tiles verdes, em blocos de no maximo dois passos, e depois reavalia. O frame real com Amazon vermelha em offset `[6,2]` produziu a rota `DDSDDD`; a condicao ainda nao reapareceu em combate ao vivo depois da correcao.

No teste de 22:56, uma Amazon surgiu durante `DWWAA`; outra Valkyrie surgiu durante a aproximacao ao corpo. O bot interrompeu ambos os movimentos, executou os combates e retomou a patrulha, terminando em `(-3,-4,0)` com 5 movimentos de patrulha contabilizados. O usuario informou depois que reposicionou manualmente o personagem em `(0,0,0)`.

O parser do Loot Log passou a normalizar ruido terminal antes de comparar linhas. Isso evita que uma linha antiga reaparecendo com `[`, `l¢` ou `l¥` seja registrada como novo item desejado. A referencia contem 894 tiles (`x=-17..16`, `y=-18..9`).

Politica adicionada depois: o inicio de cada combate grava um checkpoint da patrulha. Depois de perseguir e lotear, o bot usa `return_to_checkpoint()` antes de escolher outra area. Combates durante o retorno nao substituem o checkpoint original. O retorno ao `(0,0,0)` amarelo e permitido como destino, sem clique de escada. Esta politica passou nos testes offline, mas ainda nao foi exercitada ao vivo apos a implementacao.

Estado operacional informado pelo usuario ao final: personagem reposicionado manualmente em `(0,0,0)` e nenhum processo `hunt_bot.py`/`combat_until_clear.py` ativo.

## Aviso operacional

Automacao de gameplay pode violar as regras do Tibia e pode ser detectada pelo BattlEye. O codigo atual evita injecao e escrita na memoria do processo, mas ainda envia teclado e mouse. Use somente com entendimento desse risco.

## Ambiente confirmado

- Sistema: Windows 10 Pro 64 bits, build `19045`.
- GPU: NVIDIA GeForce RTX 3060.
- Python: `C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe`.
- Tesseract: `C:\Program Files\Tesseract-OCR\tesseract.exe`, versao 5.5.3.
- Cliente: `C:\Users\bessa\AppData\Local\Tibia\packages\Tibia\bin\client.exe`.
- Janela observada: `Tibia - Rafaelkrosa`.
- Classe da janela: `Qt693QWindowIcon`.
- Screenshots do jogo: `C:\Users\bessa\AppData\Local\Tibia\packages\Tibia\screenshots`.
- O PID observado foi `6624`, mas ele muda a cada execucao. Nunca fixe esse PID no codigo.

## Configuracao necessaria no Tibia

1. Ativar as opcoes avancadas.
2. Em `Options > Misc > Screenshots`, incluir a interface inteira.
3. A propriedade correspondente em `conf\clientoptions.json` e `screnshotsOnlyGameWindow: false`.
4. Associar `TakeScreenshot` a `Num *` em Chat On.
5. `Enter` alterna entre Chat On e Chat Off.
6. Chat Off e o modo usado para combate e movimento.

Hotkeys confirmadas pelo usuario e pela configuracao atual:

| Acao | Tecla |
|---|---|
| Alternar Chat On/Off | `Enter` |
| Screenshot interno | `Num *`, em Chat On |
| Ataque configurado | `P` |
| Cura configurada | `O` |
| Movimento cardinal | `W`, `A`, `S`, `D` |
| Movimento diagonal | `Q`, `E`, `Z`, `C` |
| Quick Loot Area At Player | `Alt+Q` |

## Por que capturas normais ficam pretas

A janela retornou `WindowDisplayAffinity = 0x1`, que corresponde a `WDA_MONITOR`. O jogo aparece no monitor fisico, mas o compositor entrega preto para metodos comuns de captura.

| Metodo | Resultado |
|---|---|
| `PrintWindow` padrao | 100% preto |
| `PrintWindow` com `PW_RENDERFULLCONTENT` | 100% preto |
| Recorte do desktop por GDI/Pillow | 100% preto |
| Windows Graphics Capture pelo monitor | 100% preto |
| Windows Graphics Capture pela janela | Falha ao criar `GraphicsCaptureItem` |
| NVIDIA Overlay | `Protected Content running`, depois `Screenshot failed` |
| Screenshot interno do Tibia | Funciona |
| Medal | Funcionou em testes anteriores |

O relatorio reproduzivel esta em `captures_focused\report.json`.

Logs antigos do Medal em `C:\Users\bessa\Documents\Medal\MedalLog20260816.txt` indicaram captura da swap chain D3D12 e injecao. Isso explica por que Medal conseguiu capturar antes da exclusao aplicada pelo compositor.

Nao existe uma forma externa simples de ler a textura diretamente da VRAM: o recurso nao possui handle compartilhado e o conteudo e tratado como protegido. Um hook como Medal ou OBS Game Capture seria a outra abordagem, mas aumenta o risco de conflito com BattlEye.

## Arquitetura atual

```text
Janela Tibia
  -> normalizar Chat para permitir screenshot
  -> screenshot interno completo
  -> selecionar o ultimo frame do backlog
  -> OCR de HP e mana
  -> OCR e analise de barras da Battle List
  -> converter coordenada do screenshot para a tela
  -> clicar no alvo permitido
  -> pressionar P no cooldown
  -> monitorar audio do PID do Tibia
  -> parar quando a Battle List ficar vazia
  -> pressionar Enter e terminar em Chat On
```

## Scripts

### `capture_diagnostic.py`

Compara captura GDI, `PrintWindow` e WGC. Mede luminancia, percentual de preto, classe da janela e `display_affinity`.

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\capture_diagnostic.py" --focus --output ".\captures_focused"
```

### `capture_internal.py`

Aciona o screenshot oficial e copia o PNG para `internal_captures`.

O estado inicial do Chat pode ser On ou Off:

1. Tenta `Num *` diretamente.
2. Se aparecer um arquivo `_Hotkey`, o Chat estava On; pressiona `Enter` para normalizar em Chat Off.
3. Se nao aparecer, pressiona `Enter`, usa `Num *` e pressiona `Enter` novamente.
4. Em caso de sucesso, sempre termina em Chat Off.

O jogo pode gerar seis frames de backlog com o mesmo timestamp e sufixos `_1` a `_6`. `_1` e o mais antigo e `_6` e o mais recente. O codigo espera o lote estabilizar e seleciona o maior nome, normalmente `_6`.

Somente arquivos com `_Hotkey` sao aceitos como resposta. Isso impede que um screenshot automatico de SkillUp ou LevelUp seja confundido com a captura solicitada.

Durante a captura, o arquivo temporario `.capture_in_progress` existe. O monitor de audio usa esse marcador para ignorar o som do proprio screenshot.

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\capture_internal.py"
```

### `read_status_bars.py`

Le HP e mana de duas formas:

1. Detecta barras pequenas sobre o personagem pelas cores verde `(0, 192, 0)` e azul `(0, 0, 255)`. A largura interna observada e 29 pixels.
2. Em screenshots completos, faz OCR apenas nas pequenas regioes do HUD superior.

O canal vermelho isola o texto branco do fundo colorido. O recorte e ampliado 10 vezes e enviado ao Tesseract com whitelist `0123456789/()` e `--psm 7`.

Saida validada:

```json
{
  "health": {"current": 315, "maximum": 315},
  "mana": {"current": 870, "maximum": 870},
  "health_numeric_percent": 100.0,
  "mana_numeric_percent": 100.0
}
```

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\read_status_bars.py"
```

### `read_battle_list.py`

Analisa uma ROI relativa no lado direito da imagem:

```text
x: 86% ate 100% da largura
y: 58% ate 79% da altura
```

A ROI e ampliada quatro vezes e lida pelo Tesseract com `--psm 6`. Os nomes sao normalizados para ASCII e comparados por similaridade.

Alvos padrao:

```python
("Amazon", "Valkyrie", "Witch")
```

Regras atuais:

- Similaridade minima: `0.8`.
- Match exato e aceito mesmo com confianca baixa.
- Match aproximado exige confianca minima de 20.
- Entradas visiveis sao contadas pelas barras de vida verde, verde selecionado, amarela ou vermelha.
- Cada resultado inclui a coordenada central do texto dentro do screenshot.
- Nomes repetidos permanecem como entradas separadas.

Validacao de nomes repetidos:

```text
Screenshot 2026-09-10_133644599_Rafaelkrosa_Hotkey_6.png
visible_entries = 3
matched_enemies = Valkyrie, Valkyrie, Valkyrie
coordenadas Y = 440, 462, 484
```

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\read_battle_list.py"
```

### `monitor_tibia_audio.py`

Usa `pycaw` e `IAudioMeterInformation` para medir somente a sessao de audio cujo PID pertence a janela do Tibia.

Spotify, Discord, navegador, microfone e audio geral do Windows nao entram na medicao. Durante o teste havia Spotify tocando, mas apenas PID `6624` foi consultado.

| Parametro | Valor padrao |
|---|---:|
| Threshold | `0.003` |
| Intervalo | `0.01 s` |
| Silencio para encerrar | `4.0 s` |

Teste real de 10 segundos:

```text
peak_max = 0.480841
active_samples = 179
eventos sonoros = 6
```

Outro teste durante combate:

```text
combat_started imediato
peak_max = 0.666730
estado final = combat
```

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\monitor_tibia_audio.py"
```

### `attack_once.py`

Executa uma unica acao controlada:

1. Captura a tela interna.
2. Recusa agir se nenhum alvo permitido for confirmado.
3. Escolhe a primeira entrada reconhecida.
4. Converte a coordenada do screenshot para o client rect atual.
5. Usa `ClientToScreen` para obter a coordenada absoluta.
6. Clica com botao esquerdo.
7. Pressiona `P`.
8. Restaura a posicao anterior do cursor.

Exemplo real:

```text
Alvo: Valkyrie
OCR: "�alkyrie"
Confianca: 84
Similaridade: 0.93
Screenshot click: [1162, 442]
Screen click: [1326, 516]
Resultado confirmado pelo usuario: Valkyrie eliminada
```

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\attack_once.py"
```

O script termina em Chat Off porque `capture_internal.py` normaliza para esse estado.

### `combat_until_clear.py`

Controlador de combate atual:

1. Inicia um `AudioTracker` em thread separada, filtrado pelo PID do Tibia.
2. Captura e le Battle List, HP e mana.
3. Pressiona `O` se HP estiver abaixo de `--heal-below`, padrao 70%.
4. Para imediatamente se a Battle List estiver vazia.
5. Para com seguranca apos duas leituras contendo somente entradas nao permitidas.
6. Clica na primeira entrada permitida e pressiona `P`.
7. Repete `P` a cada 1.8 segundos por ate 6 segundos.
8. Se houver 4 segundos de silencio, antecipa uma nova leitura em vez de abandonar um alvo ainda visivel.
9. Repete ate a Battle List esvaziar ou atingir o limite, padrao 60 segundos.
10. Ao terminar com estado de Chat conhecido, pressiona `Enter` e retorna a Chat On.

Teste real completo:

```text
13:46:16 scan: HP 100%, mana 100%, uma Valkyrie
13:46:17 clique + P
13:46:19 P
13:46:21 P
13:46:22 P
13:46:41 scan: Battle List vazia
motivo final: battle_list_empty
ataques: 4
curas: 0
audio_peak: 0.694453
estado final: Chat On
resultado confirmado pelo usuario: Valkyrie eliminada corretamente
```

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\combat_until_clear.py" --max-seconds 60 --silence 4 --heal-below 70
```

## Informacoes locais encontradas

Os arquivos em `AppData\Local\Tibia` contem configuracoes, hotkeys, sidebars, analisadores, cache e logs. Eles nao persistem HP e mana atuais.

- `characterdata\...\statusBarData.json` guarda apenas estilo e visibilidade.
- `characterdata\...\xpanalyser.json` guarda preferencias do analisador.
- `conf\clientoptions.json` guarda hotkeys e configuracao visual.
- A arvore UI Automation do Qt expoe action buttons, slots, chat entries e objetos `BattleListEntry`, mas nao expoe nomes ou HP/mana de forma util.
- O processo permitiu abrir handles de leitura, mas nao foi feita varredura de offsets. Isso seria fragil entre atualizacoes e adicionaria risco com BattlEye.

## Resultados preservados

Arquivos importantes em `internal_captures`:

| Arquivo | Conteudo |
|---|---|
| `2026-09-10_124141417_Rafaelkrosa_Hotkey_1.png` | Interface completa, HP 315/315, mana 870/870 |
| `2026-09-10_133346791_Rafaelkrosa_Hotkey_6.png` | Valkyrie reconhecida e combate ativo |
| `2026-09-10_133548245_Rafaelkrosa_Hotkey_6.png` | Base do primeiro ataque real |
| `2026-09-10_133644599_Rafaelkrosa_Hotkey_6.png` | Tres entradas Valkyrie simultaneas |
| `2026-09-10_134602677_Rafaelkrosa_Hotkey_6.png` | Ciclo completo antes do ataque validado |
| `2026-09-10_134626911_Rafaelkrosa_Hotkey_6.png` | Battle List vazia apos o ataque |

Exemplo de Amazon no diretorio original:

```text
C:\Users\bessa\AppData\Local\Tibia\packages\Tibia\screenshots\2026-09-10_125933122_Rafaelkrosa_Hotkey_6.png
OCR Amazon: confianca 96, similaridade 1.0
```

## Dependencias

```text
numpy==2.2.6
opencv-python==5.0.0.93
Pillow==12.3.0
pycaw==20251023
pytesseract==0.3.13
psutil==7.2.2
windows-capture==2.0.0
```

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" -m pip install -r ".\requirements.txt"
```

## Procedimento de reconstrucao

1. Confirmar que o Tibia esta aberto e logado.
2. Confirmar screenshots com interface completa.
3. Confirmar `TakeScreenshot = Num *` em Chat On.
4. Instalar dependencias e Tesseract.
5. Rodar `capture_internal.py` e esperar `scope = whole_client_interface`.
6. Rodar `read_status_bars.py` em uma fixture conhecida.
7. Rodar `read_battle_list.py` em `2026-09-10_133644599...` e esperar tres Valkyries.
8. Rodar `monitor_tibia_audio.py --duration 10` enquanto Spotify e Tibia produzem audio; confirmar que o PID e somente do Tibia.
9. Usar `attack_once.py` apenas com supervisao.
10. Usar `combat_until_clear.py` somente depois de validar coordenadas e estado do Chat.

## Retomada apos queda ou reinicio

1. Reabrir o Tibia e entrar no personagem.
2. Esperar o titulo mudar de `Tibia` para `Tibia - <personagem>`.
3. Nao reutilizar o PID antigo. Os scripts localizam novamente a janela e derivam o PID atual.
4. Confirmar que nao existe `.capture_in_progress` deixado por encerramento abrupto. Se existir sem uma captura rodando, ele e um marcador obsoleto.
5. Rodar primeiro `capture_internal.py`, sem ataque, para confirmar screenshot, Chat e OCR.
6. Rodar `monitor_tibia_audio.py --duration 10` depois que o cliente produzir algum som e criar a sessao de audio.
7. Somente entao testar `attack_once.py` ou `combat_until_clear.py`.

Se o cliente fechar enquanto um script estiver rodando, encerre o script e reinicie o fluxo. O codigo atual nao reconecta automaticamente a uma nova janela ou sessao de audio.

Validacao sintatica:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" -m py_compile ".\capture_diagnostic.py" ".\capture_internal.py" ".\read_status_bars.py" ".\read_battle_list.py" ".\monitor_tibia_audio.py" ".\attack_once.py" ".\combat_until_clear.py"
```

## Limitacoes conhecidas

1. Screenshot interno e OCR sao lentos para tempo real. Uma iteracao completa observada levou mais de 15 segundos.
2. O jogo gera ate seis frames de backlog e produz som ao capturar.
3. O audio por pico detecta qualquer som do Tibia, nao apenas combate. Passos, interface, loot, cura e screenshots automaticos podem causar falso positivo.
4. O marcador ignora screenshots iniciados por `capture_internal.py`, mas nao screenshots automaticos do jogo.
5. A ROI da Battle List e relativa, mas ainda pressupoe o layout atual.
6. A leitura de HP/mana pressupoe o HUD superior no layout atual.
7. O controlador escolhe sempre o primeiro alvo permitido; nao ha prioridade por vida, distancia ou tipo.
8. A cura automatica esta implementada, mas ainda nao foi validada abaixo de 70%.
9. Nao ha confirmacao visual de que cada `P` causou dano; somente audio e desaparecimento da entrada.
10. Entradas nao permitidas nunca sao clicadas.
11. `attack_once.py` deixa Chat Off; `combat_until_clear.py` tenta terminar em Chat On.
12. Se a primeira captura falhar, o estado do Chat e `unknown` e nao deve ser alternado cegamente.
13. Nao existem testes automatizados, fixtures reduzidas ou log persistente das decisoes.
14. O projeto ainda nao usa Git.

## Proximos passos recomendados

### 1. Controlador central e dry-run

Unificar captura, audio, OCR e input em uma maquina de estados:

```text
IDLE_CHAT_ON
MOVING_CHAT_OFF
COMBAT_SCAN
TARGET_SELECTED
ATTACKING
LOOTING
RECOVERING
ERROR
```

Adicionar `--dry-run` como padrao. Registrar clique e tecla sem envia-los e exigir `--execute` para controlar o jogo.

### 2. Reduzir latencia

Investigar por que o jogo gera seis frames apesar de `screenshotsUseBacklog` ter aparecido como falso no arquivo. Desativar backlog pela interface pode reduzir atraso.

Opcoes adicionais:

1. Rodar OCR somente quando pixels indicarem mudanca.
2. Executar HP, mana e Battle List em paralelo.
3. Usar templates de digitos e nomes para o layout fixo.
4. Manter OCR em um worker persistente.
5. Reavaliar Medal ou OBS para frames continuos, considerando BattlEye.

### 3. Movimento para cacar inimigos

Comecar com uma rota de waypoints, nao navegacao livre:

1. Manter Chat Off durante movimento.
2. Percorrer direcoes `W/A/S/D/Q/E/Z/C` por numero de passos.
3. Pausar imediatamente quando o audio do Tibia indicar atividade.
4. Capturar e verificar a Battle List.
5. Entrar em `COMBAT_SCAN` se houver alvo permitido.
6. Retomar do waypoint atual depois do loot.

Deteccao de travamento:

1. Comparar a ROI do minimapa antes e depois de cada passo.
2. Se o minimapa nao mudar por varias tentativas, marcar bloqueio.
3. Tentar uma direcao alternativa limitada.
4. Nunca enviar movimento indefinidamente sem confirmacao visual.

Depois da rota fixa funcionar, evoluir para localizacao pelo minimapa, marcadores e grafo de navegacao.

### 4. Loot

A configuracao atual possui `QuickLootAreaAtPlayer = Alt+Q`, mas o personagem precisa estar proximo do corpo. Nao dispare essa hotkey imediatamente depois de a Battle List esvaziar.

1. Esperar Battle List vazia.
2. Usar o numero e tipo de inimigos observados para definir quantos corpos procurar.
3. Detectar cada corpo com os templates de `DeadBodys`.
4. Calcular a rota ate um tile adjacente.
5. Executar um passo e relocalizar antes do passo seguinte.
6. Pressionar `Alt+Q` uma vez quando estiver adjacente.
7. Confirmar pelo Loot Log e gravar o corpo/encontro no ledger.
8. Repetir para o proximo corpo ainda nao processado.
9. Retomar a rota de caca.

O teste integrado de 20:14 enviou `Alt+Q` uma vez, mas o cliente respondeu `The container for unassigned loot is full`. O parser agora classifica isso como `blocked_container_full`, e o ledger impede repeticao para o mesmo encontro. O container precisa ser esvaziado ou configurado antes do proximo teste.

### 5. Cura e mana

Validar `O` em teste supervisionado abaixo de 70%.

Adicionar cooldown confirmado visualmente, histerese, limite critico para abandonar a caca e acao para mana baixa depois que a hotkey correta for informada.

### 6. Visao mais robusta

1. Encontrar dinamicamente o titulo `Battle List` antes de definir a ROI.
2. Associar texto, barra e icone da mesma linha.
3. Adicionar fixtures de Amazon, Valkyrie, Witch, lista vazia, alvo selecionado e vida baixa.
4. Testar escalas de interface e tamanhos de janela diferentes.
5. Exigir duas leituras concordantes antes de clicar em match aproximado.

### 7. Seguranca operacional

1. Hotkey global de emergencia.
2. Limite de ataques, curas e movimentos por sessao.
3. Parar se a janela perder foco ou mudar de personagem.
4. Parar se HP nao puder ser lido.
5. Parar diante de entrada fora da whitelist conforme politica definida.
6. Registrar decisoes em JSONL com screenshot associado.
7. Restaurar cursor e estado do Chat em todos os erros.

## Criterio de sucesso da proxima fase

```text
Chat On e parado
-> audio exclusivo do Tibia detectado
-> Chat Off
-> inimigo permitido reconhecido
-> combate ate Battle List vazia
-> cura quando necessario
-> Alt+Q para loot
-> retomar rota
-> Chat On ao encerrar
```
