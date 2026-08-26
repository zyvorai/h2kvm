// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"fmt"
	"strings"
	"testing"
	"time"
)

func TestFormatAgeSeconds(t *testing.T) {
	ts := time.Now().Add(-30 * time.Second)
	result := formatAge(ts)

	if !strings.HasSuffix(result, "s") {
		t.Errorf("expected result to end with 's' for seconds, got %q", result)
	}
	// Should be roughly "30s" but timing can vary by a second or two.
	if result != "30s" && result != "29s" && result != "31s" {
		t.Errorf("expected roughly '30s', got %q", result)
	}
}

func TestFormatAgeMinutes(t *testing.T) {
	ts := time.Now().Add(-5 * time.Minute)
	result := formatAge(ts)

	if !strings.HasSuffix(result, "m") {
		t.Errorf("expected result to end with 'm' for minutes, got %q", result)
	}
	if result != "5m" {
		t.Errorf("expected '5m', got %q", result)
	}
}

func TestFormatAgeHours(t *testing.T) {
	ts := time.Now().Add(-3 * time.Hour)
	result := formatAge(ts)

	if !strings.HasSuffix(result, "h") {
		t.Errorf("expected result to end with 'h' for hours, got %q", result)
	}
	if result != "3h" {
		t.Errorf("expected '3h', got %q", result)
	}
}

func TestFormatAgeDays(t *testing.T) {
	ts := time.Now().Add(-72 * time.Hour)
	result := formatAge(ts)

	if !strings.HasSuffix(result, "d") {
		t.Errorf("expected result to end with 'd' for days, got %q", result)
	}
	if result != "3d" {
		t.Errorf("expected '3d', got %q", result)
	}
}

func TestFormatAgeJustNow(t *testing.T) {
	ts := time.Now()
	result := formatAge(ts)

	if !strings.HasSuffix(result, "s") {
		t.Errorf("expected result to end with 's' for just now, got %q", result)
	}
	if result != "0s" {
		t.Errorf("expected '0s', got %q", result)
	}
}

func TestFormatAgeOneMinuteBoundary(t *testing.T) {
	// Exactly 59 seconds should be formatted as seconds.
	ts := time.Now().Add(-59 * time.Second)
	result := formatAge(ts)
	if !strings.HasSuffix(result, "s") {
		t.Errorf("expected 59s to be formatted as seconds, got %q", result)
	}
}

func TestFormatAgeOneHourBoundary(t *testing.T) {
	// Exactly 59 minutes should be formatted as minutes.
	ts := time.Now().Add(-59 * time.Minute)
	result := formatAge(ts)
	if !strings.HasSuffix(result, "m") {
		t.Errorf("expected 59m to be formatted as minutes, got %q", result)
	}
}

func TestFormatAge23Hours(t *testing.T) {
	// 23 hours should be formatted as hours.
	ts := time.Now().Add(-23 * time.Hour)
	result := formatAge(ts)
	if !strings.HasSuffix(result, "h") {
		t.Errorf("expected 23h to be formatted as hours, got %q", result)
	}
	if result != "23h" {
		t.Errorf("expected '23h', got %q", result)
	}
}

func TestFormatAge24Hours(t *testing.T) {
	// Exactly 24 hours should be formatted as days.
	ts := time.Now().Add(-24 * time.Hour)
	result := formatAge(ts)
	if !strings.HasSuffix(result, "d") {
		t.Errorf("expected 24h to be formatted as days, got %q", result)
	}
	if result != "1d" {
		t.Errorf("expected '1d', got %q", result)
	}
}

func TestFormatAgeManyDays(t *testing.T) {
	ts := time.Now().Add(-30 * 24 * time.Hour)
	result := formatAge(ts)

	if result != "30d" {
		t.Errorf("expected '30d', got %q", result)
	}
}

func TestIsNoMatchErrorNotFound(t *testing.T) {
	// Test with a string-based error containing the known message.
	err := fmt.Errorf("the server could not find the requested resource")
	if !isNoMatchError(err) {
		t.Error("expected isNoMatchError to return true for resource-not-found message")
	}
}

func TestIsNoMatchErrorGenericError(t *testing.T) {
	err := fmt.Errorf("connection refused")
	if isNoMatchError(err) {
		t.Error("expected isNoMatchError to return false for generic error")
	}
}

func TestIsNoMatchErrorTimeout(t *testing.T) {
	err := fmt.Errorf("context deadline exceeded")
	if isNoMatchError(err) {
		t.Error("expected isNoMatchError to return false for timeout error")
	}
}

func TestIsNoMatchErrorWrapped(t *testing.T) {
	inner := fmt.Errorf("the server could not find the requested resource")
	err := fmt.Errorf("list VMs: %w", inner)
	if !isNoMatchError(err) {
		t.Error("expected isNoMatchError to return true for wrapped resource-not-found message")
	}
}

func TestIsNoMatchErrorEmptyMessage(t *testing.T) {
	err := fmt.Errorf("")
	if isNoMatchError(err) {
		t.Error("expected isNoMatchError to return false for empty error message")
	}
}

func TestKubeConfigAvailableDoesNotPanic(t *testing.T) {
	// KubeConfigAvailable should not panic regardless of environment.
	// It may return true or false depending on whether kubeconfig exists.
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("KubeConfigAvailable panicked: %v", r)
		}
	}()

	_ = KubeConfigAvailable()
}

func TestGVRValues(t *testing.T) {
	// Verify the GVR constants are set correctly.
	if gvrKubeVirt.Group != "kubevirt.io" {
		t.Errorf("expected gvrKubeVirt.Group %q, got %q", "kubevirt.io", gvrKubeVirt.Group)
	}
	if gvrKubeVirt.Version != "v1" {
		t.Errorf("expected gvrKubeVirt.Version %q, got %q", "v1", gvrKubeVirt.Version)
	}
	if gvrKubeVirt.Resource != "kubevirts" {
		t.Errorf("expected gvrKubeVirt.Resource %q, got %q", "kubevirts", gvrKubeVirt.Resource)
	}

	if gvrCDI.Group != "cdi.kubevirt.io" {
		t.Errorf("expected gvrCDI.Group %q, got %q", "cdi.kubevirt.io", gvrCDI.Group)
	}
	if gvrCDI.Version != "v1beta1" {
		t.Errorf("expected gvrCDI.Version %q, got %q", "v1beta1", gvrCDI.Version)
	}

	if gvrVMI.Resource != "virtualmachineinstances" {
		t.Errorf("expected gvrVMI.Resource %q, got %q", "virtualmachineinstances", gvrVMI.Resource)
	}

	if gvrVM.Resource != "virtualmachines" {
		t.Errorf("expected gvrVM.Resource %q, got %q", "virtualmachines", gvrVM.Resource)
	}

	if gvrVMIMigration.Resource != "virtualmachineinstancemigrations" {
		t.Errorf("expected gvrVMIMigration.Resource %q, got %q", "virtualmachineinstancemigrations", gvrVMIMigration.Resource)
	}
}
