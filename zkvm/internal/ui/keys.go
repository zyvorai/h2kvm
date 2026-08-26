// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package ui

import "github.com/charmbracelet/bubbles/key"

// KeyMap defines all global key bindings for the TUI.
type KeyMap struct {
	Quit     key.Binding
	Help     key.Binding
	Wizard   key.Binding
	Browser  key.Binding
	Refresh  key.Binding
	Settings key.Binding
	NextTab  key.Binding
	PrevTab  key.Binding
	Down     key.Binding
	Up       key.Binding
	Select   key.Binding
	Back     key.Binding
}

// DefaultKeyMap returns the default set of key bindings.
func DefaultKeyMap() KeyMap {
	return KeyMap{
		Quit: key.NewBinding(
			key.WithKeys("ctrl+q"),
			key.WithHelp("ctrl+q", "quit"),
		),
		Help: key.NewBinding(
			key.WithKeys("f1"),
			key.WithHelp("F1", "help"),
		),
		Wizard: key.NewBinding(
			key.WithKeys("f2"),
			key.WithHelp("F2", "quick wizard"),
		),
		Browser: key.NewBinding(
			key.WithKeys("f3"),
			key.WithHelp("F3", "browse VMs"),
		),
		Refresh: key.NewBinding(
			key.WithKeys("f5"),
			key.WithHelp("F5", "refresh"),
		),
		Settings: key.NewBinding(
			key.WithKeys("ctrl+s"),
			key.WithHelp("ctrl+s", "settings"),
		),
		NextTab: key.NewBinding(
			key.WithKeys("tab"),
			key.WithHelp("tab", "next tab"),
		),
		PrevTab: key.NewBinding(
			key.WithKeys("shift+tab"),
			key.WithHelp("shift+tab", "previous tab"),
		),
		Down: key.NewBinding(
			key.WithKeys("j", "down"),
			key.WithHelp("j/down", "scroll down"),
		),
		Up: key.NewBinding(
			key.WithKeys("k", "up"),
			key.WithHelp("k/up", "scroll up"),
		),
		Select: key.NewBinding(
			key.WithKeys("enter"),
			key.WithHelp("enter", "select/confirm"),
		),
		Back: key.NewBinding(
			key.WithKeys("esc"),
			key.WithHelp("esc", "back/close"),
		),
	}
}

// ShortHelp returns a short list of key bindings for the help bubble.
func (k KeyMap) ShortHelp() []key.Binding {
	return []key.Binding{k.Help, k.Quit, k.NextTab, k.PrevTab}
}

// FullHelp returns the full list of key bindings for the help bubble.
func (k KeyMap) FullHelp() [][]key.Binding {
	return [][]key.Binding{
		{k.NextTab, k.PrevTab, k.Down, k.Up},
		{k.Select, k.Back, k.Refresh},
		{k.Help, k.Wizard, k.Browser, k.Settings},
		{k.Quit},
	}
}

// GlobalKeyMap is a backward-compatible alias for KeyMap.
type GlobalKeyMap = KeyMap

// DefaultGlobalKeys is a backward-compatible alias for DefaultKeyMap.
func DefaultGlobalKeys() GlobalKeyMap {
	return DefaultKeyMap()
}
