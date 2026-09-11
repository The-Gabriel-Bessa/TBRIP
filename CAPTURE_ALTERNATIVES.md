# Alternativas aos screenshots

## Situacao atual

O cliente usa `WindowDisplayAffinity = WDA_MONITOR` e conteudo protegido. Neste computador, `PrintWindow`, captura do desktop, Windows Graphics Capture, NVIDIA Overlay e captura do monitor ja retornaram preto ou foram recusados.

O screenshot interno continua sendo a fonte de fallback que:

- nao injeta codigo no cliente;
- mostra gameplay, minimapa, Battle List, HP/mana e Loot Log;
- funciona com a protecao atual.

## Fonte primaria adotada

O OBS Game Capture desta maquina consegue capturar o Tibia e publica o resultado pela `OBS Virtual Camera`. O bot consome esse dispositivo por FFmpeg/DirectShow, sem usar `dxcam`, e recebe frames continuamente. O OBS realiza o hook; o bot nao injeta codigo adicional no cliente.

O canvas ativo foi detectado como `1600x900`, embora a camera parada anunciasse `1280x720`. Por isso o runtime aceita o formato nativo, converte a saida para `1280x720`, remove as barras do `Fit to screen` e restaura o tamanho da area cliente antes da deteccao. Os detectores de barra e minimapa toleram a conversao RGB/YUV do OBS.

`--capture-source auto` valida os leitores em dois frames e volta ao screenshot interno se o OBS estiver parado, mostrar o placeholder ou estiver mal enquadrado. `--capture-source obs` rejeita o frame e encerra; `--capture-source screenshot` ignora o OBS.

## Fontes que podem reduzir processamento visual

O cliente possui centenas de arquivos `assets\minimap-*.bmp.lzma`, alem de `map-*.dat` e `staticmapdata-*.dat`. Eles podem fornecer terreno estatico depois que a cave local for alinhada ao mapa oficial. Eles nao informam posicao atual, criaturas, HP/mana, corpos ou se um movimento falhou.

O melhor caminho e hibrido:

1. Usar mapa estatico e a referencia persistente para planejar.
2. Atualizar a posicao prevista pelas teclas enviadas.
3. Ler Battle List e barras em cada frame de decisao.
4. Corrigir a posicao pelo minimapa depois de cada movimento.

Depois de mais validacao, ainda sera possivel confirmar a cada dois ou tres passos em corredores conhecidos. O padrao atual mantem um frame por tile porque a captura deixou de ser o gargalo e isso reduz o intervalo ate detectar um bloqueio ou inimigo.

## Alternativas que nao resolvem o estado vivo

- APIs web do Tibia fornecem dados publicos de personagem e mundo, nao telemetria em tempo real da sessao.
- GitHub pode fornecer parsers e formatos conhecidos, mas nao acesso privilegiado ao cliente em execucao.
- UI Automation do Qt expoe controles, mas nao o estado renderizado da gameplay.
- Arquivos JSON locais guardam configuracoes e historicos de analisadores, nao posicao e HP atuais.
- NVIDIA Video Codec SDK codifica frames que ja foram adquiridos; ele nao ignora por si so a protecao de captura.

## Alternativas tecnicas nao adotadas

- Um hook proprio de Direct3D nao foi adotado. O OBS Game Capture ja em uso captura antes do compositor, mas seu hook ainda pode conflitar com BattlEye e deve ser mantido sob observacao.
- Leitura de memoria ou protocolo de rede seria rapida e estruturada, mas e fragil, depende de offsets/protocolo e aumenta muito o risco de deteccao.
- Uma placa de captura HDMI ou camera externa evita a protecao do Windows e oferece video de baixa latencia, mas exige hardware e continua sendo uma fonte visual.

## Retencao

O runtime integrado grava em `runtime\captures`, mantem no maximo 100 PNGs e remove a copia criada na pasta de screenshots do Tibia depois de uma copia bem-sucedida. Fixtures historicas em `movement\captures`, `autoloot\captures` e `internal_captures` nao entram nessa limpeza.
