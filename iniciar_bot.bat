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
echo Max moves: 30 ^| Segmento: 10 ^| Verifica a cada 2 ^| Autoloot: ON
echo.
python hunt_bot.py --max-moves 30 --segment-steps 10 --verify-every 2 --autoloot
echo.
echo ========================================
echo Bot finalizado.
echo ========================================
pause
