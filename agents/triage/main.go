package main

import (
	"context"
	"encoding/json"
	"io"
	"log"
	"os"
	"strings"

	"github.com/nats-io/nats.go"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/trace"
)

type TriageTask struct {
	ID       string `json:"id"`
	Patient  string `json:"patient"`
	Symptoms any    `json:"symptoms"`
}

type TriageResult struct {
	TaskID    string `json:"task_id"`
	Priority  string `json:"priority"`
	Specialty string `json:"specialty"`
	Action    string `json:"action"`
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

func symptomsText(symptoms any) string {
	switch v := symptoms.(type) {
	case string:
		return v
	case []any:
		parts := make([]string, 0, len(v))
		for _, item := range v {
			if s, ok := item.(string); ok {
				parts = append(parts, s)
			}
		}
		return strings.Join(parts, ", ")
	default:
		return ""
	}
}

func processTriage(task TriageTask) TriageResult {
	text := strings.ToLower(symptomsText(task.Symptoms))
	priority := "NORMAL"
	specialty := "терапевт"
	action := "Запланировать плановый приём"

	urgent := []string{"chest pain", "боль в груди", "одышка", "потеря сознания", "кровь"}
	for _, kw := range urgent {
		if strings.Contains(text, kw) {
			priority = "HIGH"
			specialty = "кардиолог"
			action = "Срочный приём в течение 24 часов"
			break
		}
	}

	if strings.Contains(text, "fever") || strings.Contains(text, "температура") {
		if priority != "HIGH" {
			priority = "MEDIUM"
			specialty = "инфекционист"
			action = "Приём в ближайшие 2–3 дня"
		}
	}

	return TriageResult{
		TaskID:    task.ID,
		Priority:  priority,
		Specialty: specialty,
		Action:    action,
	}
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

	log.Println("INFO Triage Agent connected")
	tracer := otel.Tracer("triage-agent")

	_, err = nc.QueueSubscribe("tasks.triage", "triage-workers", func(msg *nats.Msg) {
		_, span := tracer.Start(context.Background(), "triage-processing")
		defer span.End()

		var task TriageTask
		if err := json.Unmarshal(msg.Data, &task); err != nil {
			log.Printf("ERROR invalid payload: %v", err)
			return
		}

		log.Printf("INFO triage patient=%s symptoms=%v", task.Patient, task.Symptoms)
		result := processTriage(task)
		data, _ := json.Marshal(result)

		if msg.Reply != "" {
			if err := msg.Respond(data); err != nil {
				log.Printf("ERROR respond: %v", err)
			}
		} else {
			_ = nc.Publish("tasks.triage.done", data)
		}
	})
	if err != nil {
		log.Fatal(err)
	}

	select {}
}
