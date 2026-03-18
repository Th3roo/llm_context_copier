import fnmatch
from pathlib import Path
from gitignore_parser import parse_gitignore

def get_gitignore_matcher(base_path: Path):
    """
    Создает функцию-матчер на основе правил из файла .gitignore.
    """
    gitignore_path = base_path / '.gitignore'
    if gitignore_path.is_file():
        try:
            return parse_gitignore(gitignore_path, base_path)
        except Exception as e:
            print(f"Warning: Could not parse .gitignore file: {e}")
    return lambda p: False


def get_gitattributes_matcher(base_path: Path):
    """
    Создает функцию-матчер на основе правил linguist-* из .gitattributes.
    """
    gitattributes_path = base_path / '.gitattributes'
    if not gitattributes_path.is_file():
        return lambda p: False

    rules = []
    try:
        with open(gitattributes_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                pattern = parts[0]
                attributes = parts[1:]
                is_ignore_rule = None
                for attr in attributes:
                    if attr in ("linguist-generated", "linguist-generated=true", "linguist-vendored", "linguist-vendored=true"):
                        is_ignore_rule = True
                    elif attr in ("-linguist-generated", "linguist-generated=false", "-linguist-vendored", "linguist-vendored=false"):
                        is_ignore_rule = False
                if is_ignore_rule is not None:
                    rules.append((pattern, is_ignore_rule))
    except Exception as e:
        print(f"Warning: Could not parse .gitattributes file: {e}")
        return lambda p: False

    if not rules:
        return lambda p: False

    def matcher(file_path: Path) -> bool:
        try:
            if file_path.is_absolute():
                relative_path_str = str(file_path.relative_to(base_path).as_posix())
            else:
                relative_path_str = str(file_path.as_posix())
        except ValueError:
            return False

        last_match = None
        for pattern, is_ignore in rules:
            match = False
            if fnmatch.fnmatch(relative_path_str, pattern):
                match = True
            elif fnmatch.fnmatch(relative_path_str, f"{pattern}/**"):
                match = True
            elif pattern.endswith('/') and relative_path_str.startswith(pattern):
                match = True
            if match:
                last_match = is_ignore
        return last_match if last_match is not None else False
    return matcher


def get_project_structure(root_path: Path, ignored_patterns: list, gitignore_matcher, gitattributes_matcher) -> str:
    """
    Строит строковое представление дерева проекта.
    """
    tree_lines = []

    def recurse(current_path: Path, prefix: str = ""):
        if gitignore_matcher(current_path) or gitattributes_matcher(current_path) or any(part in ignored_patterns for part in current_path.relative_to(root_path).parts):
            return
        try:
            items = sorted(list(current_path.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
        except (OSError, PermissionError):
            return

        valid_items = [item for item in items if not (item.name in ignored_patterns or gitignore_matcher(item) or gitattributes_matcher(item))]
        for i, item in enumerate(valid_items):
            is_last = i == (len(valid_items) - 1)
            connector = "└── " if is_last else "├── "
            tree_lines.append(f"{prefix}{connector}{item.name}")
            if item.is_dir():
                new_prefix = prefix + ("    " if is_last else "│   ")
                recurse(item, new_prefix)

    tree_lines.append(f"{root_path.name}")
    recurse(root_path)
    return "\n".join(tree_lines)
