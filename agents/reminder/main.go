package main
import (
    "log"
    "github.com/nats-io/nats.go"
    "time"
)
func main() {
    nc, err := nats.Connect("nats://nats:4222")
    if err != nil { log.Fatal(err) }
    log.Println("Reminder Agent connected to NATS")
    select {}
}
