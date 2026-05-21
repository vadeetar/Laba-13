package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"

	"github.com/nats-io/nats.go"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/trace"
)

type FeedbackTask struct {
	ID      string `json:"id"`
	Patient string `json:"patient"`
	Rating  int    `json:"rating"`
}

type FeedbackResult struct {
	TaskID       string `json:"task_id"`
	Status       string `json:"status"`
	TotalCount   int64  `json:"total_feedbacks"`
	AverageScore string `json:"average_score"`
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

func main() {
	setupLogger()
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

	rdb := redis.NewClient(&redis.Options{Addr: redisAddr})
	if err := rdb.Ping(ctx).Err(); err != nil {
		log.Printf("ERROR redis ping: %v", err)
	} else {
		log.Println("INFO Feedback Agent restored Redis state")
	}

	nc, err := nats.Connect(natsURL)
	if err != nil {
		log.Fatal(err)
	}

	log.Println("INFO Feedback Agent connected")
	tracer := otel.Tracer("feedback-agent")

	_, err = nc.QueueSubscribe("tasks.feedback", "feedback-workers", func(msg *nats.Msg) {
		ctx, span := tracer.Start(extractCtx(msg), "feedback-processing")
		defer span.End()

		var task FeedbackTask
		if err := json.Unmarshal(msg.Data, &task); err != nil {
			log.Printf("ERROR invalid payload: %v", err)
			return
		}

		count, err := rdb.Incr(ctx, "total_feedbacks").Result()
		if err != nil {
			log.Printf("ERROR redis incr: %v", err)
			return
		}

		sum, _ := rdb.IncrBy(ctx, "feedback_score_sum", int64(task.Rating)).Result()
		avg := float64(sum) / float64(count)

		log.Printf("INFO feedback patient=%s rating=%d total=%d", task.Patient, task.Rating, count)

		result := FeedbackResult{
			TaskID:       task.ID,
			Status:       "saved",
			TotalCount:   count,
			AverageScore: fmt.Sprintf("%.1f", avg),
		}
		data, _ := json.Marshal(result)

		respondWithTrace(ctx, msg, nc, data)
	})
	if err != nil {
		log.Fatal(err)
	}

	select {}
}
