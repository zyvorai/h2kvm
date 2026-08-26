// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package models

// Statistics holds aggregated migration metrics.
type Statistics struct {
	TotalMigrations  int     `json:"total_migrations"`
	ActiveMigrations int     `json:"active_migrations"`
	CompletedToday   int     `json:"completed_today"`
	SuccessRate      float64 `json:"success_rate"`
	TotalCompleted   int     `json:"total_completed"`
	TotalFailed      int     `json:"total_failed"`
	AvgDuration      float64 `json:"avg_duration_seconds"`
}
