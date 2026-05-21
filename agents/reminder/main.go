package main

import (
	"context"
	"encoding/json"
	"log"
	"os"

	"github.com/nats-io/nats.go"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/sdk/trace"
)

type ReminderTask struct {
	Patient string `json:"patient"`
	Date    string `json:"date"`
}

type ReminderResult struct {
	Status string `json:"status"`
	Sent   bool   `json:"sent"`
}

func initTracer() {
	tp := trace.NewTracerProvider()
	otel.SetTracerProvider(tp)
}

func main() {

	initTracer()

	natsURL := os.Getenv("NATS_URL")

	if natsURL == "" {
		natsURL = "nats://nats:4222"
	}

	nc, err := nats.Connect(natsURL)

	if err != nil {
		log.Fatal(err)
	}

	log.Println("Reminder Agent connected")

	tracer := otel.Tracer("reminder-agent")

	_, err = nc.QueueSubscribe("tasks.reminder", "reminder-workers", func(msg *nats.Msg) {

		_, span := tracer.Start(context.Background(), "reminder-processing")
		defer span.End()

		var task ReminderTask

		err := json.Unmarshal(msg.Data, &task)

		if err != nil {
			log.Println(err)
			return
		}

		log.Printf("Sending reminder to %s\n", task.Patient)

		result := ReminderResult{
			Status: "success",
			Sent:   true,
		}

		data, _ := json.Marshal(result)

		nc.Publish("tasks.reminder.done", data)

		log.Println("Reminder sent")
	})

	if err != nil {
		log.Fatal(err)
	}

	select {}
}