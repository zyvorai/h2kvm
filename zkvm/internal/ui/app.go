// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package ui

import (
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/help"
	"github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/hyper2kvm/zkvm/internal/models"
	"github.com/hyper2kvm/zkvm/internal/protocol"
	"github.com/hyper2kvm/zkvm/internal/state"
	"github.com/hyper2kvm/zkvm/internal/widgets"
)

// TabModel is the interface that each tab sub-model must implement.
type TabModel interface {
	tea.Model
	TabTitle() string
}

// SocketEventMsg wraps a protocol.Envelope received from the socket.
type SocketEventMsg struct {
	Envelope protocol.Envelope
}

// TickMsg is sent periodically for refresh cycles.
type TickMsg struct {
	Time time.Time
}

// ConnectedMsg signals that the socket connection is established.
type ConnectedMsg struct{}

// DisconnectedMsg signals that the socket connection was lost.
type DisconnectedMsg struct{}

// Tab indices.
const (
	TabHome       = 0
	TabDashboard  = 1
	TabWizard     = 2
	TabBrowser    = 3
	TabMigrations = 4
	TabBatch      = 5
	TabSettings   = 6
)

// tickInterval is the periodic refresh interval.
const tickInterval = 2 * time.Second

// App is the root Bubble Tea model for the hyper2kvm TUI.
type App struct {
	keys      KeyMap
	help      help.Model
	tabs      []TabModel
	activeTab int
	store     *state.Store
	statusBar widgets.StatusBar
	width     int
	height    int
	showHelp  bool
	ready     bool
}

// NewApp creates the root application model.
// Tabs are passed in from main.go to avoid circular imports.
func NewApp(store *state.Store, tabs []TabModel) App {
	keys := DefaultKeyMap()
	h := help.New()
	h.ShowAll = false

	return App{
		keys:      keys,
		help:      h,
		tabs:      tabs,
		activeTab: TabHome,
		store:     store,
		statusBar: widgets.NewStatusBar(80),
	}
}

// Init implements tea.Model.
func (a App) Init() tea.Cmd {
	return tea.Batch(tickCmd(), tea.EnterAltScreen)
}

// tickCmd returns a command that sends a TickMsg after the tick interval.
func tickCmd() tea.Cmd {
	return tea.Tick(tickInterval, func(t time.Time) tea.Msg {
		return TickMsg{Time: t}
	})
}

// Update implements tea.Model.
func (a App) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmds []tea.Cmd

	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		a.width = msg.Width
		a.height = msg.Height
		a.statusBar = a.statusBar.SetWidth(msg.Width)
		a.help.Width = msg.Width
		a.ready = true
		return a, nil

	case tea.KeyMsg:
		// Global key handling (always active).
		switch {
		case key.Matches(msg, a.keys.Quit):
			return a, tea.Quit

		case key.Matches(msg, a.keys.Help):
			a.showHelp = !a.showHelp
			return a, nil

		case key.Matches(msg, a.keys.Back):
			if a.showHelp {
				a.showHelp = false
				return a, nil
			}

		case key.Matches(msg, a.keys.Refresh):
			return a, tickCmd()

		case key.Matches(msg, a.keys.Wizard):
			a.activeTab = TabWizard
			return a, nil

		case key.Matches(msg, a.keys.Browser):
			a.activeTab = TabBrowser
			return a, nil

		case key.Matches(msg, a.keys.Settings):
			a.activeTab = TabSettings
			return a, nil

		case key.Matches(msg, a.keys.NextTab):
			if !a.showHelp {
				a.activeTab = (a.activeTab + 1) % len(a.tabs)
				return a, nil
			}

		case key.Matches(msg, a.keys.PrevTab):
			if !a.showHelp {
				a.activeTab = (a.activeTab - 1 + len(a.tabs)) % len(a.tabs)
				return a, nil
			}
		}

	case SocketEventMsg:
		a.dispatchSocketEvent(msg.Envelope)
		a.statusBar = a.statusBar.SetActiveMigrations(
			len(a.store.GetActiveMigrations()),
		)
		return a, nil

	case ConnectedMsg:
		a.store.SetConnected(true)
		a.statusBar = a.statusBar.SetConnected(true)
		return a, nil

	case DisconnectedMsg:
		a.store.SetConnected(false)
		a.statusBar = a.statusBar.SetConnected(false)
		return a, nil

	case TickMsg:
		a.statusBar = a.statusBar.SetConnected(a.store.IsConnected())
		a.statusBar = a.statusBar.SetActiveMigrations(
			len(a.store.GetActiveMigrations()),
		)
		cmds = append(cmds, tickCmd())
		return a, tea.Batch(cmds...)

	// Migration control messages from the migrations tab.
	case models.PauseMigrationMsg:
		if a.store.IsConnected() && a.store.Client != nil {
			_ = a.store.Client.SendFireAndForget(protocol.NewPauseMigrationRequest(msg.ID))
		}
		return a, nil
	case models.ResumeMigrationMsg:
		if a.store.IsConnected() && a.store.Client != nil {
			_ = a.store.Client.SendFireAndForget(protocol.NewResumeMigrationRequest(msg.ID))
		}
		return a, nil
	case models.CancelMigrationMsg:
		if a.store.IsConnected() && a.store.Client != nil {
			_ = a.store.Client.SendFireAndForget(protocol.NewCancelMigrationRequest(msg.ID))
		}
		return a, nil

	// Batch control messages.
	case models.BatchStartAllMsg:
		if a.store.IsConnected() && a.store.Client != nil {
			for _, item := range msg.Items {
				cfg := protocol.StartMigrationConfig{
					VMName:     item.VMName,
					SourceType: item.SourceType,
					SourcePath: item.SourcePath,
				}
				_ = a.store.Client.SendFireAndForget(protocol.NewStartMigrationRequest(cfg))
			}
		}
		return a, nil
	case models.BatchCancelAllMsg:
		if a.store.IsConnected() && a.store.Client != nil {
			for _, id := range msg.IDs {
				_ = a.store.Client.SendFireAndForget(protocol.NewCancelMigrationRequest(id))
			}
		}
		return a, nil
	}

	// Forward to active tab.
	if a.activeTab >= 0 && a.activeTab < len(a.tabs) {
		updated, cmd := a.tabs[a.activeTab].Update(msg)
		if tab, ok := updated.(TabModel); ok {
			a.tabs[a.activeTab] = tab
		}
		if cmd != nil {
			cmds = append(cmds, cmd)
		}
	}

	return a, tea.Batch(cmds...)
}

// View implements tea.Model.
func (a App) View() string {
	if !a.ready {
		return "Initializing..."
	}

	var b strings.Builder

	// Content area (top — Zellij style, no title bar).
	// Height = total - tabbar(1) - statusbar(1) - newlines(2).
	contentHeight := a.height - 3
	if contentHeight < 1 {
		contentHeight = 1
	}

	var content string
	if a.showHelp {
		content = a.renderHelpOverlay()
	} else if a.activeTab >= 0 && a.activeTab < len(a.tabs) {
		content = a.tabs[a.activeTab].View()
	}

	contentStyle := ContentStyle.Width(a.width).Height(contentHeight)
	b.WriteString(contentStyle.Render(content))
	b.WriteString("\n")

	// Tab bar (bottom — Zellij style).
	b.WriteString(a.renderTabBar())
	b.WriteString("\n")

	// Status bar (very bottom).
	b.WriteString(a.statusBar.View())

	return b.String()
}

// renderTabBar renders the tab bar with active/inactive styling.
func (a App) renderTabBar() string {
	var tabs []string
	for i, tab := range a.tabs {
		title := tab.TabTitle()
		if i == a.activeTab {
			tabs = append(tabs, TabActiveStyle.Render(title))
		} else {
			tabs = append(tabs, TabInactiveStyle.Render(title))
		}
	}

	row := lipgloss.JoinHorizontal(lipgloss.Top, tabs...)
	return TabBarStyle.Width(a.width).Render(row)
}

// renderHelpOverlay renders the help overlay using the built-in help bubble.
func (a App) renderHelpOverlay() string {
	a.help.ShowAll = true
	helpText := a.help.View(a.keys)
	return OverlayStyle.Render(
		HeadingStyle.Render("Keyboard Shortcuts") + "\n\n" + helpText,
	)
}

// dispatchSocketEvent routes a socket envelope to the state store.
func (a App) dispatchSocketEvent(env protocol.Envelope) {
	switch env.Type {
	case "migration_update":
		// Decoded elsewhere; the store is updated by the socket listener.
	case "log":
		// Decoded elsewhere; the store is updated by the socket listener.
	case "metrics":
		// Decoded elsewhere; the store is updated by the socket listener.
	case "_disconnected":
		a.store.SetConnected(false)
	}
}
