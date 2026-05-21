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
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/trace"
)

type AppointmentTask struct {
	ID        string `json:"id"`
	Patient   string `json:"patient"`
	Date      string `json:"date"`
	Specialty string `json:"specialty,omitempty"`
}

type AppointmentResult struct {
	TaskID      string `json:"task_id"`
	Status      string `json:"status"`
	Message     string `json:"message"`
	AgentID     string `json:"agent_id"`
	AgentCost   int    `json:"agent_cost"`
	Appointment string `json:"appointment_id"`
}

type AuctionBid struct {
	AgentID   string  `json:"agent_id"`
	Cost      int     `json:"cost"`
	Skill     float64 `json:"skill"`
	Available bool    `json:"available"`
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
		log.Printf("OTLP exporter: %v", err)
		otel.SetTracerProvider(trace.NewTracerProvider())
		return
	}
	tp := trace.NewTracerProvider(trace.WithBatcher(exporter))
	otel.SetTracerProvider(tp)
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
	if err := nc.PublishMsg(resp); err != nil {
		log.Printf("ERROR respond: %v", err)
	}
}

func agentMeta() (string, int, float64) {
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
	skill := 0.85
	if raw := os.Getenv("AGENT_SKILL"); raw != "" {
		if v, err := strconv.ParseFloat(raw, 64); err == nil {
			skill = v
		}
	}
	return id, cost, skill
}

func main() {
	setupLogger()
	initTracer()

	agentID, agentCost, agentSkill := agentMeta()

	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = "nats://nats:4222"
	}

	nc, err := nats.Connect(natsURL)
	if err != nil {
		log.Fatal(err)
	}

	log.Printf("INFO Appointment Agent id=%s cost=%d skill=%.2f", agentID, agentCost, agentSkill)
	tracer := otel.Tracer(agentID)

	// Аукцион: каждый агент отвечает ставкой (не queue — все получают запрос)
	_, err = nc.Subscribe("tasks.auction", func(msg *nats.Msg) {
		ctx, span := tracer.Start(extractCtx(msg), "auction-bid")
		defer span.End()

		bid := AuctionBid{
			AgentID:   agentID,
			Cost:      agentCost,
			Skill:     agentSkill,
			Available: true,
		}
		data, _ := json.Marshal(bid)
		respondWithTrace(ctx, msg, nc, data)
		log.Printf("INFO auction bid sent agent=%s cost=%d", agentID, agentCost)
	})
	if err != nil {
		log.Fatal(err)
	}

	_, err = nc.QueueSubscribe("tasks.appointment", "appointment-workers", func(msg *nats.Msg) {
		ctx, span := tracer.Start(extractCtx(msg), "appointment-processing")
		defer span.End()

		var task AppointmentTask
		if err := json.Unmarshal(msg.Data, &task); err != nil {
			log.Printf("ERROR invalid payload: %v", err)
			return
		}

		log.Printf("INFO appointment patient=%s specialty=%s", task.Patient, task.Specialty)

		result := AppointmentResult{
			TaskID:      task.ID,
			Status:      "success",
			Message:     "Запись создана для " + task.Patient + " к " + task.Specialty,
			AgentID:     agentID,
			AgentCost:   agentCost,
			Appointment: "APT-" + task.ID[:8],
		}
		data, _ := json.Marshal(result)
		respondWithTrace(ctx, msg, nc, data)
	})
	if err != nil {
		log.Fatal(err)
	}

	select {}
}
