// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package theme

import "testing"

func TestThemes(t *testing.T) {
	for name, th := range map[string]Theme{"Forge": Forge, "TokyoNight": TokyoNight, "Hypersdk": Hypersdk, "Light": Light} {
		if string(th.Bg) == "" || string(th.Primary) == "" || string(th.BgPanel) == "" {
			t.Errorf("%s has empty colors", name)
		}
		if string(th.Subtle) == "" {
			t.Errorf("%s has empty Subtle color", name)
		}
	}
}

func TestSetTheme(t *testing.T) {
	SetTheme("tokyo")
	if Active.Primary != TokyoNight.Primary { t.Error("tokyo failed") }
	SetTheme("neon")
	if Active.Primary != Hypersdk.Primary { t.Error("neon failed") }
	SetTheme("light")
	if Active.Primary != Light.Primary { t.Error("light failed") }
	SetTheme("unknown")
	if Active.Primary != Forge.Primary { t.Error("default should be Forge") }
}
