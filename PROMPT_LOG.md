# PROMPT_LOG — лог взаимодействия с AI

**Студент:** Тарасов Вадим Романович, группа 221131  
**Лабораторная:** №13, вариант 18

| № | Промпт / задача | Результат |
|---|-----------------|-----------|
| 1 | Развернуть NATS и Redis в docker-compose для MAS на Windows | docker-compose с сервисами nats, redis, агентами |
| 2 | Исправить `docker-compose: command not found` в Git Bash | Использование `docker compose` (v2) |
| 3 | Синхронизация FastAPI и Go через NATS, исправление 504 timeout | Request-Reply через `msg.Respond` / `nc.request` |
| 4 | Подключение Go к Redis для stateful feedback-agent | INCR счётчиков, восстановление при старте |
| 5 | Добавить OpenTelemetry и Jaeger | OTLP exporter в оркестраторе и Go-агентах |
| 6 | Реализовать аукцион распределения задач | `tasks.auction`, ставки cost/skill от агентов |
| 7 | Динамическое масштабирование при нагрузке | Redis-очередь + `docker compose scale` |
| 8 | LLM-агент (Ollama) | `agents/llm`, Ollama API + rules fallback |
| 9 | Веб-панель мониторинга | FastAPI + Jinja2 `/monitor`, ручной запуск pipeline |
| 10 | Доработка по замечаниям проверки | Полный pipeline, 4 Go-агента + LLM, trace propagation |
