# SPDX-License-Identifier: Apache-2.0
# Makefile for zkvm (Go Bubble Tea TUI)

BINARY   := zkvm
MODULE   := github.com/hyper2kvm/zkvm
VERSION  ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
LDFLAGS  := -s -w -X main.version=$(VERSION)
GOFLAGS  ?=
PREFIX   ?= /usr/local

.PHONY: all build clean install uninstall fmt vet test cross-compile

all: build

build:
	go build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(BINARY) .

clean:
	rm -f $(BINARY) $(BINARY)-*

install: build
	install -Dm755 $(BINARY) $(DESTDIR)$(PREFIX)/bin/$(BINARY)

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/$(BINARY)

fmt:
	gofmt -s -w .

vet:
	go vet ./...

test:
	go test ./...

# Cross-compile for all platforms
cross-compile:
	GOOS=linux   GOARCH=amd64 go build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(BINARY)-linux-amd64 .
	GOOS=linux   GOARCH=arm64 go build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(BINARY)-linux-arm64 .
	GOOS=darwin  GOARCH=amd64 go build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(BINARY)-darwin-amd64 .
	GOOS=darwin  GOARCH=arm64 go build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(BINARY)-darwin-arm64 .
	@echo "Built: $(BINARY)-{linux,darwin}-{amd64,arm64}"

# Build for macOS only
build-macos:
	GOOS=darwin GOARCH=arm64 go build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(BINARY)-darwin-arm64 .
	GOOS=darwin GOARCH=amd64 go build $(GOFLAGS) -ldflags "$(LDFLAGS)" -o $(BINARY)-darwin-amd64 .
	@echo "Built: $(BINARY)-darwin-{amd64,arm64}"
