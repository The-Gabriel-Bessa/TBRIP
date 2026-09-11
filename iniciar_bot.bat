@echo off
title TibiaRIP - Hunt Bot
cd /d "%~dp0"

echo ========================================
echo   TibiaRIP - Hunt Bot
echo ========================================
echo.
echo Verificando dependencias...
python -c "import comtypes, pycaw, cv2, numpy, PIL, pytesseract" 2>nul
if errorlevel 1 (
    echo Instalando dependencias...
    pip install comtypes pycaw opencv-python numpy Pillow pytesseract
)
echo.
echo Iniciando bot...
echo Max moves: 30 ^| Segmento: 10 ^| Verifica a cada passo ^| Autoloot: ON
echo Heal: 90%% ^| Emergencia F1: 300HP ^| Recuo: 4 inimigos
echo.
python hunt_bot.py --max-moves 30 --segment-steps 10 --verify-every 1 --autoloot --heal-below 90 --emergency-hp 300 --retreat-enemies 4 %*
echo.
echo ========================================
echo Bot finalizado.
echo ========================================
pause
