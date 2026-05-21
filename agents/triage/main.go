package main
import (
    "context"
    "os"
    "github.com/nats-io/nats.go"
    "github.com/redis/go-redis/v9"
)

func main() {
    // ВАЖНО: используем переменную среды для хоста
    nc, _ := nats.Connect(os.Getenv("NATS_URL"))
    rdb := redis.NewClient(&redis.Options{
        Addr: "redis:6379", // Имя сервиса в docker-compose
    })

    // ... остальной код подписки NATS
}