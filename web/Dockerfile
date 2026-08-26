# Build stage
FROM golang:1.23-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o h2kweb .

# Frontend build
FROM node:20-alpine AS frontend
WORKDIR /build
COPY dashboard/package*.json ./
RUN npm ci
COPY dashboard/ .
RUN npm run build

# Runtime
FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=builder /build/h2kweb /usr/local/bin/
COPY --from=frontend /build/dist /usr/local/share/h2kweb/dashboard/
EXPOSE 5070
ENTRYPOINT ["h2kweb", "--addr", ":5070", "--static-dir", "/usr/local/share/h2kweb/dashboard"]
