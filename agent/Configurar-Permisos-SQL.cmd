@echo off
setlocal EnableExtensions
title Permisos de backup SQL - Data Express Agent
cd /d "%~dp0"

if not exist "%~dp0installer\Grant-BackupPermissions.ps1" (
    echo ERROR: no se encontro installer\Grant-BackupPermissions.ps1. Extraiga todo el ZIP.
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

echo Ejecute esto en el servidor de SQL Server donde esta instalado el agente.
echo Necesita un usuario de Windows que sea sysadmin en SQL Server.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Grant-BackupPermissions.ps1"
set "RESULT=%errorlevel%"
echo.
if not "%RESULT%"=="0" (
    echo ERROR: no se aplicaron todos los permisos. Revise el detalle de arriba.
    pause
    exit /b %RESULT%
)
echo LISTO.
pause
exit /b 0
