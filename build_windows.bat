@echo off
rem ==========================================================================
rem  Perennia - cria a versao para partilhar (Windows)
rem
rem  Faz duplo clique neste ficheiro. Demora uns minutos na primeira vez.
rem  No fim tens dist\Perennia-windows.zip: e esse que envias aos colegas.
rem  Eles so precisam de descompactar e abrir Perennia.exe.
rem ==========================================================================
setlocal
cd /d "%~dp0"
echo.
echo == Perennia: a criar o executavel para Windows ==
echo.

set PY=python
where py >nul 2>nul && set PY=py -3

if not exist .build-venv (
    echo [1/5] A criar um ambiente so para o build...
    %PY% -m venv .build-venv || goto :erro
)
call .build-venv\Scripts\activate.bat || goto :erro

echo [2/5] A instalar as bibliotecas e o PyInstaller...
python -m pip install --upgrade pip >nul || goto :erro
python -m pip install -r requirements.txt pyinstaller || goto :erro

echo [3/5] A confirmar que o nucleo funciona...
python main.py --self-test || goto :erro

echo [4/5] A empacotar...
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\perennia.spec || goto :erro
xcopy /E /I /Y gpx dist\Perennia\gpx >nul
xcopy /E /I /Y workouts dist\Perennia\workouts >nul
copy /Y packaging\LEIA-ME.txt dist\Perennia\LEIA-ME.txt >nul

echo [5/5] A criar o zip...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Perennia' -DestinationPath 'dist\Perennia-windows.zip' -Force" || goto :erro

echo.
echo Pronto!  dist\Perennia-windows.zip
echo Experimenta primeiro: dist\Perennia\Perennia.exe
echo.
pause
exit /b 0

:erro
echo.
echo O build falhou. Copia as mensagens acima e envia-as.
pause
exit /b 1
