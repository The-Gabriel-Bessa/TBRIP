# Movement

Modulo separado para localizacao e movimentacao. O controlador integrado reutiliza este bloco sem permitir que ele concorra com combate ou autoloot pelo teclado.

## Passo 1 - localizar e ampliar o minimapa

`zoom_minimap.py`:

1. Captura a interface completa.
2. Localiza o grande quadrado do minimapa por offsets fixos a partir da borda direita, que permanecem estaveis em modo janela e maximizado.
3. Valida formato, variacao de luminancia e presenca de cores.
4. Converte o centro para coordenadas reais da tela.
5. Posiciona o cursor no minimapa.
6. Envia cinco scrolls para cima.
7. Captura novamente e mede a diferenca visual.
8. Salva recortes antes e depois em `movement\captures`.
9. Termina em Chat On.

Uso:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\movement\zoom_minimap.py"
```

Nenhuma tecla de caminhada e enviada neste passo.

## Teste validado

Cinco scrolls para cima foram enviados no centro do minimapa. A janela mudou de tamanho entre as capturas, e o localizador por borda direita identificou corretamente os dois casos:

```text
Screenshot 1283x709: box [1115, 4, 1218, 117], center [1166, 60]
Screenshot 1600x900: box [1432, 4, 1535, 117], center [1483, 60]
```

Comparacao dos recortes antes e depois:

```text
mean_absolute_difference = 74.913
changed_pixels_percent = 78.744
visually_changed = true
```

Fixtures:

```text
movement\captures\2026-09-10_205959109_Rafaelkrosa_Hotkey_6.png
movement\captures\2026-09-10_210004080_Rafaelkrosa_Hotkey_6.png
```

O minimapa ficou no zoom detalhado solicitado e o script terminou em Chat On.

## Passo 2 - mapa local e gameplay

`world_model.py` transforma o minimapa ampliado em uma grade de tiles e relaciona essa grade com a gameplay:

1. Encontra o componente branco do personagem e define essa posicao como `(0,0,0)`.
2. Usa `x` positivo para leste/direita e `y` positivo para sul/baixo.
3. Separa verde caminhavel, cinza bloqueado, vermelho bloqueado e amarelo de subida.
4. Ignora o pequeno contorno amarelo do marcador branco para nao gerar uma escada falsa na origem.
5. Converte um offset visivel do mapa em um ponto da gameplay, cuja grade tem 15 por 11 tiles de 44 pixels.
6. Confirma por OCR que `Rafaelkrosa` aparece acima do tile central da gameplay.
7. Compara novas leituras com a referencia da cave para estimar a coordenada atual.

Referencia atual:

```text
movement\amazon_camp_cave_reference.json
origem: (0,0,0)
tiles conhecidos: 566
```

Analisar uma captura e localizar o personagem na referencia:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\movement\world_model.py" ".\movement\captures\2026-09-10_210004080_Rafaelkrosa_Hotkey_6.png" --reference ".\movement\amazon_camp_cave_reference.json"
```

Resultado validado na captura inicial:

```text
marcador branco: box [1484, 56, 6, 6]
centro no minimapa: [1486.5, 58.5]
centro na gameplay: [624, 302]
nome detectado: Rafaelkrosa
posicao localizada: [0, 0, 0]
tiles comparados: 566
concordancia: 100%
```

O mapa local usa `.` para verde, `#` para cinza, `R` para vermelho, `^` para escada, `P` para o personagem e `?` para regioes desconhecidas. Amarelos fora da area visivel da gameplay sao registrados, mas nao recebem ponto de clique ate ficarem dentro de `x=-7..7` e `y=-5..5`.

Esta etapa apenas interpreta screenshots. Ela nao envia teclas de movimento nem clica em escadas.

## Passo 3 - primeiros movimentos validados

Foram enviados tres `D`, sempre com captura e validacao antes do passo seguinte:

```text
2026-09-10_212151077: (0,0,0), 566/566 tiles
2026-09-10_212242926: (1,0,0), 543/543 tiles
2026-09-10_212333089: (2,0,0), 521/521 tiles
2026-09-10_212422417: (3,0,0), 499/499 tiles
```

Em todas as capturas, HP e mana estavam em 100% e a Battle List estava vazia. A escada escondida pelo personagem na origem apareceu sucessivamente nos offsets `(-1,0)`, `(-2,0)` e `(-3,0)`, confirmando que `(0,0,0)` e um tile `stairs_up_yellow`.

As quatro observacoes foram incorporadas em `amazon_camp_cave_reference.json`. A referencia cresceu de 566 para 635 tiles, sem conflitos de terreno. `--update-reference` permite incorporar uma nova captura apenas depois de uma relocalizacao confiavel:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\movement\world_model.py" "CAPTURA.png" --reference ".\movement\amazon_camp_cave_reference.json" --update-reference
```

Estado final deste teste: personagem em `(3,0,0)` e Chat Off. Nenhum movimento adicional foi enviado.

## Passo 4 - WASD, colisao e contorno

`safe_walk.py` executa somente `WASD`. Antes de cada comando, confere o terreno global na referencia; depois, captura o minimapa e exige a coordenada prevista. O pressionamento dura 60 ms para evitar teclas perdidas. Se o screenshot interno atrasar, o executor repete apenas a captura, nunca a tecla de movimento.

A sequencia manual `S D D W W A A A` foi executada a partir da origem:

```text
S -> ( 0,  1, 0) movido
D -> ( 1,  1, 0) movido
D -> ( 2,  1, 0) movido
W -> ( 2,  0, 0) movido
W -> ( 2, -1, 0) movido
A -> ( 1, -1, 0) movido
A -> ( 1, -1, 0) bloqueado por cinza em (0,-1,0)
A -> ( 1, -1, 0) bloqueado por cinza em (0,-1,0)
```

Depois da colisao, `pathfinding.py` calculou um contorno para oeste usando apenas verde:

```text
W A A A A A
(1,-1,0) -> (1,-2,0) -> (0,-2,0) -> (-1,-2,0)
          -> (-2,-2,0) -> (-3,-2,0) -> (-4,-2,0)
```

Todos os passos do contorno tiveram 100% de concordancia visual e Battle List vazia. A posicao final e `(-4,-2,0)`. A referencia passou a conter 784 tiles, cobrindo `x=-17..14` e `y=-15..9`.

Uso do executor:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\movement\safe_walk.py" "WASD" --start "x,y,z" --reference ".\movement\amazon_camp_cave_reference.json"
```

`--allow-blocked` deve ser usado apenas em testes intencionais de colisao. Sem essa opcao, o executor recusa qualquer destino cinza, vermelho, amarelo ou desconhecido.

## Saida inicial e antirretorno

Quando `hunt_bot.py` inicia em `(0,0,0)`, a primeira rota de patrulha e fixa:

```text
D -> ( 1,  0, 0)
W -> ( 1, -1, 0)
W -> ( 1, -2, 0)
A -> ( 0, -2, 0)
A -> (-1, -2, 0)
```

Todos esses pontos estao registrados como verdes. Cura e combate continuam tendo prioridade; a rota inicial so comeca quando for seguro mover.

A patrulha mantem as 20 posicoes mais recentes. O planejador penaliza fortemente:

- reverter imediatamente para o tile anterior;
- atravessar tiles presentes nessa janela recente;
- escolher destinos ja visitados muitas vezes na execucao atual.

O retorno continua permitido quando for a unica saida de um corredor. Depois que uma posicao sai da janela recente, ela volta a ser candidata normal, permitindo revisitar a area apos tempo suficiente para respawn.

## Verificacao em lote

Na patrulha, `--verify-every 2` envia ate dois comandos previamente confirmados como verdes antes do proximo screenshot. O frame final de um segmento e reutilizado como inicio do seguinte, removendo a captura duplicada.

O resultado deve ser exatamente a coordenada final prevista. Combate, aproximacao de corpos e perseguicao de alvo fugitivo continuam verificando um tile por vez.

Teste vivo da saida inicial:

```text
DW: (0,0,0) -> (1,-1,0), 8.2 s
WA: (1,-1,0) -> (0,-2,0), 8.3 s
```

Uma Amazon apareceu antes do ultimo `A`; a saida foi interrompida e o combate recebeu prioridade.

## Alvo fora de alcance

`combat_feedback.py` procura especificamente `Destination is out of range`. Somente quando essa mensagem aparece, nomes verdes e vermelhos na gameplay sao lidos, o offset do alvo e calculado e `attack_range_approach()` planeja ate dois passos verdes de perseguicao por vez. Sem a mensagem, o combate normal nao movimenta o personagem.

Tres falhas consecutivas para localizar ou alcancar o alvo encerram o combate em vez de manter um loop de ataques.

## Retorno depois do loot

Ao iniciar um combate, `hunt_bot.py` salva a coordenada de patrulha como checkpoint. Perseguicao e autoloot podem afastar o personagem; depois que a Battle List fica vazia, `return_to_checkpoint()` calcula uma rota verde de volta antes de permitir uma nova decisao de patrulha.

Se outro inimigo aparecer durante o retorno, o movimento para e o checkpoint original permanece pendente. O retorno tambem aceita `(0,0,0)` como destino especial, embora seja o tile amarelo da escada, pois andar para esse tile nao executa o clique de subida.
