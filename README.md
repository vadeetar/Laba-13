# 🏥 Система поддержки пациентов - Распределённая мультиагентная система

### Выполнил: Тарасов Вадим Романович
### Группа: 221131
### Вариант: 18
### Дата сдачи: 21.05.2026

---

## 🏗 Архитектура системы
Система представляет собой мультиагентную архитектуру (MAS), где каждый агент выполняет узкоспециализированную задачу, а Оркестратор на Python управляет сложными бизнес-процессами через шину сообщений **NATS**.

### Агенты системы:
1. **Appointment Agent (Go):** Создает и подтверждает записи к врачу.
2. **Triage Agent (Go):** Интеллектуальный анализатор симптомов, определяющий приоритет (Priority) и специализацию врача.
3. **Reminder Agent (Go):** Автоматизирует отправку напоминаний пациентам.
4. **Feedback Agent (Go + Redis):** Собирает обратную связь и ведет статистику в Redis.

---

## 🔄 Pipeline обработки пациента (Sequence Diagram)
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
