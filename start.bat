@echo off
title Infra Platform

echo Arrancando Backend...
start "Backend" cmd /k "cd /d "%~dp0backend" && python dev_server.py"

echo Arrancando Frontend...
start "Frontend" cmd /k "cd /d "%~dp0frontend" && npm start"

echo Listo. Abre http://localhost:3000
