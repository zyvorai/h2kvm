// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os/exec"
	"time"
)

// NotificationConfig controls how completion/failure alerts are delivered.
type NotificationConfig struct {
	DesktopEnabled bool   // Use notify-send / osascript
	WebhookURL     string // HTTP POST endpoint
	OnCompletion   bool   // Notify on success
	OnFailure      bool   // Notify on failure
}

// SendNotification dispatches an alert through all enabled channels.
func SendNotification(cfg NotificationConfig, title, message string) {
	if cfg.DesktopEnabled {
		_ = sendDesktopNotification(title, message)
	}
	if cfg.WebhookURL != "" {
		_ = sendWebhook(cfg.WebhookURL, title, message)
	}
}

// sendDesktopNotification uses notify-send (Linux) to show a desktop alert.
func sendDesktopNotification(title, message string) error {
	if path, err := exec.LookPath("notify-send"); err == nil {
		cmd := exec.Command(path, "--app-name=hyper2kvm", title, message)
		return cmd.Run()
	}
	return fmt.Errorf("notify-send not found — install libnotify for desktop notifications: sudo dnf install libnotify (Fedora/RHEL) or sudo apt install libnotify-bin (Debian/Ubuntu)")
}

// sendWebhook POSTs a JSON payload to the configured URL.
func sendWebhook(url, title, message string) error {
	payload := map[string]string{
		"title":   title,
		"message": message,
		"source":  "zkvm",
		"time":    time.Now().Format(time.RFC3339),
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Post(url, "application/json", bytes.NewReader(body))
	if err != nil {
		return err
	}
	resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("webhook notification failed with HTTP %d — verify the webhook URL %q is correct and the endpoint is accepting POST requests", resp.StatusCode, url)
	}
	return nil
}
