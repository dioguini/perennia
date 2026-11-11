@echo off
rem ==========================================================================
rem  Perennia - cria o atalho "Perennia" no Ambiente de trabalho (Windows).
rem
rem  Duplo clique. O atalho abre a aplicacao com o icone da Perennia, sem
rem  consola e sem PyCharm. Se ja fizeste o build (dist\Perennia\Perennia.exe),
rem  o atalho aponta para esse executavel; senao, para o ambiente do projeto.
rem  Depois podes fixa-lo na barra de tarefas (botao direito no atalho).
rem ==========================================================================
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "packaging\criar_atalho.ps1"
echo.
pause
