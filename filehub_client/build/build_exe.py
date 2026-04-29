#!/usr/bin/env python3
"""
Скрипт для сборки FileHubClient
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

PROJECT_NAME = "FileHubClient"
MAIN_SCRIPT = "client.py"

class BuildManager:
    def __init__(self):
        self.build_dir = Path(__file__).parent
        self.project_root = self.build_dir.parent
        self.dist_dir = self.project_root / "dist"
        
        print(f"Build dir: {self.build_dir}")
        print(f"Project root: {self.project_root}")
        print(f"Dist dir: {self.dist_dir}")
        
    def clean(self):
        """Очистка"""
        print("\n[1/3] Cleaning...")
        
        if self.dist_dir.exists():
            shutil.rmtree(self.dist_dir)
            print(f"  Removed {self.dist_dir}")
        
        # Clean pyinstaller cache
        cache_dir = Path.home() / "AppData" / "Local" / "pyinstaller"
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            print(f"  Removed cache")
        
        # Remove build temp
        temp_dir = self.build_dir / "temp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            print(f"  Removed {temp_dir}")
        
        # Remove spec files
        for spec in self.build_dir.glob("*.spec"):
            spec.unlink()
            print(f"  Removed {spec}")
            
        print("  Done")
    
    def build(self):
        """Сборка"""
        print("\n[2/3] Running PyInstaller...")
        
        os.chdir(self.project_root)
        
        # Простая команда без лишних опций
        cmd = [
            sys.executable, '-m', 'PyInstaller',
            '--name', PROJECT_NAME,
            '--onedir',
            '--console',
            '--clean',
            '--noconfirm',
            '--distpath', str(self.dist_dir),
            '--workpath', str(self.build_dir / 'temp'),
            '--specpath', str(self.build_dir),
            MAIN_SCRIPT
        ]
        
        print(f"\nCommand: {' '.join(cmd)}\n")
        
        # Запускаем с выводом в реальном времени
        process = subprocess.Popen(
            cmd,
            stdout=None,  # Выводим напрямую в консоль
            stderr=None,
            text=True
        )
        
        process.wait()
        
        if process.returncode == 0:
            print("\n  ✓ PyInstaller completed successfully")
            return True
        else:
            print(f"\n  ✗ PyInstaller failed with code {process.returncode}")
            return False
    
    def copy_files(self):
        """Копирование файлов"""
        print("\n[3/3] Copying additional files...")
        
        output_dir = self.dist_dir / PROJECT_NAME
        
        # Copy config
        config_src = self.project_root / "client.conf"
        config_dst = output_dir / "client.conf"
        if config_src.exists():
            shutil.copy2(config_src, config_dst)
            print(f"  Copied client.conf")
        
        # Create directories
        for dir_name in ['downloads', 'my_shares']:
            dir_path = output_dir / dir_name
            dir_path.mkdir(exist_ok=True)
            print(f"  Created {dir_name}/")
        
        print("  Done")
        
        # Show result
        exe_path = output_dir / f"{PROJECT_NAME}.exe"
        if exe_path.exists():
            size = exe_path.stat().st_size / 1024 / 1024
            print(f"\n✅ SUCCESS!")
            print(f"   Executable: {exe_path}")
            print(f"   Size: {size:.2f} MB")
            print(f"   Output dir: {output_dir}")
        else:
            print(f"\n❌ FAILED: {exe_path} not found")

def main():
    manager = BuildManager()
    
    if len(sys.argv) > 1 and sys.argv[1] == 'clean':
        manager.clean()
        return
    
    manager.clean()
    if manager.build():
        manager.copy_files()
    else:
        print("\n❌ BUILD FAILED!")
        sys.exit(1)

if __name__ == '__main__':
    main()