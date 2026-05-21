# 🏥 Система поддержки пациентов (Lab 13)

Система автоматизации процессов записи и обслуживания пациентов на базе микросервисной архитектуры. Реализована в рамках лабораторной работы №13 (Вариант 18).

**Студент:** Тарасов Вадим Романович, группа 221131

---

## 🏗 Архитектура системы

Система состоит из центрального **Оркестратора** (Python/FastAPI) и четырех **Микросервисов-агентов** (Go), обменивающихся сообщениями через **NATS**. Хранение состояния реализовано с помощью **Redis**.

### Диаграмма взаимодействия (Pipeline)

```mermaid
sequenceDiagram
    participant Client
    participant Orchestrator
    participant TriageAgent
    participant AppointmentAgent
    Client->>Orchestrator: POST /patients/register
    Orchestrator->>TriageAgent: patients.triage (symptoms)
    TriageAgent-->>Orchestrator: triage.completed (priority, specialty)
    Orchestrator->>AppointmentAgent: appointments.process (specialty)
    AppointmentAgent-->>Orchestrator: appointments.completed (appointment_id)
    Orchestrator-->>Client: 200 OK (appointment_details)

graph TD
    User((Пользователь)) --> Orchestrator[Оркестратор - FastAPI]
    Orchestrator --> NATS{Шина NATS}
    
    subgraph "Агенты (Microservices)"
        NATS --> TriageAgent[Triage Agent - Go]
        NATS --> ApptAgent[Appointment Agent - Go]
        NATS --> RemindAgent[Reminder Agent - Go]
        NATS --> FeedAgent[Feedback Agent - Go]
    end
    
    TriageAgent -->|Анализ симптомов| NATS
    ApptAgent -->|Запись| NATS
    RemindAgent -->|Уведомление| NATS
    FeedAgent -->|Оценка| NATS

⚙️ Агенты системы
Triage Agent (Go): Анализирует жалобы и симптомы пациента, классифицирует серьезность (urgency) и рекомендует профильного специалиста.

Appointment Agent (Go): Отвечает за логику записи на прием, управление расписанием и создание слотов в базе данных.


🚀 Быстрый старт
Убедитесь, что у вас установлены Docker и Docker Compose.

Склонируйте репозиторий.

Запустите всю систему командой:

Bash
docker compose up --build
API будет доступно по адресу http://localhost:8000.

Reminder Agent (Go): Генерирует напоминания пациентам о предстоящих визитах, работая в асинхронном режиме.

Feedback Agent (Go): Обрабатывает отзывы пациентов после приема, сохраняя их для аналитики качества обслуживания.


📡 Примеры API-запросов
Регистрация пациента:
POST /patients/register

Request Body:

JSON
{
  "patient_id": "PAT001",
  "first_name": "Иван",
  "last_name": "Петров",
  "symptoms": ["chest pain"],
  "urgency": "high"
}
Response:

JSON
{
  "status": "success",
  "appointment": { "appointment_id": "APT001", "specialty": "Cardiologist" },
  "triage": { "priority": 1, "level": "high" }
}




🛡 Отказоустойчивость и обработка ошибок
Система спроектирована для работы в высоконагруженных средах:

Таймауты: Оркестратор ожидает ответа от агентов не более 5 секунд. Если агент не справляется, возвращается ошибка 504.

Retry-механизм: В коде оркестратора предусмотрена логика повторных попыток отправки сообщений при сбоях сети NATS.

Изоляция: Каждый агент функционирует в отдельном Docker-контейнере. Отказ одного из агентов (например, модуля отзывов) не приводит к падению всей системы записи
