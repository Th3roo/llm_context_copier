import argparse
import json
import sys
from pathlib import Path
import pyperclip
from .context_generator import create_llm_context

def progress_callback(message):
    """Простой колбэк для вывода прогресса в консоль."""
    print(message, file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(
        description="Собирает контекст проекта для LLM из командной строки.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "repo_path",
        help="Путь к папке проекта."
    )
    parser.add_argument(
        "-c", "--config",
        default="config.json",
        help="Путь к файлу конфигурации JSON. (по умолчанию: config.json)"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Путь к файлу для сохранения вывода. Если не указан, вывод будет скопирован в буфер обмена и напечатан в stdout."
    )
    parser.add_argument(
        "--no-clipboard",
        action="store_true",
        help="Не копировать вывод в буфер обмена."
    )
    parser.add_argument(
        '--include-ext', nargs='*', help='Переопределить расширения для включения (через пробел).'
    )
    parser.add_argument(
        '--include-files', nargs='*', help='Переопределить файлы для включения по имени.'
    )
    parser.add_argument(
        '--exclude-folders', nargs='*', help='Переопределить папки для исключения.'
    )
    parser.add_argument(
        '--exclude-files', nargs='*', help='Переопределить файлы для исключения по имени.'
    )
    parser.add_argument(
        '--exclude-ext', nargs='*', help='Переопределить расширения для исключения.'
    )
    parser.add_argument(
        '--no-tree', action='store_false', dest='include_tree', help='Не включать дерево проекта.'
    )
    parser.add_argument(
        '--max-chars', type=int, help='Переопределить лимит символов на файл.'
    )

    args = parser.parse_args()

    # --- Загрузка конфигурации ---
    config = {
        "include_ext": [],
        "include_files": [],
        "exclude_folders": [],
        "exclude_files": [],
        "exclude_ext": [],
        "include_tree": True,
        "max_chars_per_file": 100000
    }

    config_path = Path(args.config)
    if config_path.is_file():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config.update(json.load(f))
            progress_callback(f"ℹ️  Конфигурация загружена из {config_path}")
        except json.JSONDecodeError as e:
            print(f"❌ Ошибка парсинга JSON в {config_path}: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.config != "config.json":
        # Если пользователь указал кастомный путь и он не найден
        print(f"⚠️  Файл конфигурации не найден по пути: {args.config}", file=sys.stderr)


    # --- Переопределение из аргументов командной строки ---
    if args.include_ext is not None: config['include_ext'] = args.include_ext
    if args.include_files is not None: config['include_files'] = args.include_files
    if args.exclude_folders is not None: config['exclude_folders'] = args.exclude_folders
    if args.exclude_files is not None: config['exclude_files'] = args.exclude_files
    if args.exclude_ext is not None: config['exclude_ext'] = args.exclude_ext
    if args.max_chars is not None: config['max_chars_per_file'] = args.max_chars
    # Действие 'store_false' для no-tree само обновит args.include_tree
    config['include_tree'] = args.include_tree


    try:
        progress_callback("🚀 Запускаю сборку контекста...")
        result = create_llm_context(
            repo_path_str=args.repo_path,
            include_ext=config['include_ext'],
            include_files=config['include_files'],
            exclude_folders=config['exclude_folders'],
            exclude_files=config['exclude_files'],
            exclude_ext=config['exclude_ext'],
            include_tree=config['include_tree'],
            max_chars_per_file=config['max_chars_per_file'],
            progress_callback=progress_callback
        )

        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(result)
            progress_callback(f"✅ Результат сохранен в файл: {output_path}")
        else:
            print(result)

        if not args.no_clipboard and not args.output:
            pyperclip.copy(result)
            progress_callback("✅ Результат скопирован в буфер обмена.")

        progress_callback("🎉 Готово!")

    except FileNotFoundError as e:
        print(f"❌ Ошибка: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Произошла непредвиденная ошибка: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
