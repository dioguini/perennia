@echo off
rem ==========================================================================
rem  Perennia - instalacao num computador novo (Windows).
rem
rem  Duplo clique. Cria o ambiente virtual (.venv), instala os requisitos e
rem  corre "main.py --setup": a pasta data\ com a base de dados (treinos de
rem  base, exercicios do ginasio, metricas...), os ficheiros modelo, o
rem  autoteste e, se quiseres, o GarminDB e o atalho no Ambiente de trabalho.
rem  Pode correr-se outra vez: o que ja existe fica como esta.
rem
rem  Python: usa o 3.13 (ou o 3.12 / 3.14). A Perennia precisa do 3.11+;
rem  o GarminDB precisa do 3.12+ (https://www.python.org/downloads/ - marca
rem  "Add python.exe to PATH"). Se o .venv for de um Python antigo e houver
rem  um 3.12+, o antigo fica guardado em .venv-antigo e cria-se um novo.
rem ==========================================================================
setlocal
cd /d "%~dp0"
set "CHK=import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
set "CHK11=import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"

set "PY="
rem  o 3.13 primeiro (o testado); o py do "Python install manager" e, se o py
rem  antigo se sobrepuser, o python3.X.exe que ele poe em %LocalAppData%\Python\bin
for %%V in (3.13 3.12 3.14) do (
  if not defined PY (
    py -%%V -c "%CHK%" >nul 2>nul && set "PY=py -%%V"
  )
  if not defined PY if exist "%LocalAppData%\Python\bin\python%%V.exe" (
    "%LocalAppData%\Python\bin\python%%V.exe" -c "%CHK%" >nul 2>nul && set "PY="%LocalAppData%\Python\bin\python%%V.exe""
  )
)
if not defined PY (
  python -c "%CHK%" >nul 2>nul && set "PY=python"
)
set "OLDPY="
if not defined PY (
  py -3 -c "%CHK11%" >nul 2>nul && set "PY=py -3" && set "OLDPY=1"
)
if not defined PY (
  python -c "%CHK11%" >nul 2>nul && set "PY=python" && set "OLDPY=1"
)
if not defined PY goto semPython
if defined OLDPY (
  echo Aviso: so encontrei um Python 3.11. A Perennia funciona, mas o GarminDB
  echo precisa do Python 3.12 ou mais recente ^(https://www.python.org/downloads/^).
)

if not exist ".venv\Scripts\python.exe" goto criar
if defined OLDPY goto requisitos
".venv\Scripts\python.exe" -c "%CHK%" >nul 2>nul
if not errorlevel 1 goto requisitos
echo O .venv usa um Python antigo; passo para um 3.12+ ^(o GarminDB precisa dele^).
echo O antigo fica guardado em .venv-antigo.
if exist ".venv-antigo" rmdir /s /q ".venv-antigo"
move ".venv" ".venv-antigo" >nul
if errorlevel 1 goto falhou

:criar
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
echo Nao encontrei o Python 3.11+ (recomendado: 3.12 ou mais recente).
echo Instala-o de https://www.python.org/downloads/ (marca "Add python.exe to
echo PATH") e corre este ficheiro outra vez.
echo.
pause
exit /b 1

:falhou
echo.
echo Algo falhou (ve a mensagem acima). Corrige e corre este ficheiro outra vez.
echo.
pause
exit /b 1
