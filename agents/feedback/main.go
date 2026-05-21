package main

import (
	"context"
	"encoding/json"
	"log"
	"os"

	"github.com/nats-io/nats.go"

	"github.com/redis/go-redis/v9"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/sdk/trace"
)

type FeedbackTask struct {
	Patient string `json:"patient"`
	Rating  int    `json:"rating"`
}

func initTracer() {
	tp := trace.NewTracerProvider()
	otel.SetTracerProvider(tp)
}

func main() {

	initTracer()

	ctx := context.Background()

	natsURL := os.Getenv("NATS_URL")
	redisAddr := os.Getenv("REDIS_ADDR")

	if natsURL == "" {
		natsURL = "nats://nats:4222"
	}

	if redisAddr == "" {
		redisAddr = "redis:6379"
	}

	rdb := redis.NewClient(&redis.Options{
		Addr: redisAddr,
	})

	nc, err := nats.Connect(natsURL)

	if err != nil {
		log.Fatal(err)
	}

	log.Println("Feedback Agent connected")

	tracer := otel.Tracer("feedback-agent")

	_, err = nc.QueueSubscribe("tasks.feedback", "feedback-workers", func(msg *nats.Msg) {

		_, span := tracer.Start(context.Background(), "feedback-processing")
		defer span.End()

		var task FeedbackTask

		err := json.Unmarshal(msg.Data, &task)

		if err != nil {
			log.Println(err)
			return
		}

		count, err := rdb.Incr(ctx, "total_feedbacks").Result()

		if err != nil {
			log.Println(err)
			return
		}

		log.Printf("Feedback from %s rating=%d total=%d\n",
			task.Patient,
			task.Rating,
			count,
		)

		response := map[string]interface{}{
			"status": "saved",
			"count":  count,
		}

		data, _ := json.Marshal(response)

		nc.Publish("tasks.feedback.done", data)
	})

	if err != nil {
		log.Fatal(err)
	}

	select {}
}