// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

package api

import (
	"os"
	"testing"
	"time"
)

func TestIsProtectedFromCleanup(t *testing.T) {
	now := time.Now()
	recent := now.Add(-30 * time.Minute)
	old := now.Add(-48 * time.Hour)

	cases := []struct {
		path string
		mod  time.Time
		want bool
	}{
		{"/var/lib/hyper2kvm/output/job/2025legacy.qcow2.part", recent, true},
		{"/var/lib/hyper2kvm/output/job/2025legacy.qcow2.tmp", recent, true},
		{"/var/lib/hyper2kvm/output/job/2025legacy.qcow2", recent, true},
		{"/var/lib/hyper2kvm/output/job/2025legacy.qcow2", old, false},
	}

	for _, tc := range cases {
		info := &fileInfoStub{modTime: tc.mod}
		if got := isProtectedFromCleanup(tc.path, info); got != tc.want {
			t.Fatalf("isProtectedFromCleanup(%q) = %v, want %v", tc.path, got, tc.want)
		}
	}
}

type fileInfoStub struct {
	modTime time.Time
}

func (f *fileInfoStub) Name() string       { return "stub" }
func (f *fileInfoStub) Size() int64        { return 0 }
func (f *fileInfoStub) Mode() os.FileMode  { return 0 }
func (f *fileInfoStub) ModTime() time.Time { return f.modTime }
func (f *fileInfoStub) IsDir() bool        { return false }
func (f *fileInfoStub) Sys() interface{}   { return nil }
