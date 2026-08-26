// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


// h2kweb is the hyper2kvm web dashboard server.
// It provides a browser-based UI for VM migration with provider browsing
// (VMware vSphere, Azure, EC2) and real-time job monitoring via WebSocket.
package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/json"
	"encoding/pem"
	"flag"
	"fmt"
	"log"
	"math/big"
	"net"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/hyper2kvm/web/internal/adapters/azure"
	"github.com/hyper2kvm/web/internal/adapters/ec2"
	"github.com/hyper2kvm/web/internal/adapters/vsphere"
	"github.com/hyper2kvm/web/internal/api"
	"github.com/hyper2kvm/web/internal/domain"
	"github.com/hyper2kvm/web/internal/jobs"
	"github.com/hyper2kvm/web/internal/ports"
	"github.com/hyper2kvm/web/internal/registry"
	"github.com/hyper2kvm/web/internal/runner"
)

var (
	version = "0.1.0"
)

func main() {
	// Flags.
	addr := flag.String("addr", ":5070", "HTTP listen address")
	binaryPath := flag.String("binary", "", "Path to h2kvmctl binary (auto-detect if empty)")
	apiKey := flag.String("api-key", "", "API key for authentication (disabled if empty)")
	staticDir := flag.String("static-dir", "", "Path to dashboard static files (auto-detect if empty)")
	tlsCert := flag.String("tls-cert", "auto", "TLS certificate file (default: auto-generate self-signed; use 'none' to disable HTTPS)")
	tlsKey := flag.String("tls-key", "", "TLS private key file")
	showVersion := flag.Bool("version", false, "Print version and exit")
	flag.Parse()

	if *showVersion {
		fmt.Printf("h2kweb %s\n", version)
		os.Exit(0)
	}

	log.Printf("h2kweb %s starting", version)

	// Ensure runtime directories exist (NBD locking, workflow).
	for _, dir := range []string{"/run/hyper2kvm", "/run/hyper2kvm/workflow"} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			log.Printf("warning: cannot create %s: %v", dir, err)
		}
	}

	// Create components.
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// WebSocket hub.
	wsHub := api.NewWSHub()
	go wsHub.Run(ctx)

	// h2kvmctl runner.
	h2kRunner := runner.New(*binaryPath)
	log.Printf("h2kvmctl binary: %s", h2kRunner.BinaryPath())

	// Job manager.
	jobManager := jobs.NewManager(ctx, h2kRunner, wsHub)

	// Provider registry.
	reg := registry.New()
	reg.RegisterFactory(domain.ProviderVSphere, func() ports.ComputeProvider {
		return vsphere.New()
	})
	reg.RegisterFactory(domain.ProviderAzure, func() ports.ComputeProvider {
		return azure.New()
	})
	reg.RegisterFactory(domain.ProviderEC2, func() ports.ComputeProvider {
		return ec2.New()
	})

	// TLS: default is auto (self-signed), use "none" to disable.
	certFile, keyFile := *tlsCert, *tlsKey
	if certFile == "none" {
		certFile, keyFile = "", ""
	} else if certFile == "auto" {
		certFile, keyFile = generateSelfSignedCert()
		log.Printf("auto-generated self-signed TLS cert: %s", certFile)
	}

	// Log resolved paths.
	log.Printf("[api] resolved paths: binary=%s staticDir=%s", h2kRunner.BinaryPath(), *staticDir)
	if certFile != "" {
		log.Printf("[tls] cert=%s key=%s", certFile, keyFile)
	} else {
		log.Printf("[tls] disabled (plain HTTP)")
	}

	// API server.
	srv := api.NewServer(api.ServerConfig{
		Addr:      *addr,
		APIKey:    *apiKey,
		StaticDir: *staticDir,
		TLSCert:   certFile,
		TLSKey:    keyFile,
	}, jobManager, reg, wsHub)

	// Start stale upload cleanup goroutine.
	go cleanupStaleUploads(ctx)

	// Start server in background.
	errCh := make(chan error, 1)
	go func() {
		errCh <- srv.Start()
	}()

	proto := "http"
	if certFile != "" {
		proto = "https"
	}
	log.Printf("listening on %s://%s", proto, *addr)

	// Wait for signal or error.
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	select {
	case sig := <-sigCh:
		log.Printf("received signal %s, shutting down", sig)
	case err := <-errCh:
		if err != nil {
			log.Printf("server error: %v", err)
		}
	}

	// Graceful shutdown.
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	reg.DisconnectAll(shutdownCtx)
	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Printf("shutdown error: %v", err)
		os.Exit(1)
	}

	log.Println("shutdown complete")
}

// cleanupStaleUploads runs every hour and removes chunked upload sessions
// older than 24 hours. It reads meta.json from each session directory to
// determine the creation time.
func cleanupStaleUploads(ctx context.Context) {
	const uploadsDir = "/var/lib/hyper2kvm/input/.uploads"
	const maxAge = 24 * time.Hour

	ticker := time.NewTicker(1 * time.Hour)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			log.Printf("[cleanup] scanning for stale upload sessions in %s", uploadsDir)
			entries, err := os.ReadDir(uploadsDir)
			if err != nil {
				// Directory may not exist yet; that is fine.
				continue
			}
			removedCount := 0
			for _, entry := range entries {
				if !entry.IsDir() {
					continue
				}
				sessionDir := filepath.Join(uploadsDir, entry.Name())
				metaPath := filepath.Join(sessionDir, "meta.json")

				data, err := os.ReadFile(metaPath)
				if err != nil {
					continue
				}

				var meta struct {
					CreatedAt string `json:"created_at"`
				}
				if err := json.Unmarshal(data, &meta); err != nil {
					continue
				}

				created, err := time.Parse(time.RFC3339, meta.CreatedAt)
				if err != nil {
					continue
				}

				if time.Since(created) > maxAge {
					if err := os.RemoveAll(sessionDir); err != nil {
						log.Printf("[cleanup] failed to remove stale upload session %s: %v", entry.Name(), err)
					} else {
						log.Printf("[cleanup] removed stale upload session %s (created %s)", entry.Name(), meta.CreatedAt)
						removedCount++
					}
				}
			}
			log.Printf("[cleanup] scan complete: %d sessions found, %d removed", len(entries), removedCount)
		}
	}
}

// generateSelfSignedCert creates a self-signed TLS certificate and key
// in /var/lib/hyper2kvm/tls/ and returns the file paths.
func generateSelfSignedCert() (certFile, keyFile string) {
	dir := "/var/lib/hyper2kvm/tls"
	certFile = filepath.Join(dir, "server.crt")
	keyFile = filepath.Join(dir, "server.key")

	// Reuse existing cert if present.
	if _, err := os.Stat(certFile); err == nil {
		if _, err := os.Stat(keyFile); err == nil {
			return certFile, keyFile
		}
	}

	os.MkdirAll(dir, 0700)

	// Generate ECDSA P-256 key.
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		log.Fatalf("generate TLS key: %v", err)
	}

	// Build certificate template.
	hostname, _ := os.Hostname()
	template := x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      pkix.Name{Organization: []string{"hyper2kvm"}, CommonName: hostname},
		NotBefore:    time.Now(),
		NotAfter:     time.Now().Add(365 * 24 * time.Hour), // 1 year
		KeyUsage:     x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		DNSNames:     []string{hostname, "localhost"},
		IPAddresses:  []net.IP{net.ParseIP("127.0.0.1")},
	}

	// Add all host IPs as SANs.
	if addrs, err := net.InterfaceAddrs(); err == nil {
		for _, a := range addrs {
			if ipnet, ok := a.(*net.IPNet); ok && !ipnet.IP.IsLoopback() {
				template.IPAddresses = append(template.IPAddresses, ipnet.IP)
			}
		}
	}

	// Self-sign.
	certDER, err := x509.CreateCertificate(rand.Reader, &template, &template, &key.PublicKey, key)
	if err != nil {
		log.Fatalf("create TLS cert: %v", err)
	}

	// Write cert.
	cf, err := os.Create(certFile)
	if err != nil {
		log.Fatalf("write TLS cert: %v", err)
	}
	pem.Encode(cf, &pem.Block{Type: "CERTIFICATE", Bytes: certDER})
	cf.Close()

	// Write key.
	keyDER, err := x509.MarshalECPrivateKey(key)
	if err != nil {
		log.Fatalf("marshal TLS key: %v", err)
	}
	kf, err := os.OpenFile(keyFile, os.O_CREATE|os.O_WRONLY, 0600)
	if err != nil {
		log.Fatalf("write TLS key: %v", err)
	}
	pem.Encode(kf, &pem.Block{Type: "EC PRIVATE KEY", Bytes: keyDER})
	kf.Close()

	return certFile, keyFile
}
