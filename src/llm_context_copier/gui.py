import os
import sys
from pathlib import Path
import pyperclip
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QFileDialog, QTextEdit,
    QCheckBox, QGroupBox, QStatusBar, QSpinBox, QFormLayout
)
from PyQt6.QtCore import QThread, QObject, pyqtSignal, Qt, QSettings
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from .context_generator import create_llm_context, DEFAULT_IGNORE_PATTERNS
from .file_utils import get_project_structure, get_gitignore_matcher, get_gitattributes_matcher


class Worker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, repo_path, include_ext, include_files, exclude_folders, exclude_files, exclude_ext, include_tree, max_chars):
        super().__init__()
        self.repo_path = repo_path
        self.include_ext = include_ext
        self.include_files = include_files
        self.exclude_folders = exclude_folders
        self.exclude_files = exclude_files
        self.exclude_ext = exclude_ext
        self.include_tree = include_tree
        self.max_chars = max_chars

    def run(self):
        try:
            result = create_llm_context(
                self.repo_path, self.include_ext, self.include_files, self.exclude_folders,
                self.exclude_files, self.exclude_ext, self.include_tree, self.max_chars, self.progress
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("MyCompany", "RepoCopier")
        self.setWindowTitle('Repo Copier для LLM v3.5')
        self.setGeometry(100, 100, 800, 700)
        self.setAcceptDrops(True)
        self.initUI()
        self.load_settings()
        self.thread = None
        self.worker = None

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        path_group = QGroupBox("1. Укажите или перетащите папку проекта")
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Перетащите папку сюда или нажмите 'Обзор'")
        browse_btn = QPushButton("Обзор...")
        browse_btn.clicked.connect(self.browse_folder)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(browse_btn)
        path_group.setLayout(path_layout)

        settings_group = QGroupBox("2. Настройте фильтры")
        settings_layout = QFormLayout()
        self.ext_edit = QLineEdit()
        settings_layout.addRow(QLabel("<b>Включить в контекст:</b>"), None)
        settings_layout.addRow("Расширения файлов:", self.ext_edit)
        self.include_files_edit = QLineEdit()
        settings_layout.addRow("Файлы по имени:", self.include_files_edit)
        self.exclude_folders_edit = QLineEdit()
        self.exclude_files_edit = QLineEdit()
        self.exclude_ext_edit = QLineEdit()
        settings_layout.addRow(QLabel("<b>Исключить из контекста (дополнительно к .gitignore):</b>"), None)
        settings_layout.addRow("Папки по имени:", self.exclude_folders_edit)
        settings_layout.addRow("Файлы по имени:", self.exclude_files_edit)
        settings_layout.addRow("Файлы по расширению:", self.exclude_ext_edit)

        settings_layout.addRow(QLabel("<b>Прочие настройки:</b>"), None)

        limit_layout = QHBoxLayout()
        self.limit_spinbox = QSpinBox()
        self.limit_spinbox.setRange(100, 1_000_000)
        self.limit_spinbox.setSingleStep(1000)
        self.limit_spinbox.setSuffix(" симв.")
        limit_layout.addWidget(self.limit_spinbox)
        limit_layout.addStretch()
        settings_layout.addRow("Лимит символов на файл:", limit_layout)

        self.tree_checkbox = QCheckBox("Включить дерево файлов в полный вывод")
        settings_layout.addRow(self.tree_checkbox)

        self.exact_tokens_checkbox = QCheckBox("Точный подсчет токенов (для OpenAI моделей)")
        settings_layout.addRow(self.exact_tokens_checkbox)

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
        if not repo_path:
            return
        include_ext = self.ext_edit.text().split()
        include_files = self.include_files_edit.text().split()
        exclude_folders = self.exclude_folders_edit.text().split()
        exclude_files = self.exclude_files_edit.text().split()
        exclude_ext = [e if e.startswith('.') else '.' + e for e in self.exclude_ext_edit.text().split() if e]
        include_tree = self.tree_checkbox.isChecked()
        max_chars = self.limit_spinbox.value()
        self.log_text.clear()
        self.log_text.append("🚀 Запускаю полную обработку...")
        self.set_ui_enabled(False)
        self.thread = QThread()
        self.worker = Worker(repo_path, include_ext, include_files, exclude_folders, exclude_files, exclude_ext, include_tree, max_chars)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.progress.connect(lambda msg: self.log_text.append(msg))
        self.thread.start()

    def load_settings(self):
        self.path_edit.setText(self.settings.value("last_path", str(Path.home())))
        self.ext_edit.setText(self.settings.value("include_ext", ".py .js .html .css .md .txt .json"))
        self.include_files_edit.setText(self.settings.value("include_files", "LICENSE Dockerfile .env.example"))
        self.exclude_folders_edit.setText(self.settings.value("exclude_folders", "docs assets temp"))
        self.exclude_files_edit.setText(self.settings.value("exclude_files", "package-lock.json yarn.lock"))
        self.exclude_ext_edit.setText(self.settings.value("exclude_ext", ".log .tmp .bak"))
        self.limit_spinbox.setValue(self.settings.value("limit_per_file", 100000, type=int))
        self.tree_checkbox.setChecked(self.settings.value("include_tree", True, type=bool))
        self.exact_tokens_checkbox.setChecked(self.settings.value("exact_tokens", False, type=bool))

    def save_settings(self):
        self.settings.setValue("last_path", self.path_edit.text())
        self.settings.setValue("include_ext", self.ext_edit.text())
        self.settings.setValue("include_files", self.include_files_edit.text())
        self.settings.setValue("exclude_folders", self.exclude_folders_edit.text())
        self.settings.setValue("exclude_files", self.exclude_files_edit.text())
        self.settings.setValue("exclude_ext", self.exclude_ext_edit.text())
        self.settings.setValue("limit_per_file", self.limit_spinbox.value())
        self.settings.setValue("include_tree", self.tree_checkbox.isChecked())
        self.settings.setValue("exact_tokens", self.exact_tokens_checkbox.isChecked())

    def browse_folder(self):
        start_path = self.path_edit.text() if self.path_edit.text() and Path(self.path_edit.text()).is_dir() else str(Path.home())
        folder_path = QFileDialog.getExistingDirectory(self, "Выберите папку проекта", start_path)
        if folder_path:
            self.path_edit.setText(folder_path)

    def validate_path(self):
        repo_path = self.path_edit.text()
        if not repo_path or not Path(repo_path).is_dir():
            self.status_bar.showMessage("❌ Ошибка: Укажите корректный путь к папке проекта.")
            return None
        return repo_path

    def generate_tree_only(self):
        repo_path_str = self.validate_path()
        if not repo_path_str:
            return
        repo_path = Path(repo_path_str)
        self.log_text.clear()
        self.log_text.append("🌳 Генерирую только дерево файлов...")
        exclude_folders = self.exclude_folders_edit.text().split()
        all_exclusions = DEFAULT_IGNORE_PATTERNS + exclude_folders
        try:
            gitignore_matcher = get_gitignore_matcher(repo_path)
            gitattributes_matcher = get_gitattributes_matcher(repo_path)
            tree = get_project_structure(repo_path, all_exclusions, gitignore_matcher, gitattributes_matcher)
            pyperclip.copy(tree)
            self.log_text.append("\n" + tree)
            self.log_text.append(f"\n✅ Дерево проекта скопировано в буфер обмена ({len(tree):,} символов).")
            self.status_bar.showMessage("✅ Дерево проекта скопировано.")
        except Exception as e:
            self.log_text.append(f"\n❌ Ошибка при генерации дерева: {e}")
            self.status_bar.showMessage(f"❌ Ошибка: {e}")

    def on_finished(self, result):
        if not result or "File contents:\n==============\n" == result.strip():
            self.log_text.append("\n❌ Ничего не найдено с заданными параметрами.")
            self.status_bar.showMessage("❌ Файлы не найдены.")
        else:
            pyperclip.copy(result)
            char_count = len(result)
            approx_token_count = char_count // 4
            base_message = f"{char_count:,} символов, ~{approx_token_count:,} токенов (приблиз.)"
            full_message = base_message
            if self.exact_tokens_checkbox.isChecked():
                try:
                    import PyTokenCounter
                    exact_token_count = PyTokenCounter.GetNumTokenStr(string=result)
                    full_message += f" | {exact_token_count:,} (для OpenAI)"
                except (ImportError, Exception) as e:
                    print(f"Warning: Could not use PyTokenCounter ({e}).")
                    full_message += " | Ошибка точного подсчета"
            self.log_text.append(f"\n✅ Готово! Контекст скопирован ({full_message}).")
            self.status_bar.showMessage(f"✅ Готово! Скопировано ({full_message}).")
        self.cleanup_thread()

    def on_error(self, error_message):
        self.log_text.append(f"\n❌ Произошла ошибка: {error_message}")
        self.status_bar.showMessage(f"❌ Ошибка: {error_message}")
        self.cleanup_thread()

    def cleanup_thread(self):
        if self.thread:
            self.thread.quit()
            self.thread.wait()
        self.set_ui_enabled(True)

    def set_ui_enabled(self, enabled):
        widgets_to_toggle = [
            self.run_button, self.tree_button, self.path_edit, self.ext_edit,
            self.include_files_edit, self.exclude_folders_edit,
            self.exclude_files_edit, self.exclude_ext_edit, self.limit_spinbox,
            self.tree_checkbox, self.exact_tokens_checkbox
        ]
        for w in widgets_to_toggle:
            w.setEnabled(enabled)

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isdir(path):
                self.path_edit.setText(path)
            else:
                self.status_bar.showMessage("❌ Пожалуйста, перетащите папку, а не файл.")
