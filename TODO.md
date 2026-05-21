# План разработки (Лабораторная работа №13, вариант 18)

- [x] Развернуть инфраструктуру NATS + Redis + Jaeger через Docker Compose
- [x] Разработать оркестратор на FastAPI с pipeline
- [x] Агент «Триаж» (Go) — Request-Reply, классификация симптомов
- [x] Агент «Запись к врачу» (Go) ×2 — аукцион, балансировка QueueSubscribe
- [x] Агент «Напоминание» (Go)
- [x] Агент «Обратная связь» (Go + Redis, stateful)
- [x] LLM-агент (Python) — анализ симптомов
- [x] OpenTelemetry → Jaeger
- [x] REST API POST /patients/register
- [x] Retry (до 3 раз), таймауты, логирование в файл
- [x] Веб-мониторинг /monitor
- [x] Тесты (pytest, go test)
- [x] Конфигурация через .env
