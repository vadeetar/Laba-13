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

type TriageTask struct {
	Patient string `json:"patient"`
	Symptoms string `json:"symptoms"`
}

type TriageResult struct {
	Priority string `json:"priority"`
	Action   string `json:"action"`
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

	log.Println("Triage Agent connected")

	tracer := otel.Tracer("triage-agent")

	_, err = nc.QueueSubscribe("tasks.triage", "triage-workers", func(msg *nats.Msg) {

		_, span := tracer.Start(context.Background(), "triage-processing")
		defer span.End()

		var task TriageTask

		err := json.Unmarshal(msg.Data, &task)

		if err != nil {
			log.Println(err)
			return
		}

		log.Printf("Analyzing symptoms: %s\n", task.Symptoms)

		result := TriageResult{
			Priority: "HIGH",
			Action:   "Visit doctor immediately",
		}

		data, _ := json.Marshal(result)

		nc.Publish("tasks.triage.done", data)
	})

	if err != nil {
		log.Fatal(err)
	}

	select {}
}