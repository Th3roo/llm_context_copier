import sys
import os
from pathlib import Path
import pyperclip
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QFileDialog, QTextEdit,
    QCheckBox, QGroupBox, QStatusBar, QSpinBox
)
from PyQt6.QtCore import QThread, QObject, pyqtSignal, Qt, QSettings
from gitignore_parser import parse_gitignore

# --- КОНФИГУРАЦИЯ ---
DEFAULT_IGNORE = [
    ".git", ".svn", ".hg", "venv", ".venv", "env", "ENV",
    "__pycache__", "*.pyc", ".pytest_cache", ".mypy_cache",
    ".vscode", ".idea", "*.swp", "node_modules", "dist",
    "build", "target", "out", ".env", "*.log", "*.lock",
]
# --- КОНЕЦ КОНФИГУРАЦИИ ---


def get_gitignore_matcher(base_path: Path):
    gitignore_path = base_path / '.gitignore'
    if gitignore_path.is_file():
        try:
            return parse_gitignore(gitignore_path, base_path)
        except Exception as e:
            print(f"Warning: Could not parse .gitignore file: {e}")
    return lambda p: False


def get_project_structure(root_path: Path, ignored_patterns: list, gitignore_matcher) -> str:
    tree_lines = []
    
    def recurse(current_path: Path, prefix: str = ""):
        if gitignore_matcher(current_path) or any(part in str(current_path.relative_to(root_path)) for part in ignored_patterns):
            return
        
        try:
            items = sorted(list(current_path.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
        except (OSError, PermissionError):
            return

        valid_items = [item for item in items if not (item.name in ignored_patterns or gitignore_matcher(item))]

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


def create_llm_context(
    repo_path_str: str, extensions: list, include_files: list,
    exclude: list, include_tree: bool, max_chars_per_file: int, progress_callback
) -> str:
    repo_path = Path(repo_path_str).resolve()
    if not repo_path.is_dir():
        raise FileNotFoundError(f"Directory not found: {repo_path}")

    progress_callback.emit("- Parsing .gitignore...")
    gitignore_matcher = get_gitignore_matcher(repo_path)
    all_exclusions = DEFAULT_IGNORE + exclude
    output_parts = []
    
    if include_tree:
        progress_callback.emit("- Building project tree...")
        tree_structure = get_project_structure(repo_path, all_exclusions, gitignore_matcher)
        output_parts.append("Project file structure:\n=======================\n```\n" + tree_structure + "\n```\n")

    output_parts.append("File contents:\n==============")

    progress_callback.emit("- Finding files...")
    files_to_process_set = set()
    for ext in extensions:
        if ext and not ext.startswith('.'): ext = '.' + ext
        if ext: files_to_process_set.update(repo_path.rglob(f'*{ext}'))
    for filename in include_files:
        if filename: files_to_process_set.update(repo_path.rglob(filename))

    final_file_list = []
    for file_path in sorted(list(files_to_process_set)):
        if file_path.is_file():
            path_parts = {p.name for p in file_path.parents} | {file_path.name}
            if any(part in all_exclusions for part in path_parts) or gitignore_matcher(file_path):
                continue
            final_file_list.append(file_path)

    total_files = len(final_file_list)
    for i, file_path in enumerate(final_file_list):
        relative_path_str = str(file_path.relative_to(repo_path))
        progress_callback.emit(f"({i+1}/{total_files}) 📄 {relative_path_str}")
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(max_chars_per_file + 1)
            
            truncated = False
            if len(content) > max_chars_per_file:
                content = content[:max_chars_per_file]
                truncated = True

            lang = file_path.suffix.lstrip('.') if file_path.suffix else 'text'
            
            output_parts.append(f"--- START OF FILE: {relative_path_str} ---")
            output_parts.append(f"```{lang}\n{content.strip()}")
            if truncated:
                output_parts.append("\n\n[... content truncated due to size limit ...]")
            
            # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
            output_parts.append(f"```\n--- END OF FILE: {relative_path_str} ---\n")

        except Exception as e:
            progress_callback.emit(f"⚠️  Could not read: {relative_path_str} | {e}")

    return "\n".join(output_parts)


class Worker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, repo_path, extensions, include_files, exclude, include_tree, max_chars):
        super().__init__()
        self.repo_path, self.extensions, self.include_files = repo_path, extensions, include_files
        self.exclude, self.include_tree, self.max_chars = exclude, include_tree, max_chars

    def run(self):
        try:
            result = create_llm_context(
                self.repo_path, self.extensions, self.include_files,
                self.exclude, self.include_tree, self.max_chars, self.progress
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("MyCompany", "RepoCopier")
        self.setWindowTitle('Repo Copier для LLM v2.4')
        self.setGeometry(100, 100, 750, 650)
        self.initUI()
        self.load_settings()
        self.thread = None
        self.worker = None

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        path_group = QGroupBox("1. Выберите папку проекта")
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        browse_btn = QPushButton("Обзор...")
        browse_btn.clicked.connect(self.browse_folder)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(browse_btn)
        path_group.setLayout(path_layout)

        settings_group = QGroupBox("2. Настройте фильтры")
        settings_layout = QVBoxLayout()
        
        ext_layout = QHBoxLayout()
        ext_layout.addWidget(QLabel("Включить расширения:"))
        self.ext_edit = QLineEdit()
        ext_layout.addWidget(self.ext_edit)
        
        include_files_layout = QHBoxLayout()
        include_files_layout.addWidget(QLabel("Включить файлы (по имени):"))
        self.include_files_edit = QLineEdit()
        include_files_layout.addWidget(self.include_files_edit)

        exclude_layout = QHBoxLayout()
        exclude_layout.addWidget(QLabel("Доп. исключения:"))
        self.exclude_edit = QLineEdit()
        exclude_layout.addWidget(self.exclude_edit)

        limit_layout = QHBoxLayout()
        limit_layout.addWidget(QLabel("Лимит символов на файл:"))
        self.limit_spinbox = QSpinBox()
        self.limit_spinbox.setRange(100, 1_000_000)
        self.limit_spinbox.setSingleStep(1000)
        self.limit_spinbox.setSuffix(" симв.")
        limit_layout.addWidget(self.limit_spinbox)
        limit_layout.addStretch()

        self.tree_checkbox = QCheckBox("Включить дерево файлов в полный вывод")
        
        settings_layout.addLayout(ext_layout)
        settings_layout.addLayout(include_files_layout)
        settings_layout.addLayout(exclude_layout)
        settings_layout.addLayout(limit_layout)
        settings_layout.addWidget(self.tree_checkbox)
        settings_group.setLayout(settings_layout)

        action_group = QGroupBox("3. Выполнить действие")
        action_layout = QHBoxLayout()
        self.run_button = QPushButton("🚀 Сгенерировать всё и скопировать")
        self.run_button.setStyleSheet("font-size: 14px; padding: 10px; background-color: #4CAF50; color: white;")
        self.run_button.clicked.connect(self.run_processing)
        self.tree_button = QPushButton("📋 Только дерево в буфер")
        self.tree_button.setStyleSheet("font-size: 14px; padding: 10px;")
        self.tree_button.clicked.connect(self.generate_tree_only)
        action_layout.addWidget(self.run_button)
        action_layout.addWidget(self.tree_button)
        action_group.setLayout(action_layout)

        log_group = QGroupBox("Лог выполнения")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        
        main_layout.addWidget(path_group)
        main_layout.addWidget(settings_group)
        main_layout.addWidget(action_group)
        main_layout.addWidget(log_group)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Готов к работе.")

    def run_processing(self):
        repo_path = self.validate_path()
        if not repo_path: return

        extensions = self.ext_edit.text().split()
        include_files = self.include_files_edit.text().split()
        exclude = self.exclude_edit.text().split()
        include_tree = self.tree_checkbox.isChecked()
        max_chars = self.limit_spinbox.value()
        
        self.log_text.clear()
        self.log_text.append("🚀 Запускаю полную обработку...")
        self.set_ui_enabled(False)
        
        self.thread = QThread()
        self.worker = Worker(repo_path, extensions, include_files, exclude, include_tree, max_chars)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.progress.connect(lambda msg: self.log_text.append(msg))
        self.thread.start()

    def load_settings(self):
        self.path_edit.setText(self.settings.value("last_path", str(Path.home())))
        self.ext_edit.setText(self.settings.value("extensions", ".py .js .html .css .md .txt .json"))
        self.include_files_edit.setText(self.settings.value("include_files", "LICENSE Dockerfile .env.example"))
        self.exclude_edit.setText(self.settings.value("exclusions", "docs assets"))
        self.limit_spinbox.setValue(self.settings.value("limit_per_file", 100000, type=int))
        self.tree_checkbox.setChecked(self.settings.value("include_tree", True, type=bool))

    def save_settings(self):
        self.settings.setValue("last_path", self.path_edit.text())
        self.settings.setValue("extensions", self.ext_edit.text())
        self.settings.setValue("include_files", self.include_files_edit.text())
        self.settings.setValue("exclusions", self.exclude_edit.text())
        self.settings.setValue("limit_per_file", self.limit_spinbox.value())
        self.settings.setValue("include_tree", self.tree_checkbox.isChecked())
    
    def browse_folder(self):
        start_path = self.path_edit.text() if self.path_edit.text() else str(Path.home())
        folder_path = QFileDialog.getExistingDirectory(self, "Выберите папку проекта", start_path)
        if folder_path: self.path_edit.setText(folder_path)
    def validate_path(self):
        repo_path = self.path_edit.text()
        if not repo_path or not Path(repo_path).is_dir():
            self.status_bar.showMessage("❌ Ошибка: Укажите корректный путь к папке проекта.")
            return None
        return repo_path
    def generate_tree_only(self):
        repo_path_str = self.validate_path()
        if not repo_path_str: return
        repo_path = Path(repo_path_str)
        self.log_text.clear(); self.log_text.append("🌳 Генерирую только дерево файлов...")
        exclude = self.exclude_edit.text().split()
        all_exclusions = DEFAULT_IGNORE + exclude
        try:
            gitignore_matcher = get_gitignore_matcher(repo_path)
            tree = get_project_structure(repo_path, all_exclusions, gitignore_matcher)
            pyperclip.copy(tree)
            self.log_text.append("\n" + tree)
            self.log_text.append(f"\n✅ Дерево проекта скопировано в буфер обмена ({len(tree)} символов).")
            self.status_bar.showMessage("✅ Дерево проекта скопировано.")
        except Exception as e:
            self.log_text.append(f"\n❌ Ошибка при генерации дерева: {e}")
            self.status_bar.showMessage(f"❌ Ошибка: {e}")
    def on_finished(self, result):
        if not result:
            self.log_text.append("\n❌ Ничего не найдено с заданными параметрами.")
            self.status_bar.showMessage("❌ Файлы не найдены.")
        else:
            pyperclip.copy(result)
            char_count = len(result)
            self.log_text.append(f"\n✅ Готово! Контекст скопирован ({char_count:,} символов).")
            self.status_bar.showMessage(f"✅ Готово! Скопировано {char_count:,} символов.")
        self.cleanup_thread()
    def on_error(self, error_message):
        self.log_text.append(f"\n❌ Произошла ошибка: {error_message}")
        self.status_bar.showMessage(f"❌ Ошибка: {error_message}")
        self.cleanup_thread()
    def cleanup_thread(self):
        self.thread.quit(); self.thread.wait(); self.set_ui_enabled(True)
    def set_ui_enabled(self, enabled):
        for w in [self.run_button, self.tree_button, self.path_edit, self.ext_edit, self.include_files_edit, self.exclude_edit, self.limit_spinbox]:
            w.setEnabled(enabled)
    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = App()
    ex.show()
    sys.exit(app.exec())