FROM golang:1.25-alpine as builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY main.go .
RUN CGO_ENABLED=0 GOOS=linux go build -o triage-agent .

FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/triage-agent .
CMD ["./triage-agent"]
