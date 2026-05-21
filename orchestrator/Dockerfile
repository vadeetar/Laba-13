FROM golang:1.24-alpine AS builder
WORKDIR /app
# Копируем всё содержимое
COPY . .
# Скачиваем зависимости и собираем
RUN go mod tidy && go build -o main .

FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/main .
CMD ["./main"]