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

type AppointmentTask struct {
	ID      string `json:"id"`
	Patient string `json:"patient"`
	Date    string `json:"date"`
}

type AppointmentResult struct {
	Status  string `json:"status"`
	Message string `json:"message"`
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

	log.Println("Appointment Agent connected to NATS")

	tracer := otel.Tracer("appointment-agent")

	_, err = nc.QueueSubscribe("tasks.appointment", "appointment-workers", func(msg *nats.Msg) {

		ctx, span := tracer.Start(context.Background(), "appointment-processing")
		defer span.End()

		var task AppointmentTask

		err := json.Unmarshal(msg.Data, &task)

		if err != nil {
			log.Println(err)
			return
		}

		log.Printf("Appointment request: %+v\n", task)

		result := AppointmentResult{
			Status:  "success",
			Message: "Appointment created for " + task.Patient,
		}

		data, _ := json.Marshal(result)

		nc.Publish("tasks.appointment.done", data)

		log.Println("Appointment processed")

		_ = ctx
	})

	if err != nil {
		log.Fatal(err)
	}

	select {}
}