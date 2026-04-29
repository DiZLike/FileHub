@echo off
chcp 65001 >nul
echo ===========================================
echo            GIT SYNC SCRIPT
echo ===========================================
echo.

echo [ШАГ 1/4] Проверка статуса репозитория...
git status
echo.
set /p confirm_status="Продолжить добавление файлов? (y/n): "
if /i not "%confirm_status%"=="y" (
    echo Операция отменена.
    pause
    exit /b
)

echo.
echo [ШАГ 2/4] Добавление всех измененных файлов...
git add .
echo Файлы добавлены.
echo.

echo [ШАГ 3/4] Создание коммита...
set /p confirm_commit="Подтвердить коммит с сообщением 'Sync'? (y/n): "
if /i not "%confirm_commit%"=="y" (
    echo Операция отменена.
    pause
    exit /b
)
git commit -m "Sync"
echo.

echo [ШАГ 4/4] Отправка изменений на сервер...
set /p confirm_push="Подтвердить push? (y/n): "
if /i not "%confirm_push%"=="y" (
    echo Операция отменена.
    pause
    exit /b
)
git push
echo.

echo ===========================================
echo            ГОТОВО!
echo ===========================================
pause