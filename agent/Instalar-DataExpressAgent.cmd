@echo off
setlocal EnableExtensions
title Instalador de Data Express Agent
cd /d "%~dp0"

if not exist "%~dp0installer\Install-DataExpressAgent.ps1" (
    echo ERROR: no se encontro el instalador. Extraiga todo el ZIP.
    pause
    exit /b 2
)

fltmc >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Solicitando permisos de administrador...
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    if not "%errorlevel%"=="0" exit /b 3
    exit /b 0
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Install-DataExpressAgent.ps1"
set "INSTALL_RESULT=%errorlevel%"
if not "%INSTALL_RESULT%"=="0" (
    echo ERROR: la instalacion no pudo completarse.
    pause
    exit /b %INSTALL_RESULT%
)

echo LISTO: el agente confirmo su vinculacion con Data Express.
pause
exit /b 0
