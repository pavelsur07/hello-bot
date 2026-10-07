# Hello Bot

Модульный монолит на Python 3.12+. Текущий MVP получает личные текстовые
сообщения Telegram через long polling, ищет опубликованный Markdown-раздел
и отправляет ответ с источником. Нет ответа — предлагает уточнить вопрос
или обратиться к оператору.

Jev, OpenAI, Kimi, веб-чат, MAX и автоматическая передача человеку пока
не подключены. Границы и критерии — в [docs/mvp.md](docs/mvp.md),
модули — в [docs/architecture.md](docs/architecture.md).

## Установка

Из корня репозитория в PowerShell; активация среды не нужна:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
```

Linux/macOS: используйте .venv/bin/python вместо .venv\Scripts\python.exe.
Версии инструментов и их зависимостей зафиксированы. Для работы бота внешние
пакеты не нужны; Ruff, mypy и build используются только при разработке.
Первоначальная установка требует доступа к PyPI.

## Демо без ключей и сети

```powershell
.\.venv\Scripts\python.exe apps/telegram_bot/main.py --demo-update examples/demo_update.json --knowledge-dir examples/knowledge
```

Ожидается ответ о доставке за 300 ₽ со ссылкой на раздел. Демо использует
вымышленные знания; рабочий каталог knowledge/ не подключается автоматически.

## Единая проверка

```powershell
.\.venv\Scripts\python.exe scripts/check.py
```

Эту же команду запускает GitHub Actions для Python 3.12 и 3.14.
Она проверяет форматирование, линтер, типы, архитектурные импорты и unittest,
собирает sdist/wheel, устанавливает wheel в отдельную среду и запускает демо.
Проверки не требуют токенов или сети после установки инструментов.
Артефакты находятся в .local/; пользовательский dist/ не удаляется.
Wheel содержит библиотеку hello_bot; CLI, документация и примеры — в
репозитории и sdist. Демо при проверке использует установленную библиотеку.

Форматирование: python -m ruff format .
Отдельные тесты: python -m unittest tests.test_telegram_flow -v
(обе команды выполнять Python из .venv).

## Telegram long polling

Добавьте опубликованные статьи в knowledge/ по
[KNOWLEDGE_RULES.md](KNOWLEDGE_RULES.md). Только TELEGRAM_BOT_TOKEN читается
из окружения. [.env.example](.env.example) описывает конфигурацию; приложение
не загружает .env автоматически. Пути задаются аргументами CLI; относительные
пути отсчитываются от корня проекта. Ввод токена без литерала в истории:

```powershell
$env:TELEGRAM_BOT_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Telegram token' -AsSecureString)).Password
.\.venv\Scripts\python.exe apps/telegram_bot/main.py --knowledge-dir knowledge --db-path .local/events.sqlite3
```

Один процесс на один токен и файл SQLite. При установленном webhook бот
отказывается запускать polling; перед переходом проверьте getWebhookInfo
и вручную удалите webhook. Реальный API проверяется отдельно с тестовым
ботом; обычные тесты подменяют транспорт.

Повтор отправленного update не создаёт второй ответ. Если отправка завершилась
таймаутом или статус sent не удалось сохранить, процесс останавливается:
исход доставки неизвестен. Pending блокирует следующий запуск.
Проверьте доставку в Telegram; отправленные события отметьте sent,
подтверждённо неотправленные освободите через EventStore.release.
Восстановление согласуется отдельно; не удаляйте БД и не сбрасывайте все
pending ради запуска. Telegram и SQLite не поддерживают общую транзакцию;
гарантия exactly-once для внешней отправки отсутствует.

Длинный раздел не блокирует очередь: бот предлагает обратиться к оператору
и сохраняет источник. После изменения знаний перезапустите бот.

## Структура

- apps/telegram_bot/ — CLI; apps/api/ и apps/worker/ — будущие точки входа.
- packages/hello_bot/ — core, channels, conversations, knowledge, storage,
  routing и ai; реализации находятся рядом с контрактами.
- knowledge/ — рабочие знания; examples/ — вымышленные демонстрационные данные.
- tests/fixtures/ — синтетические события и будущий набор классификации.
- scripts/check.py — единая проверка; .github/workflows/ — CI.
- docs/ — MVP, архитектура, разработка и планы.

Порядок работы — в [docs/development.md](docs/development.md),
правила агентов — в [AGENTS.md](AGENTS.md).
[План подготовки](docs/plans/autonomous-development-foundation.md).
