@echo off
setlocal EnableDelayedExpansion
title Tarcker — Instalacao

echo ======================================================
echo   Tarcker — Instalacao (Windows)
echo   Diretorio: %~dp0
echo ======================================================
echo.

:: ------------------------------------------------------------------
:: 1. Verificar Python
:: ------------------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado.
    echo Baixe em: https://www.python.org/downloads/
    pause & exit /b 1
)

:: Localizar pythonw.exe (mesmo diretorio do python.exe)
for /f "delims=" %%i in ('where python') do set PYTHON_EXE=%%i & goto :found_python
:found_python
set PYTHONW_EXE=%PYTHON_EXE:python.exe=pythonw.exe%
if not exist "%PYTHONW_EXE%" set PYTHONW_EXE=%PYTHON_EXE%

echo Python  : %PYTHON_EXE%
echo Pythonw : %PYTHONW_EXE%
echo.

:: ------------------------------------------------------------------
:: 2. Instalar dependencias Python
:: ------------------------------------------------------------------
echo Instalando dependencias Python...
pip install --quiet --upgrade pip
pip install --quiet pywin32 psutil pynput Pillow plyer pystray
if errorlevel 1 (
    echo ERRO ao instalar dependencias.
    pause & exit /b 1
)
echo   OK.
echo.

:: ------------------------------------------------------------------
:: 3. Criar config padrao
:: ------------------------------------------------------------------
echo Criando configuracao padrao...
python -c "from tarcker.config import load_config, CONFIG_FILE; load_config(); print('  Config em:', CONFIG_FILE)"
echo.

:: ------------------------------------------------------------------
:: 4. Registrar no Agendador de Tarefas do Windows
::    - Dispara no logon do usuario atual
::    - Usa pythonw.exe (sem janela de terminal)
::    - Nao precisa de admin
:: ------------------------------------------------------------------
set TASK_NAME=Tarcker
set WORK_DIR=%~dp0
:: Remove trailing backslash
if "%WORK_DIR:~-1%"=="\" set WORK_DIR=%WORK_DIR:~0,-1%
set MAIN_PY=%WORK_DIR%\main.py
set LOG_FILE=%USERPROFILE%\.tarcker\tarcker.log

echo Registrando no Agendador de Tarefas...

:: Remover tarefa anterior se existir
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: Criar nova tarefa: roda no logon, sem janela, com atraso de 30s para aguardar sessao
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%PYTHONW_EXE%\" \"%MAIN_PY%\" --no-log" ^
  /sc ONLOGON ^
  /delay 0000:30 ^
  /ru "%USERNAME%" ^
  /f >nul

if errorlevel 1 (
    echo ERRO ao registrar tarefa. Tente executar como Administrador.
    goto :manual_startup
)
echo   Tarefa registrada: iniciara automaticamente ao fazer login.
echo   Logs em: %LOG_FILE%
goto :after_startup

:manual_startup
echo.
echo Alternativa: atalho na pasta Inicializacao...
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set VBS_FILE=%STARTUP_DIR%\tarcker.vbs

(
echo Set WshShell = CreateObject("WScript.Shell"^)
echo WshShell.Run """%PYTHONW_EXE%"" ""%MAIN_PY%"" --no-log", 0, False
) > "%VBS_FILE%"
echo   Atalho criado em: %VBS_FILE%
echo   O Tarcker iniciara automaticamente no proximo login.

:after_startup
echo.

:: ------------------------------------------------------------------
:: 5. Iniciar agora (em background, sem janela)
:: ------------------------------------------------------------------
set /p START_NOW="Iniciar o Tarcker agora? [S/n]: "
if /i "%START_NOW%"=="" set START_NOW=S
if /i "%START_NOW%"=="S" (
    echo Iniciando em background...
    :: Verifica se ja esta rodando
    tasklist /fi "imagename eq pythonw.exe" 2>nul | find /i "pythonw" >nul
    if not errorlevel 1 (
        echo   Aviso: pythonw.exe ja esta rodando. Pode ja estar ativo.
    )
    start "" /b "%PYTHONW_EXE%" "%MAIN_PY%" --no-log
    timeout /t 3 /nobreak >nul
    tasklist /fi "imagename eq pythonw.exe" 2>nul | find /i "pythonw" >nul
    if not errorlevel 1 (
        echo   OK - Tarcker rodando em background!
    ) else (
        echo   Iniciando via python.exe como fallback...
        start "" /min python "%MAIN_PY%" --no-log
    )
)

echo.
echo ======================================================
echo   Instalacao concluida!
echo.
echo   Comandos uteis:
echo     Ver resumo de hoje  : python main.py --summary
echo     Parar o Tarcker     : taskkill /im pythonw.exe /f
echo     Ver tarefas Windows : schtasks /query /tn Tarcker
echo     Remover da inicializ: schtasks /delete /tn Tarcker /f
echo ======================================================
echo.
pause
