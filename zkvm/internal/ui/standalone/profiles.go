// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

const profileDirName = ".config/hyper2kvm/profiles"

// ConversionProfile stores a reusable set of form field values.
type ConversionProfile struct {
	Name      string            `json:"name"`
	Fields    map[string]string `json:"fields"`
	CreatedAt time.Time         `json:"created_at"`
}

// profileDirPath returns the profile storage directory.
func profileDirPath() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, profileDirName)
}

// SaveProfile persists the current form state as a named profile.
func SaveProfile(name string, form *FormData) error {
	dir := profileDirPath()
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("cannot create profile directory at %s: %w — check directory permissions", dir, err)
	}

	fields := make(map[string]string)
	for i := range form.Categories {
		for j := range form.Categories[i].Fields {
			f := &form.Categories[i].Fields[j]
			val := f.CLIValue()
			if val != "" {
				fields[f.Label] = val
			}
		}
	}

	profile := ConversionProfile{
		Name:      name,
		Fields:    fields,
		CreatedAt: time.Now(),
	}

	data, err := json.MarshalIndent(profile, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal profile: %w", err)
	}

	path := filepath.Join(dir, name+".json")
	if err := os.WriteFile(path, data, 0644); err != nil {
		return fmt.Errorf("failed to write profile %q to %s: %w — check directory permissions and available disk space", name, path, err)
	}
	return nil
}

// LoadProfile reads a named profile from disk.
func LoadProfile(name string) (*ConversionProfile, error) {
	path := filepath.Join(profileDirPath(), name+".json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("cannot read profile %q: %w — available profiles are stored in %s", name, err, profileDirPath())
	}

	var profile ConversionProfile
	if err := json.Unmarshal(data, &profile); err != nil {
		return nil, fmt.Errorf("failed to parse profile %q from %s: %w — the file may be corrupted, try deleting and re-saving the profile", name, path, err)
	}
	return &profile, nil
}

// ListProfiles returns all saved profiles sorted by creation time (newest first).
func ListProfiles() ([]ConversionProfile, error) {
	dir := profileDirPath()
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}

	var profiles []ConversionProfile
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		name := strings.TrimSuffix(e.Name(), ".json")
		p, err := LoadProfile(name)
		if err != nil {
			continue
		}
		profiles = append(profiles, *p)
	}

	sort.Slice(profiles, func(i, j int) bool {
		return profiles[i].CreatedAt.After(profiles[j].CreatedAt)
	})
	return profiles, nil
}

// DeleteProfile removes a named profile from disk.
func DeleteProfile(name string) error {
	path := filepath.Join(profileDirPath(), name+".json")
	if err := os.Remove(path); err != nil {
		return fmt.Errorf("failed to delete profile %q at %s: %w", name, path, err)
	}
	return nil
}

// ApplyProfile sets form field values from a profile.
func ApplyProfile(profile *ConversionProfile, form *FormData) {
	for i := range form.Categories {
		for j := range form.Categories[i].Fields {
			f := &form.Categories[i].Fields[j]
			val, ok := profile.Fields[f.Label]
			if !ok {
				continue
			}
			switch f.Type {
			case FieldToggle:
				f.BoolValue = val == "true"
			case FieldSelect:
				for idx, opt := range f.Options {
					if opt == val {
						f.SelectedIdx = idx
						break
					}
				}
			default:
				f.Value = val
			}
		}
	}
}
