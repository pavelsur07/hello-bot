# Архитектура

## Текущая реализация

Python 3.12+, модульный монолит. Границы MVP — в [mvp.md](mvp.md).
Работает Telegram long polling → Markdown → ответ; классификация и
генерация моделей пока представлены только контрактами.

1. apps/telegram_bot/main.py связывает адаптеры, проверяет отсутствие webhook
   и незавершённых событий, получает updates и управляет offset.
2. ChannelAdapter.parse_event(bytes) возвращает InboundMessage или None.
3. EventStore.claim(channel, external_event_id) атомарно закрепляет событие.
4. conversations.answer использует KnowledgeSearch.search и формирует
   OutboundMessage со ссылками `<source_path>::<section_title>` в source_refs.
5. Адаптер отправляет ответ, хранилище отмечает sent. Подтверждённый отказ
   допускает повтор; неизвестный исход доставки требует остановки.

Общие модели не содержат Telegram update, URL API, SDK или SQL.

## Ответственность и интерфейсы

| Модуль | Ответственность | Интерфейсы | Допустимые зависимости |
| --- | --- | --- | --- |
| core | Неизменяемые модели сообщений и каналы | InboundMessage, OutboundMessage, Channel | Только core |
| channels | Форматы платформ и транспорт | ChannelAdapter, DeliveryUncertainError | core, свои contracts |
| knowledge | Markdown, валидация, поиск и источники | KnowledgeSearch, KnowledgeHit, MarkdownKnowledge | core, свои contracts/models |
| storage | Атомарные claims и статусы | EventStore, SQLiteEventStore | core, свои contracts |
| routing | Категории и результат классификации; исполнения нет | Intent, IntentDecision, IntentClassifier | core; в будущем ai.contracts |
| ai | Раздельные возможности решения и генерации | DecisionModel, TextGenerator | core, routing.models |
| conversations | Независимый от платформы сценарий | answer, process_update | core; contracts/models остальных модулей |
| apps | Конфигурация, запуск, связывание | Telegram CLI | Нужные реализации |

Нельзя импортировать TelegramClient, SQLiteEventStore или SDK из conversations,
core, models.py и contracts.py. Контракты и модели используют только типы и
стандартные средства моделирования. Адаптеры находятся внутри предметных
модулей; новые слои не добавлены. Импорты проверяет tests/test_architecture.py.
Цикл исполнения ai ↔ routing не допускается: ai использует только
routing.models, routing — только ai.contracts.

## Знания

Опубликованные knowledge/**/*.md — источник истины. examples/knowledge/ —
вымышленные данные, подключаемые явным аргументом CLI.
MarkdownKnowledge строит индекс в памяти при старте; возвращает document_id,
путь, раздел, текст, title и area. Изменения файлов применяются после рестарта.
Постоянного индекса, хешей, фоновой переиндексации и PostgreSQL сейчас нет.
repository_root передаётся приложением, поэтому установленный wheel
не привязывает источники к каталогу site-packages.

Поиск сравнивает слова длиной от трёх символов, требует минимум двух совпадений
и покрытия половины слов запроса. Это эвристика, а не семантическое понимание.
Правила публикации — в [KNOWLEDGE_RULES.md](../KNOWLEDGE_RULES.md).

## Доставка и ошибки

SQLite хранит pending и sent с первичным ключом (channel, external_event_id).
Схема не меняется. Один токен и файл БД обслуживает один процесс.
has_pending() блокирует запуск до ручной сверки незавершённых доставок.
recover_pending() предназначен для согласованного восстановления после сверки
всех событий; приложение его автоматически не вызывает.

Успешный Telegram sendMessage и SQLite не образуют общей транзакции.
Таймаут или некорректный ответ после отправки может означать, что сообщение дошло.
DeliveryUncertainError переводится в DeliveryStateError без освобождения claim.
Такой же останов происходит при отказе записи sent после успеха.
Подтверждённые отказы освобождают claim; offset не проходит через них.

Получение updates можно повторять. Таймаут HTTP — 35 секунд; long polling —
20 секунд; после ошибки получения используется пауза. В диагностику не попадают
токены, URL с токеном, полные клиентские сообщения и тела ответов API.

## Следующие этапы

Jev реализует DecisionModel; IntentClassifier отвечает за маршрутизацию и
проверенный порог уверенности. OpenAI/Kimi реализуют TextGenerator.
Эти возможности не объединяются в универсальный клиент. При низкой уверенности
следующий сценарий обязан уточнить вопрос или обратиться к человеку.

Вебхуки проверяют подлинность до разбора. Пользователь определяется парой
(channel, external_user_id); объединение между каналами требует подтверждённой
идентичности. PostgreSQL, другие каналы и фоновые задачи подключаются по
отдельному согласованному требованию.
