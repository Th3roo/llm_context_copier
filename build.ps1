# Скрипт для сб# --console: Показывает консольное окно. Это нужно, чтобы CLI-режим мог выводить информацию.
#   При запуске без аргументов GUI все равно запустится, но с консолью на фоне.
#   Это компромисс для гибридного приложения.
$pyinstallerCommand = "pyinstaller --onefile --console --name $AppName"

# Переменные
$AppName = "RepoCopier"
$MainScript = "src/llm_context_copier/main.py"
$Icon = "icon.ico" # Опционально: путь к файлу иконки .ico

# --- Проверки ---
if (-not (Test-Path $MainScript)) {
    Write-Host "❌ Главный скрипт '$MainScript' не найден. Сборка отменена." -ForegroundColor Red
    exit 1
}

# --- Команда PyInstaller ---
# Используем --paths для указания корня исходников, чтобы относительные импорты работали
$pyinstallerCommand = "pyinstaller --onefile --windowed --name $AppName --paths src"

if (Test-Path $Icon) {
    $pyinstallerCommand += " --icon=$Icon"
} else {
    Write-Host "⚠️  Файл иконки '$Icon' не найден, сборка будет без иконки." -ForegroundColor Yellow
}

# Добавляем главный скрипт в команду
$pyinstallerCommand += " $MainScript"

# --- Выполнение ---
Write-Host "🚀 Запускаю сборку '$AppName'..." -ForegroundColor Green
Write-Host "Команда: $pyinstallerCommand"

try {
    Invoke-Expression $pyinstallerCommand
    Write-Host "✅ Сборка успешно завершена!" -ForegroundColor Green
    Write-Host "Исполняемый файл находится в папке 'dist'."
} catch {
    Write-Host "❌ Ошибка во время сборки:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# --- Очистка (опционально) ---
# Вы можете раскомментировать эти строки, чтобы автоматически удалять
# временные файлы и папки после сборки.

# Write-Host "🧹 Очистка временных файлов..."
# if (Test-Path "$AppName.spec") { Remove-Item "$AppName.spec" }
# if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

Write-Host "🎉 Готово!"
