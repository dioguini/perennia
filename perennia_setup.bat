@echo off
rem ==========================================================================
rem  Perennia - instalacao num computador novo (Windows).
rem
rem  Duplo clique. Cria o ambiente virtual (.venv), instala os requisitos e
rem  corre "main.py --setup": a pasta data\ com a base de dados (treinos de
rem  base, exercicios do ginasio, metricas...), os ficheiros modelo, o
rem  autoteste e, se quiseres, o GarminDB e o atalho no Ambiente de trabalho.
rem  Pode correr-se outra vez: o que ja existe fica como esta.
rem  Precisa do Python 3.11+ (https://www.python.org/downloads/ - marca
rem  "Add python.exe to PATH" na instalacao).
rem ==========================================================================
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto semPython

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto pythonAntigo

if exist ".venv\Scripts\python.exe" goto requisitos
echo A criar o ambiente virtual (.venv)...
%PY% -m venv .venv
if errorlevel 1 goto falhou

:requisitos
echo A instalar os requisitos (requirements.txt)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto falhou

".venv\Scripts\python.exe" main.py --setup %*
set "RC=%errorlevel%"
echo.
pause
exit /b %RC%

:semPython
echo.
echo Nao encontrei o Python. Instala-o de https://www.python.org/downloads/
echo (marca "Add python.exe to PATH") e corre este ficheiro outra vez.
echo.
pause
exit /b 1

:pythonAntigo
echo.
echo O Python nao respondeu ou e antigo: a Perennia precisa do 3.11 ou mais
echo recente (https://www.python.org/downloads/).
echo.
pause
exit /b 1

:falhou
echo.
echo Algo falhou (ve a mensagem acima). Corrige e corre este ficheiro outra vez.
echo.
pause
exit /b 1
