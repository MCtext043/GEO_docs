@echo off
setlocal
cd /d "%~dp0"

REM PyInstaller не может удалить dist\NormDocsLangflow, пока запущен .exe из неё.
taskkill /IM NormDocsLangflow.exe /F >nul 2>&1

timeout /t 2 /nobreak >nul

if exist ".venv\Scripts\pyinstaller.exe" (
  .venv\Scripts\pyinstaller.exe build_normdocs_exe.spec --noconfirm
) else (
  python -m PyInstaller build_normdocs_exe.spec --noconfirm
)
if errorlevel 1 (
  echo.
  echo Если снова "Отказано в доступе": закройте NormDocsLangflow.exe, окно Проводника
  echo в dist\NormDocsLangflow и повторите. Иногда помогает перезагрузка или исключение
  echo папки проекта из проверки антивируса в реальном времени.
  echo.
  echo Если ошибка про пакет typing: используйте venv проекта (.venv) или удалите backport typing из глобального Python.
  pause
  exit /b 1
)

echo Сборка завершена: dist\NormDocsLangflow\NormDocsLangflow.exe
