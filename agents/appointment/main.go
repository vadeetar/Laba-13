package main

import (
	"context"
	"encoding/json"
	"io"
	"log"
	"os"
	"strconv"

	"github.com/nats-io/nats.go"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/trace"
)

type AppointmentTask struct {
	ID        string `json:"id"`
	Patient   string `json:"patient"`
	Date      string `json:"date"`
	Specialty string `json:"specialty,omitempty"`
	AgentCost int    `json:"agent_cost,omitempty"`
}

type AppointmentResult struct {
	TaskID      string `json:"task_id"`
	Status      string `json:"status"`
	Message     string `json:"message"`
	AgentID     string `json:"agent_id"`
	AgentCost   int    `json:"agent_cost"`
	Appointment string `json:"appointment_id"`
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

func agentMeta() (string, int) {
	id := os.Getenv("AGENT_ID")
	if id == "" {
		id = "appointment-agent"
	}
	cost := 3
	if raw := os.Getenv("AGENT_COST"); raw != "" {
		if v, err := strconv.Atoi(raw); err == nil {
			cost = v
		}
	}
	return id, cost
}

func main() {
	setupLogger()
	initTracer()

	agentID, agentCost := agentMeta()

	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = "nats://nats:4222"
	}

	nc, err := nats.Connect(natsURL)
	if err != nil {
		log.Fatal(err)
	}

	log.Printf("INFO Appointment Agent connected id=%s cost=%d", agentID, agentCost)
	tracer := otel.Tracer(agentID)

	_, err = nc.QueueSubscribe("tasks.appointment", "appointment-workers", func(msg *nats.Msg) {
		_, span := tracer.Start(context.Background(), "appointment-processing")
		defer span.End()

		var task AppointmentTask
		if err := json.Unmarshal(msg.Data, &task); err != nil {
			log.Printf("ERROR invalid payload: %v", err)
			return
		}

		log.Printf("INFO appointment patient=%s date=%s specialty=%s", task.Patient, task.Date, task.Specialty)

		result := AppointmentResult{
			TaskID:      task.ID,
			Status:      "success",
			Message:     "Запись создана для " + task.Patient + " к " + task.Specialty,
			AgentID:     agentID,
			AgentCost:   agentCost,
			Appointment: "APT-" + task.ID[:8],
		}
		data, _ := json.Marshal(result)

		if msg.Reply != "" {
			if err := msg.Respond(data); err != nil {
				log.Printf("ERROR respond: %v", err)
			}
		} else {
			_ = nc.Publish("tasks.appointment.done", data)
		}
		log.Println("INFO appointment processed")
	})
	if err != nil {
		log.Fatal(err)
	}

	select {}
}
