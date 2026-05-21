FROM golang:1.25-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go mod tidy && CGO_ENABLED=0 GOOS=linux go build -o main .

FROM alpine:latest
RUN mkdir -p /app/logs
WORKDIR /root/
COPY --from=builder /app/main .
CMD ["./main"]
