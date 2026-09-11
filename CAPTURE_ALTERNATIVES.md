# Alternativas aos screenshots

## Situacao atual

O cliente usa `WindowDisplayAffinity = WDA_MONITOR` e conteudo protegido. Neste computador, `PrintWindow`, captura do desktop, Windows Graphics Capture, NVIDIA Overlay e captura do monitor ja retornaram preto ou foram recusados.

O screenshot interno nao e a unica alternativa tecnicamente possivel, mas e a unica fonte completa ja comprovada que:

- nao injeta codigo no cliente;
- mostra gameplay, minimapa, Battle List, HP/mana e Loot Log;
- funciona com a protecao atual.

## Fontes que podem reduzir screenshots

O cliente possui centenas de arquivos `assets\minimap-*.bmp.lzma`, alem de `map-*.dat` e `staticmapdata-*.dat`. Eles podem fornecer terreno estatico depois que a cave local for alinhada ao mapa oficial. Eles nao informam posicao atual, criaturas, HP/mana, corpos ou se um movimento falhou.

O melhor caminho e hibrido:

1. Usar mapa estatico e a referencia persistente para planejar.
2. Atualizar a posicao prevista pelas teclas enviadas.
3. Usar audio para solicitar leitura imediata em caso de atividade.
4. Capturar periodicamente para corrigir posicao e ler estado dinamico.

Depois de mais validacao, e possivel confirmar a cada dois ou tres passos em corredores conhecidos, em vez de um screenshot por tile. Isso reduz latencia, mas aumenta o intervalo ate detectar um bloqueio ou inimigo sem som.

## Alternativas que nao resolvem o estado vivo

- APIs web do Tibia fornecem dados publicos de personagem e mundo, nao telemetria em tempo real da sessao.
- GitHub pode fornecer parsers e formatos conhecidos, mas nao acesso privilegiado ao cliente em execucao.
- UI Automation do Qt expoe controles, mas nao o estado renderizado da gameplay.
- Arquivos JSON locais guardam configuracoes e historicos de analisadores, nao posicao e HP atuais.
- NVIDIA Video Codec SDK codifica frames que ja foram adquiridos; ele nao ignora por si so a protecao de captura.

## Alternativas tecnicas nao adotadas

- OBS Game Capture e hooks Direct3D podem capturar antes do compositor, mas injetam codigo no processo e podem conflitar com BattlEye.
- Leitura de memoria ou protocolo de rede seria rapida e estruturada, mas e fragil, depende de offsets/protocolo e aumenta muito o risco de deteccao.
- Uma placa de captura HDMI ou camera externa evita a protecao do Windows e oferece video de baixa latencia, mas exige hardware e continua sendo uma fonte visual.

## Retencao

O runtime integrado grava em `runtime\captures`, mantem no maximo 100 PNGs e remove a copia criada na pasta de screenshots do Tibia depois de uma copia bem-sucedida. Fixtures historicas em `movement\captures`, `autoloot\captures` e `internal_captures` nao entram nessa limpeza.
