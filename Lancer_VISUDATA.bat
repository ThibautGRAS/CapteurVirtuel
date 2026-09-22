@echo off
setlocal
cd /d "%~dp0"
title VISUDATA - serveur local

rem ---------------------------------------------------------------------------
rem  VISUDATA doit etre servi par un petit serveur HTTP local : les modules ES
rem  et le noyau WebAssembly (lecture STEP) sont bloques par le navigateur si
rem  la page est ouverte directement en file:// .
rem  Ce script demarre un serveur sur 127.0.0.1 puis ouvre le navigateur.
rem ---------------------------------------------------------------------------

set PORT=8765

set PY=
where py >nul 2>nul && set PY=py -3
if "%PY%"=="" ( where python >nul 2>nul && set PY=python )

if "%PY%"=="" (
  echo.
  echo   [ERREUR] Python n'a pas ete trouve sur ce poste.
  echo   Autres possibilites :
  echo     - installer Python ^(https://www.python.org^)
  echo     - ou servir ce dossier avec n'importe quel serveur HTTP local
  echo       ^(ex. extension "Live Server" de VS Code^)
  echo.
  pause
  exit /b 1
)

echo.
echo   VISUDATA  -  http://localhost:%PORT%/
echo   Laissez cette fenetre ouverte pendant l'utilisation.
echo   Fermez-la ^(ou Ctrl+C^) pour arreter le serveur.
echo.

start "" http://localhost:%PORT%/index.html
%PY% serveur.py %PORT%
if errorlevel 1 pause
