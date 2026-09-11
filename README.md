# TibiaRIP

Diagnostico de captura e leitura visual do cliente oficial do Tibia no Windows.

Para arquitetura, testes reais, limitacoes e roteiro de continuidade, consulte [`HANDOFF.md`](HANDOFF.md).

As alternativas de captura, fontes estaticas do cliente e riscos de hooks/memoria estao documentados em [`CAPTURE_ALTERNATIVES.md`](CAPTURE_ALTERNATIVES.md).

## Resultado atual

- Janela encontrada: `Tibia - Rafaelkrosa`, classe Qt `Qt693QWindowIcon`.
- Renderizacao: GPU NVIDIA em engine `Graphics`; evidencias anteriores do Medal mostram swap chain D3D12.
- A janela usa `WindowDisplayAffinity = 0x1` (`WDA_MONITOR`). Por isso ela aparece no monitor fisico, mas fica preta para capturas comuns do Windows.
- `PrintWindow`, captura do desktop e WGC pelo monitor retornaram 100% preto com o Tibia em primeiro plano.
- WGC diretamente pela janela foi recusado ao criar o `GraphicsCaptureItem`.
- O NVIDIA Overlay tambem recusou a captura e registrou `Protected Content running` seguido de `Screenshot failed`.
- A captura interna do Tibia funciona e nao exige injecao. Depois de selecionar a interface inteira nas opcoes do jogo, ela inclui HUD, barras, inventario e mapa.
- O OBS Game Capture consegue obter o cliente antes do compositor. A Camera Virtual do OBS agora e a fonte primaria do bot; o screenshot interno ficou como fallback automatico.
- Validacao ao vivo em 11/09/2026: frame novo em cerca de 31 ms e ciclo completo de captura + Battle List + HP/mana + mapa em 1.30 s, contra aproximadamente 6.7 s no fluxo anterior.
- Captura de 10/09/2026 12:41: HP `315/315` e mana `870/870`, ambos 100%.

O Medal consegue capturar porque intercepta a swap chain D3D12 antes de a imagem passar pela exclusao do compositor. Tentar ler diretamente a VRAM de fora do processo nao resolve: a textura nao possui um handle compartilhado e o conteudo esta marcado como protegido. Isso normalmente exige um hook dentro do processo, como Medal ou OBS Game Capture, e pode entrar em conflito com o BattlEye.

## HP e mana

Os arquivos locais em `AppData\Local\Tibia` guardam configuracoes, hotkeys, sidebars e dados de analisadores. Eles nao persistem HP e mana atuais:

- `characterdata\...\statusBarData.json` guarda apenas estilo e visibilidade da barra.
- `conf\clientoptions.json` guarda as preferencias da interface.
- A arvore de acessibilidade do Qt expoe botoes e slots, mas nao os textos de HP/mana.
- Os valores dinamicos existem na memoria do cliente, mas procurar offsets nela e fragil e pode ser detectado pelo BattlEye. A solucao adotada aqui e leitura visual pelo OBS, com screenshot oficial como fallback, e OCR de pequenas regioes do HUD.

`read_status_bars.py` tambem mede as barras desenhadas sobre o personagem. Isso fornece percentual mesmo quando a captura esta configurada para mostrar somente o mapa; numeros exatos exigem a interface completa.

`read_battle_list.py` le as entradas visiveis da Battle List e procura, por padrao, `Amazon`, `Valkyrie` e `Witch`. O resultado inclui confianca do OCR e a coordenada do nome dentro do screenshot.

`monitor_tibia_audio.py` mede somente a sessao de audio cujo PID pertence a janela do Tibia, mas agora e apenas uma ferramenta de diagnostico separada. O controlador nao importa nem usa audio para decidir combate.

## Uso

Executar o controlador integrado de caca, com leitores paralelos, movimento verde, combate e autoloot mapeado:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\hunt_bot.py" --max-moves 30 --segment-steps 15 --verify-every 1
```

O modo padrao e `--capture-source auto`: tenta a Camera Virtual do OBS, valida o frame com os detectores e volta ao screenshot interno se a camera estiver parada ou o frame for invalido. Para exigir tempo real e abortar em vez de usar o fallback:

```powershell
python .\hunt_bot.py --capture-source obs
```

Para diagnostico ou para executar sem OBS:

```powershell
python .\hunt_bot.py --capture-source screenshot
```

O autoloot fica ativo por padrao. Para uma execucao sem loot:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\hunt_bot.py" --max-moves 30 --no-autoloot
```

Nao inicie os scripts de combate, loot e movimento separadamente ao mesmo tempo. `hunt_bot.py` executa os leitores em paralelo, mas mantem teclado e mouse sob um unico coordenador com prioridade `cura > combate > loot > movimento`.

## OBS

1. Adicione o Tibia como fonte `Game Capture`.
2. Mantenha a fonte centralizada com `Fit to screen`; nao use `Stretch to screen` nem crop manual.
3. Inicie `Start Virtual Camera` antes do bot. O canvas pode ser `1280x720` ou `1600x900`; o runtime normaliza para o tamanho real da area cliente.
4. Mantenha toda a interface, Battle List, minimapa e barras visiveis no frame.

O bot le a camera por FFmpeg/DirectShow e nunca acumula uma fila intencional de frames: cada decisao solicita um frame posterior a ultima acao. Use `--ffmpeg CAMINHO` ou `TIBIARIP_FFMPEG` se o executavel nao estiver no `PATH` nem no caminho local conhecido.

Capturar pelo proprio Tibia, copiar o PNG e ler HP/mana:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\capture_internal.py"
```

Ler novamente a captura mais recente:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\read_status_bars.py"
```

Ler a Battle List da captura mais recente:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\read_battle_list.py"
```

Monitorar apenas o audio do Tibia ate pressionar `Ctrl+C`:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\monitor_tibia_audio.py"
```

Repetir o comparativo de metodos de captura:

```powershell
& "C:\Users\bessa\AppData\Local\Programs\Python\Python310\python.exe" ".\capture_diagnostic.py" --focus --output ".\captures_focused"
```

## Configuracao do Tibia

Em `Options > Misc > Screenshots`, mantenha selecionada a opcao que inclui a interface inteira. A configuracao correspondente e `screnshotsOnlyGameWindow: false` em `conf\clientoptions.json`.

Nesta instalacao, `TakeScreenshot` esta associado a `Num *` quando o chat esta ativo. `capture_internal.py` executa `Enter`, `Num *`, `Enter`: ativa o chat, captura e retorna ao modo combate com Chat Off.

## Dependencias

```powershell
python -m pip install -r requirements.txt
```

O OCR numerico tambem usa `C:\Program Files\Tesseract-OCR\tesseract.exe`, ja instalado nesta maquina.

O stream do OBS requer FFmpeg. O executavel desta maquina e descoberto automaticamente; em outra instalacao, configure `TIBIARIP_FFMPEG` ou `--ffmpeg`.
