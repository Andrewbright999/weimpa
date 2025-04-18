# README.md — это база, инструкция. Постепенно заполняем.

## 📦 Описание
Что это. Зачем. Как.

## 🛠 Стек
Python / PHP / Flask / Laravel / PostgreSQL / SQLite / GitHub Actions

## ⚙️ Установка
```bash
git clone ...
cd проект
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 🚀 Запуск
```bash
python main.py
# или flask run / php artisan serve
```

## 🧪 Тесты
```bash
pytest
# или phpunit
```

## 📁 Структура

```
weimpa/
├── .gitignore               # 🙈 Игнорируемые файлы
├── gitmanual.md            # 📝 Инструкция по работе с git
├── requirements.txt        # 📦 Зависимости проекта
├── main.py                 # 🚀 Точка входа в приложение
│
├── config.py               # ⚙️ Конфигурации
├── db.py                   # 🗄️ Подключение к базе данных
├── data_manager.py         # 📊 Работа с данными
├── google_sheets.py        # 📄 Интеграция с Google Sheets
├── vector_search.py        # 🔍 Поиск по векторам
├── openai_module.py        # 🤖 Взаимодействие с OpenAI
│
├── communicator_router.py  # 📡 Роутинг: коммуникатор
└── manager_router.py       # 🧭 Роутинг: менеджер
```

## 🔐 Переменные окружения
- `.env` — локально  
- `.env.example` — в гите  

## 🌿 Git-порядок
- Ветки: `feature/...`, `dev/...`
- `main` — не трогать
- PR всегда
- Коммиты понятные
- `git pull` каждый день

## 🤖 CI
- `.github/workflows/*.yml`  
- Тесты, линт, билд на push/PR

## 👥 Команда
- @dev1  
- @dev2

## 📄 Лицензия
MIT
