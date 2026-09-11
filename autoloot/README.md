# Autoloot

Modulo separado do combate. `combat_until_clear.py` agora ativa por padrao a aproximacao mapeada e o autoloot; use `--no-autoloot` para desativar.

## Passo 1 - selecionar o canal Loot

`select_loot_tab.py` executa o seguinte fluxo:

1. Usa o screenshot interno do Tibia.
2. Procura visualmente a palavra `Loot` apenas na faixa de abas do chat.
3. Recusa clicar se o texto nao for reconhecido.
4. Converte a coordenada do screenshot para o client rect atual.
5. Clica na aba `Loot`.
6. Captura novamente.
7. Executa OCR sobre as linhas visiveis do canal para confirmar mensagens de loot.

Uso a partir de `TibiaRIP`:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\autoloot\select_loot_tab.py"
```

As capturas deste modulo ficam em `autoloot\captures`, separadas de `internal_captures`.

## Teste validado

Teste executado em 10/09/2026 20:00:

```text
OCR da aba: Loot
Confianca: 95
Coordenada no screenshot: [258, 629]
Coordenada na tela: [424, 703]
Resultado: canal Loot selecionado
```

Texto lido depois do clique:

```text
19:57 You looted none of the dropped items. (3 corpses)
19:57 You looted nothing from 3 corpses.
19:58 Loot of an amazon: a dagger, 5 gold coins.
```

Fixture preservada:

```text
autoloot\captures\2026-09-10_200046321_Rafaelkrosa_Hotkey_6.png
```

Este passo apenas seleciona e le o canal. Nenhum comando de coleta foi enviado.

## Passo 2 - parser e tentativa unica

`loot_log.py` compara o texto anterior e posterior do canal e estrutura apenas linhas novas. Os resultados terminais reconhecidos incluem:

- `Loot of ...`
- `You looted ...`
- `You looted nothing ...`
- `You looted none ...`
- `The container for unassigned loot is full`

`loot_once.py` envia `Alt+Q` no maximo uma vez por `encounter_id`. Cada tentativa e gravada em `loot_attempts.jsonl`; uma segunda chamada com o mesmo ID retorna `skipped_already_attempted` antes de qualquer input.

No primeiro teste integrado, duas Amazons foram mortas e `Alt+Q` foi enviado uma vez. O jogo respondeu:

```text
Attention! The container for unassigned loot is full.
```

O aviso de container de loot nao atribuido cheio pertence ao Server Log, e ignorado pelo parser e nao bloqueia a confirmacao feita exclusivamente na aba Loot.

## Passo 3 - localizar e aproximar dos corpos

As amostras em `..\DeadBodys` foram validadas. Elas sao imagens 400x400 ampliadas; o detector reduz os templates para aproximadamente o tamanho de um tile no screenshot.

`read_world_targets.py` isola os nomes verdes do mapa e registra a ultima posicao dos inimigos vivos em relacao ao personagem.

`detect_corpses.py` usa OpenCV, templates em varias escalas e o numero esperado de mortes para limitar falsos positivos.

Teste offline com os dois corpos de Amazon do ultimo combate:

```text
Corpo 1: score 0.7071, offset [-4, 0]
Corpo 2: score 0.6702, offset [-2, 3]
```

`approach_plan.py` calculou:

```text
[-4, 0] -> A, A, A -> termina adjacente em [-1, 0]
[-2, 3] -> Z, Z -> termina adjacente em [0, 1]
```

`mapped_loot.py` converte o offset de cada corpo em coordenada global, escolhe um tile verde adjacente e usa apenas `WASD`. Cada passo e confirmado pelo minimapa; parede, localizacao ambigua ou novo inimigo interrompem a aproximacao antes de `Alt+Q`.

Comando de teste do detector:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\autoloot\detect_corpses.py" ".\internal_captures\2026-09-10_201347143_Rafaelkrosa_Hotkey_6.png" --creature Amazon --count 2
```

No fluxo de combate normal, a aproximacao mapeada e executada por padrao. A antiga tentativa imediata sem aproximacao foi removida do caminho integrado.

## Estado integrado

- Aproximacao usa o mapa persistente e apenas tiles verdes.
- Movimento usa somente `WASD`.
- Cada corpo recebe um identificador de ledger proprio para evitar repeticao.
- Novo combate durante a aproximacao cancela o movimento e devolve prioridade ao combate.
- `Alt+Q` so e enviado a partir de um tile adjacente calculado.
- Resultado continua sendo confirmado exclusivamente pela aba Loot.
- Planejamento e parser possuem testes offline, e o fluxo completo foi validado em teste supervisionado.

## Teste vivo integrado

Em 10/09/2026 22:11, o controlador matou duas Amazons, detectou os corpos nos offsets `[4,2]` e `[4,1]` e calculou a aproximacao `S D D D`, saindo de `(0,0,0)` e chegando a `(3,1,0)`.

O primeiro `Alt+Q` foi confirmado pela aba Loot com mensagens de loot de 5 corpos. A segunda tentativa confirmou que nao havia itens restantes em 4 corpos. As duas entradas foram persistidas separadamente no ledger com status `confirmed_no_wanted_items`.

O teste validou ao vivo combate, deteccao de corpos, aproximacao pelo mapa, movimento `WASD`, ledger e confirmacao pela aba Loot.

O debug posterior mostrou que uma linha antiga podia reaparecer com outro sufixo de OCR (`[`, `l¢`, `l¥`) e parecer nova. A comparacao agora remove apenas esse ruido terminal; quantidades e nomes de itens continuam intactos. Registros historicos anteriores a essa correcao podem conter `confirmed_wanted_items` falso, mas novas tentativas nao reutilizam essas linhas.
