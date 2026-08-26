// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package models

// PauseMigrationMsg requests pausing a migration by ID.
type PauseMigrationMsg struct{ ID string }

// ResumeMigrationMsg requests resuming a migration by ID.
type ResumeMigrationMsg struct{ ID string }

// CancelMigrationMsg requests cancelling a migration by ID.
type CancelMigrationMsg struct{ ID string }

// BatchStartItem represents a single VM to start in a batch.
type BatchStartItem struct {
	VMName     string
	SourceType string
	SourcePath string
}

// BatchStartAllMsg signals the app to start queued batch migrations via backend.
type BatchStartAllMsg struct {
	Items []BatchStartItem
}

// BatchCancelAllMsg signals the app to cancel running batch migrations.
type BatchCancelAllMsg struct {
	IDs []string
}
