@echo off
echo === Tarcker Setup (Windows) ===

REM Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado. Instale em https://python.org
    pause
    exit /b 1
)

REM Instalar dependencias
echo Instalando dependencias...
pip install pywin32 psutil plyer

REM Gerar config padrao
echo Criando configuracao padrao...
python -c "from tarcker.config import load_config, CONFIG_FILE; load_config(); print('Config em:', CONFIG_FILE)"

echo.
echo === Pronto! ===
echo Para iniciar o monitor: python main.py
echo Para ver o resumo agora: python main.py --summary
echo.
pause
