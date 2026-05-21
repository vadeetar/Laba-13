package main

import (
	"encoding/json"
	"log"
	"github.com/nats-io/nats.go"
)

type Task struct {
	ID      string `json:"id"`
	Type    string `json:"type"`
	Payload string `json:"payload"`
}

func main() {
	nc, err := nats.Connect("nats://127.0.0.1:4222")
	if err != nil {
		log.Fatal(err)
	}
	defer nc.Close()

	log.Println("⏰ Агент 'Напоминание' запущен и ожидает задачи...")

	nc.Subscribe("tasks.reminder", func(m *nats.Msg) {
		var task Task
		json.Unmarshal(m.Data, &task)
		log.Printf("📥 Получена задача на напоминание: %s", task.ID)

		// Логика агента: планируем SMS для пациента
		response := `{"task_id": "` + task.ID + `", "success": true, "output": "SMS-напоминание запланировано"}`

		err := m.Respond([]byte(response))
		if err != nil {
			log.Printf("❌ Ошибка при отправке: %v", err)
		} else {
			log.Println("📤 Статус напоминания отправлен в Оркестратор")
		}
	})

	select {}
}