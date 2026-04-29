@echo off
chcp 65001 >nul
title FileHub Builder

echo ========================================
echo    FileHub Client Builder
echo ========================================
echo.

cd /d "%~dp0.."
echo Project: %CD%
echo.

python --version
echo.

cd build

echo Starting build...
echo.
python build_exe.py

if errorlevel 1 (
    echo.
    echo ========================================
    echo    BUILD FAILED!
    echo ========================================
    pause
    exit /b 1
)

echo.
echo ========================================
echo    BUILD COMPLETE!
echo ========================================
timeout /t 3 >nul