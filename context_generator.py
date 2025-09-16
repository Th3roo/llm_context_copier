from pathlib import Path
from file_utils import get_gitignore_matcher, get_gitattributes_matcher, get_project_structure

# --- КОНФИГУРАЦИЯ ---
DEFAULT_IGNORE_PATTERNS = [
    ".git", ".svn", ".hg", "venv", ".venv", "env", "ENV",
    "__pycache__", "*.pyc", ".pytest_cache", ".mypy_cache",
    ".vscode", ".idea", "*.swp", "node_modules", "dist",
    "build", "target", "out", ".env", "*.log", "*.lock",
]
# --- КОНЕЦ КОНФИГУРАЦИИ ---

def create_llm_context(
    repo_path_str: str, include_ext: list, include_files: list,
    exclude_folders: list, exclude_files: list, exclude_ext: list,
    include_tree: bool, max_chars_per_file: int, progress_callback
) -> str:
    """
    Собирает контекст из репозитория для LLM.
    """
    def send_progress(message):
        """Отправляет сообщение о прогрессе, поддерживая и сигналы PyQt, и обычные функции."""
        if hasattr(progress_callback, 'emit'):
            progress_callback.emit(message)
        else:
            progress_callback(message)

    repo_path = Path(repo_path_str).resolve()
    if not repo_path.is_dir():
        raise FileNotFoundError(f"Directory not found: {repo_path}")

    send_progress("- Parsing .gitignore...")
    gitignore_matcher = get_gitignore_matcher(repo_path)
    send_progress("- Parsing .gitattributes...")
    gitattributes_matcher = get_gitattributes_matcher(repo_path)
    
    all_excluded_folders = DEFAULT_IGNORE_PATTERNS + exclude_folders
    output_parts = []
    
    if include_tree:
        send_progress("- Building project tree...")
        tree_structure = get_project_structure(repo_path, all_excluded_folders, gitignore_matcher, gitattributes_matcher)
        output_parts.append("Project file structure:\n=======================\n```\n" + tree_structure + "\n```\n")

    output_parts.append("File contents:\n==============")
    send_progress("- Finding files...")
    files_to_process_set = set()
    for ext in include_ext:
        if ext and not ext.startswith('.'):
            ext = '.' + ext
        if ext:
            files_to_process_set.update(repo_path.rglob(f'*{ext}'))
    for filename in include_files:
        if filename:
            files_to_process_set.update(repo_path.rglob(filename))

    final_file_list = []
    for file_path in sorted(list(files_to_process_set)):
        if not file_path.is_file():
            continue
        if gitignore_matcher(file_path):
            continue
        if gitattributes_matcher(file_path):
            continue
        if any(folder in all_excluded_folders for folder in file_path.relative_to(repo_path).parts):
            continue
        if file_path.name in exclude_files:
            continue
        if file_path.suffix in exclude_ext:
            continue
        final_file_list.append(file_path)

    total_files = len(final_file_list)
    for i, file_path in enumerate(final_file_list):
        relative_path_str = str(file_path.relative_to(repo_path))
        send_progress(f"({i+1}/{total_files}) 📄 {relative_path_str}")
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(max_chars_per_file + 1)
            truncated = False
            if len(content) > max_chars_per_file:
                content, truncated = content[:max_chars_per_file], True
            lang = file_path.suffix.lstrip('.') if file_path.suffix else 'text'
            output_parts.append(f"--- START OF FILE: {relative_path_str} ---")
            output_parts.append(f"```{lang}\n{content.strip()}")
            if truncated:
                output_parts.append("\n\n[... content truncated due to size limit ...]")
            output_parts.append(f"```\n--- END OF FILE: {relative_path_str} ---\n")
        except Exception as e:
            send_progress(f"⚠️  Could not read: {relative_path_str} | {e}")
    return "\n".join(output_parts)
