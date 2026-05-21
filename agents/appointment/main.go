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

	log.Println("Агент 'Запись к врачу' запущен и ожидает задачи...")

	nc.Subscribe("tasks.appointment", func(m *nats.Msg) {
		var task Task
		json.Unmarshal(m.Data, &task)
		log.Printf("📥 Получен запрос на запись: %s", task.ID)

		response := `{"task_id": "` + task.ID + `", "success": true, "output": "Запись подтверждена"}`

		err := m.Respond([]byte(response))
		if err != nil {
			log.Printf("❌ Ошибка при отправке ответа: %v", err)
		} else {
			log.Println("📤 Ответ успешно отправлен в Оркестратор")
		}
	})

	select {}
}