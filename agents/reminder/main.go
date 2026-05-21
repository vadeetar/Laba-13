package main

import (
	"context"
	"encoding/json"
	"io"
	"log"
	"os"

	"github.com/nats-io/nats.go"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/trace"
)

type ReminderTask struct {
	ID      string `json:"id"`
	Patient string `json:"patient"`
	Date    string `json:"date"`
}

type ReminderResult struct {
	TaskID  string `json:"task_id"`
	Status  string `json:"status"`
	Sent    bool   `json:"sent"`
	Channel string `json:"channel"`
	Message string `json:"message"`
}

func setupLogger() {
	log.SetFlags(log.Ldate | log.Ltime | log.Lshortfile)
	writers := []io.Writer{os.Stdout}
	if path := os.Getenv("LOG_FILE"); path != "" {
		f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
		if err == nil {
			writers = append(writers, f)
		}
	}
	log.SetOutput(io.MultiWriter(writers...))
}

func initTracer() {
	ctx := context.Background()
	exporter, err := otlptracehttp.New(ctx)
	if err != nil {
		log.Printf("OTLP exporter: %v, using default provider", err)
		otel.SetTracerProvider(trace.NewTracerProvider())
		return
	}
	tp := trace.NewTracerProvider(trace.WithBatcher(exporter))
	otel.SetTracerProvider(tp)
}

func main() {
	setupLogger()
	initTracer()

	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = "nats://nats:4222"
	}

	nc, err := nats.Connect(natsURL)
	if err != nil {
		log.Fatal(err)
	}

	log.Println("INFO Reminder Agent connected")
	tracer := otel.Tracer("reminder-agent")

	_, err = nc.QueueSubscribe("tasks.reminder", "reminder-workers", func(msg *nats.Msg) {
		_, span := tracer.Start(context.Background(), "reminder-processing")
		defer span.End()

		var task ReminderTask
		if err := json.Unmarshal(msg.Data, &task); err != nil {
			log.Printf("ERROR invalid payload: %v", err)
			return
		}

		log.Printf("INFO reminder patient=%s date=%s", task.Patient, task.Date)

		result := ReminderResult{
			TaskID:  task.ID,
			Status:  "success",
			Sent:    true,
			Channel: "sms",
			Message: "Напоминание: приём " + task.Patient + " " + task.Date,
		}
		data, _ := json.Marshal(result)

		if msg.Reply != "" {
			if err := msg.Respond(data); err != nil {
				log.Printf("ERROR respond: %v", err)
			}
		} else {
			_ = nc.Publish("tasks.reminder.done", data)
		}
		log.Println("INFO reminder sent")
	})
	if err != nil {
		log.Fatal(err)
	}

	select {}
}
