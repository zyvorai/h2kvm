.PHONY: build dev frontend backend clean test install uninstall restart status logs

PREFIX   ?= /usr/local
BINDIR    = $(PREFIX)/bin
SHAREDIR  = $(PREFIX)/share/h2kweb
SYSTEMD   = /etc/systemd/system

# Build both frontend and backend
build: frontend backend
	@echo "Build complete: ./h2kweb ($(shell du -h h2kweb | cut -f1))"

# Build React dashboard
frontend:
	cd dashboard && npm ci --silent && npm run build

# Build Go binary
backend:
	go build -o h2kweb .

# Install binary, static files, systemd service, and start
install: build
	@echo "Installing h2kweb..."
	install -Dm755 h2kweb $(DESTDIR)$(BINDIR)/h2kweb
	install -dm755 $(DESTDIR)$(SHAREDIR)
	cp -r dashboard/dist $(DESTDIR)$(SHAREDIR)/dashboard
	install -Dm644 h2kweb.service $(DESTDIR)$(SYSTEMD)/h2kweb.service
	install -Dm644 h2kweb.default $(DESTDIR)/etc/default/h2kweb
	@# Patch service to point static dir to installed location
	sed -i 's|ExecStart=.*|ExecStart=$(BINDIR)/h2kweb --addr $${H2KWEB_ADDR} --static-dir $(SHAREDIR)/dashboard|' \
		$(DESTDIR)$(SYSTEMD)/h2kweb.service
	systemctl daemon-reload
	systemctl enable --now h2kweb.service
	@echo ""
	@echo "h2kweb installed and running on :5070"
	@echo "  Dashboard: http://localhost:5070"
	@echo "  Logs:      journalctl -u h2kweb -f"
	@echo "  Config:    /etc/default/h2kweb"

# Uninstall
uninstall:
	systemctl disable --now h2kweb.service 2>/dev/null || true
	rm -f $(DESTDIR)$(BINDIR)/h2kweb
	rm -rf $(DESTDIR)$(SHAREDIR)
	rm -f $(DESTDIR)$(SYSTEMD)/h2kweb.service
	rm -f $(DESTDIR)/etc/default/h2kweb
	systemctl daemon-reload
	@echo "h2kweb uninstalled"

# Shortcuts
restart:
	systemctl restart h2kweb

status:
	systemctl status h2kweb

logs:
	journalctl -u h2kweb -f

# Development: run frontend dev server + Go backend
dev:
	@echo "Starting dev mode..."
	@echo "  Frontend: http://localhost:5173"
	@echo "  Backend:  http://localhost:9090"
	cd dashboard && npm run dev &
	go run . --addr :5070

# Run Go tests
test:
	go test ./...

# Clean build artifacts
clean:
	rm -f h2kweb
	rm -rf dashboard/dist
