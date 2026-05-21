package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"github.com/nats-io/nats.go"
	"github.com/redis/go-redis/v9"
)

type Task struct {
	ID      string `json:"id"`
	Type    string `json:"type"`
	Payload string `json:"payload"`
}

var ctx = context.Background()

func main() {
	// Подключаемся к NATS
	nc, err := nats.Connect("nats://127.0.0.1:4222")
	if err != nil {
		log.Fatal(err)
	}
	defer nc.Close()

	// Подключаемся к Redis
	rdb := redis.NewClient(&redis.Options{
		Addr: "127.0.0.1:6379",
	})

	// Проверяем связь с Redis
	if err := rdb.Ping(ctx).Err(); err != nil {
		log.Fatalf("❌ Ошибка подключения к Redis: %v", err)
	}

	log.Println("📊 Агент 'Сбор обратной связи' запущен и подключен к Redis...")

	nc.Subscribe("tasks.feedback", func(m *nats.Msg) {
		var task Task
		json.Unmarshal(m.Data, &task)
		log.Printf("📥 Получен отзыв: %s", task.ID)

		// Увеличиваем счетчик отзывов в Redis на 1
		newCount, err := rdb.Incr(ctx, "total_feedbacks").Result()
		if err != nil {
			log.Printf("❌ Ошибка работы с Redis: %v", err)
			return
		}

		// Формируем ответ с учетом статистики из кэша
		outputMsg := fmt.Sprintf("Отзыв сохранен. Всего собрано отзывов: %d", newCount)
		response := `{"task_id": "` + task.ID + `", "success": true, "output": "` + outputMsg + `"}`

		m.Respond([]byte(response))
		log.Printf("📤 Ответ отправлен. Текущий счетчик: %d", newCount)
	})

	select {}
}