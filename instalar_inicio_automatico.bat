@echo off
REM Faz o Clipador ligar sozinho quando voce entrar no Windows (sem janela aberta).
cd /d "%~dp0"
set PASTA=%~dp0
set ATALHO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Clipador.vbs
> "%ATALHO%" echo Set s = CreateObject("WScript.Shell")
>> "%ATALHO%" echo s.Run """%PASTA%iniciar_clipador.bat""", 0, False
echo Pronto. O Clipador vai ligar sozinho toda vez que o Windows iniciar.
echo Para ligar agora sem reiniciar, de dois cliques em "%ATALHO%".
echo Para desligar o inicio automatico, apague esse arquivo.
pause
