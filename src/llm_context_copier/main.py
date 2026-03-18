import sys
import os
from pathlib import Path

def setup_streams_fallback():
    """
    Резервный механизм: перенаправляет stdout/stderr в лог-файлы,
    если они не определены. Используется, если не удалось прикрепиться к консоли.
    """
    log_dir = Path.home() / ".repo_copier_logs"
    if sys.stdout is None:
        log_dir.mkdir(exist_ok=True)
        sys.stdout = open(log_dir / "stdout.log", "a", encoding="utf-8")
    if sys.stderr is None:
        log_dir.mkdir(exist_ok=True)
        sys.stderr = open(log_dir / "stderr.log", "a", encoding="utf-8")

def run_gui():
    """Запускает графический интерфейс."""
    from PyQt6.QtWidgets import QApplication
    from llm_context_copier.gui import App
    
    app = QApplication(sys.argv)
    app.setOrganizationName("MyCompany")
    app.setApplicationName("RepoCopier")
    
    ex = App()
    ex.show()
    sys.exit(app.exec())

def main():
    # Если при запуске передан хотя бы один аргумент, кроме имени самого скрипта,
    # считаем, что пользователь хочет использовать CLI.
    if len(sys.argv) > 1:
        attach_and_run_cli()
    else:
        # Перед запуском GUI на всякий случай проверяем потоки,
        # т.к. его можно запустить из среды, где они не определены.
        setup_streams_fallback()
        run_gui()

def attach_and_run_cli():
    # ... logic for attaching to console ...
    # (keeping the existing logic, just shown as placeholder for brevity in tool call if needed, 
    # but I will provide the full replacement to be safe)
    cli_attached = False
    if sys.platform == "win32":
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8")
                sys.stderr = open("CONOUT$", "w", encoding="utf-8")
                cli_attached = True
        except (ImportError, OSError):
            pass

    if not cli_attached:
        setup_streams_fallback()

    from llm_context_copier.cli import main as cli_main
    cli_main()

if __name__ == '__main__':
    main()
