# Runtime

Infraestrutura compartilhada do bot integrado.

`frame_pipeline.py` mantem um pool de workers independentes. Para cada screenshot, Battle List, HP/mana e mapa/posicao sao lidos simultaneamente. Todos recebem o mesmo `frame_id`; o coordenador so decide depois da barreira de resultados.

`coordinator.py` e o unico dono logico das acoes no cliente. A prioridade global e:

```text
cura > combate > loot > movimento
```

Somente uma acao pode manter o lock por vez. Os leitores nao pressionam teclas e nao movem o mouse.

O worker de audio do Tibia permanece ativo durante a patrulha para diagnostico. Ele nao bloqueia movimento sozinho porque sons continuos causavam um loop de `rescan`; a Battle List visual e a autoridade para iniciar combate. Deteccao de corpos e OCR do Loot Log sao workers condicionais, ativados somente depois de combate e loot, para nao desperdicarem CPU em todos os frames.

## Capturas

Frames do controlador integrado ficam em `runtime\captures`. O buffer e limitado aos 100 PNGs mais recentes; depois de uma copia bem-sucedida, o arquivo correspondente criado na pasta do Tibia e removido. Capturas historicas usadas como fixtures nao sao apagadas.

Nao execute `safe_walk.py`, `combat_until_clear.py` e `hunt_bot.py` como processos independentes ao mesmo tempo. O paralelismo correto acontece entre os leitores internos; `hunt_bot.py` serializa os escritores.

## Desempenho medido

Na fixture 1283x709:

```text
captura interna:         5.94 s
HP/mana antigo:         11.37 s
HP/mana rapido:          0.31 s
Battle List vazia antes: 0.59 s
Battle List vazia agora: 0.05 s
modelo do mapa:           0.14 s
pipeline paralelo frio:   0.74 s
```

O ciclo sem combate caiu de aproximadamente 17.9 segundos para 6.7 segundos. A reducao medida e de cerca de 63%, acima da meta de 50%. OCR de nomes so roda quando barras na Battle List indicam uma entrada; OCR numerico completo fica fora do ciclo de navegacao.

Um probe vivo com uma Amazon na Battle List levou 7.87 s no total, incluindo captura, e 1.14 s na etapa paralela de analise. O probe usou `--max-moves 0`, portanto nao enviou movimento, ataque ou loot.

No teste integrado de 22:11, as leituras durante patrulha ficaram entre 0.57 e 0.62 s. O bot concluiu combate contra duas Amazons, autoloot mapeado e depois retomou a patrulha automaticamente.

## Segundo ganho de velocidade

A patrulha valida ate dois comandos verdes por screenshot com `--verify-every 2` e reutiliza o ultimo frame entre segmentos. Aproximacao de corpos e perseguicao durante combate continuam verificando um tile por vez.

Os grupos vivos `DW`, `WA`, `AA` e `WW` levaram aproximadamente 8 segundos por grupo, ou 4 segundos por tile. O modo anterior levava aproximadamente 8 segundos por tile, resultando em outra reducao proxima de 50% na movimentacao sem combate.

O debug encontrou e corrigiu dois bloqueios: audio continuo causando `rescan` infinito e timeout ocasional do screenshot encerrando o combate. O audio agora e apenas diagnostico; captura, combate e loot usam retry sem repetir a tecla de movimento.
