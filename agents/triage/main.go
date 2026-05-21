package main

import (
	"context"
	"encoding/json"
	"log"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/redis/go-redis/v9"
)

func main() {
	nc, _ := nats.Connect("nats://nats:4222")
	rdb := redis.NewClient(&redis.Options{Addr: "redis:6379"})
	ctx := context.Background()

	nc.Subscribe("patients.triage", func(m *nats.Msg) {
		// Инкремент в Redis (Stateful)
		count, _ := rdb.Incr(ctx, "triage_requests").Result()
		log.Printf("Global Triage Count: %d", count)

		var data map[string]interface{}
		json.Unmarshal(m.Data, &data)

		// Логика аукциона / ответа
		resp := map[string]interface{}{
			"success":               true,
			"priority":              1,
			"recommended_specialty": "Cardiologist",
		}
		respBytes, _ := json.Marshal(resp)
		m.Respond(respBytes)
	})

	log.Println("Triage Agent (Stateful) started...")
	select {}
}
