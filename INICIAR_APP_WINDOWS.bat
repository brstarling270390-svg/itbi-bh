@echo off
setlocal
cd /d "%~dp0"
title ITBI BH - Consulta de Transacoes

where py >nul 2>nul
if %errorlevel%==0 (
  set PYTHON=py
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set PYTHON=python
  ) else (
    echo.
    echo Python nao foi encontrado neste computador.
    echo Instale o Python 3.11 ou superior em https://www.python.org/downloads/
    echo Durante a instalacao, marque a opcao "Add Python to PATH".
    echo.
    pause
    exit /b 1
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo Preparando o ambiente na primeira execucao...
  %PYTHON% -m venv .venv
  if errorlevel 1 goto :erro
)

call ".venv\Scripts\activate.bat"
python -m pip install --disable-pip-version-check -q --upgrade pip
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :erro

python -m streamlit run app.py
exit /b 0

:erro
echo.
echo Nao foi possivel preparar o aplicativo. Verifique a conexao com a internet e tente novamente.
pause
exit /b 1
