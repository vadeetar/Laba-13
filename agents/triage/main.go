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
	"go.opentelemetry.io/otel/propagation"
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

func extractCtx(msg *nats.Msg) context.Context {
	ctx := context.Background()
	if msg.Header == nil {
		return ctx
	}
	carrier := propagation.MapCarrier{}
	for k, vals := range msg.Header {
		if len(vals) > 0 {
			carrier[k] = vals[0]
		}
	}
	return otel.GetTextMapPropagator().Extract(ctx, carrier)
}

func respondWithTrace(ctx context.Context, msg *nats.Msg, nc *nats.Conn, data []byte) {
	if msg.Reply == "" {
		return
	}
	resp := nats.NewMsg(msg.Reply)
	resp.Data = data
	if resp.Header == nil {
		resp.Header = nats.Header{}
	}
	carrier := propagation.MapCarrier{}
	otel.GetTextMapPropagator().Inject(ctx, carrier)
	for k, v := range carrier {
		resp.Header.Set(k, v)
	}
	_ = nc.PublishMsg(resp)
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
		ctx, span := tracer.Start(extractCtx(msg), "triage-processing")
		defer span.End()

		var task TriageTask
		if err := json.Unmarshal(msg.Data, &task); err != nil {
			log.Printf("ERROR invalid payload: %v", err)
			return
		}

		log.Printf("INFO triage patient=%s symptoms=%v", task.Patient, task.Symptoms)
		result := processTriage(task)
		data, _ := json.Marshal(result)

		respondWithTrace(ctx, msg, nc, data)
	})
	if err != nil {
		log.Fatal(err)
	}

	select {}
}
