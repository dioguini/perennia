@echo off
rem ==========================================================================
rem  Perennia - abre a aplicacao SEM o PyCharm (Windows).
rem
rem  Duplo clique neste ficheiro. Usa o ambiente virtual do projeto (.venv ou
rem  venv) e abre sem a janela preta da consola. Se algo correr mal, o erro
rem  fica em perennia-erro.log, na pasta dos dados (data\, aqui ao lado).
rem ==========================================================================
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" goto venv1
if exist "venv\Scripts\pythonw.exe" goto venv2
where pyw >nul 2>nul
if %errorlevel%==0 goto pyw
goto semvenv

:venv1
start "" ".venv\Scripts\pythonw.exe" main.py %*
exit /b 0

:venv2
start "" "venv\Scripts\pythonw.exe" main.py %*
exit /b 0

:pyw
start "" pyw -3 main.py %*
exit /b 0

:semvenv
echo.
echo Nao encontrei o ambiente virtual do projeto (.venv).
echo Corre primeiro o perennia_setup.bat (cria-o e prepara tudo), ou cria-o a mao:
echo     python -m venv .venv
echo     .venv\Scripts\python -m pip install -r requirements.txt
echo.
pause
exit /b 1
