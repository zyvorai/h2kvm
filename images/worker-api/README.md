# hyper2kvm Worker API - Docker Image

Production-ready Docker image for the hyper2kvm Worker Job Protocol REST API.

## Quick Start

```bash
# Pull from GitHub Container Registry
docker pull ghcr.io/ssahani/hyper2kvm-worker-api:latest

# Run container
docker run -p 8000:8000 ghcr.io/ssahani/hyper2kvm-worker-api:latest
```

Access:
- **API:** http://localhost:8000
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Build

```bash
# From repository root
docker build -t hyper2kvm-worker-api:latest -f images/worker-api/Dockerfile .

# Multi-architecture build
docker buildx build --platform linux/amd64,linux/arm64 \
  -t ghcr.io/ssahani/hyper2kvm-worker-api:latest \
  -f images/worker-api/Dockerfile \
  --push .
```

## Configuration

### Environment Variables

- `UVICORN_HOST` - Bind address (default: `0.0.0.0`)
- `UVICORN_PORT` - Port number (default: `8000`)
- `UVICORN_LOG_LEVEL` - Log level (default: `info`)
- `UVICORN_WORKERS` - Worker count (default: `1`)

### Volumes

Mount for persistent state:

```bash
docker run -p 8000:8000 \
  -v /var/lib/hyper2kvm:/var/lib/hyper2kvm \
  ghcr.io/ssahani/hyper2kvm-worker-api:latest
```

Directories:
- `/var/lib/hyper2kvm/jobs` - Job state machines
- `/var/lib/hyper2kvm/events` - Progress events
- `/var/lib/hyper2kvm/queue` - Job queue

## Production Deployment

### Docker Compose

```yaml
version: '3.8'

services:
  api:
    image: ghcr.io/ssahani/hyper2kvm-worker-api:latest
    ports:
      - "8000:8000"
    volumes:
      - hyper2kvm-data:/var/lib/hyper2kvm
    environment:
      UVICORN_LOG_LEVEL: info
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  hyper2kvm-data:
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hyper2kvm-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: hyper2kvm-api
  template:
    metadata:
      labels:
        app: hyper2kvm-api
    spec:
      containers:
      - name: api
        image: ghcr.io/ssahani/hyper2kvm-worker-api:latest
        ports:
        - containerPort: 8000
        volumeMounts:
        - name: data
          mountPath: /var/lib/hyper2kvm
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: hyper2kvm-data
---
apiVersion: v1
kind: Service
metadata:
  name: hyper2kvm-api
spec:
  selector:
    app: hyper2kvm-api
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

## Security

### Non-Root User

Image runs as non-root user `hyper2kvm` (UID 1000) for security.

### Health Check

Built-in health check on `/health` endpoint:
- Interval: 30s
- Timeout: 10s
- Retries: 3

### Minimal Base

Uses Python 3.11 slim image for reduced attack surface.

## Monitoring

### Prometheus Metrics

Metrics available at `/metrics`:

```bash
curl http://localhost:8000/metrics
```

### Logs

View logs:

```bash
docker logs -f <container-id>
```

## Troubleshooting

### Check Health

```bash
curl http://localhost:8000/health
```

### Debug Mode

```bash
docker run -p 8000:8000 \
  -e UVICORN_LOG_LEVEL=debug \
  ghcr.io/ssahani/hyper2kvm-worker-api:latest
```

### Access Shell

```bash
docker exec -it <container-id> /bin/bash
```

## Image Details

- **Base:** python:3.11-slim
- **Size:** ~150MB
- **User:** hyper2kvm (UID 1000)
- **Exposed Ports:** 8000
- **Architectures:** linux/amd64, linux/arm64

## See Also

- [REST API Documentation](../../docs/worker/REST_API.md)
- [Worker Protocol Specification](../../docs/worker/PROTOCOL_SPEC.md)
- [Kubernetes Deployment Guide](../../k8s/README.md)
