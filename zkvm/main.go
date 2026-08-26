// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


// zkvm is the Go-based Terminal User Interface for hyper2kvm.
//
// It communicates with the Python backend via a Unix domain socket
// using a newline-delimited JSON protocol.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"sync/atomic"
	"time"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/hyper2kvm/zkvm/internal/models"
	"github.com/hyper2kvm/zkvm/internal/theme"
	"github.com/hyper2kvm/zkvm/internal/protocol"
	"github.com/hyper2kvm/zkvm/internal/state"
	"github.com/hyper2kvm/zkvm/internal/ui"
	"github.com/hyper2kvm/zkvm/internal/ui/batch"
	"github.com/hyper2kvm/zkvm/internal/ui/browser"
	"github.com/hyper2kvm/zkvm/internal/ui/dashboard"
	"github.com/hyper2kvm/zkvm/internal/ui/home"
	"github.com/hyper2kvm/zkvm/internal/ui/migrations"
	"github.com/hyper2kvm/zkvm/internal/ui/settings"
	"github.com/hyper2kvm/zkvm/internal/ui/standalone"
	"github.com/hyper2kvm/zkvm/internal/ui/wizard"
)

// version is set at build time via -ldflags.
var version = "dev"

func main() {
	showVersion := flag.Bool("version", false, "Print version and exit")
	flag.BoolVar(showVersion, "v", false, "Shorthand for -version")
	themeName := flag.String("theme", "dark", "Theme: dark, light, hypersdk")
	flag.StringVar(themeName, "t", "dark", "Shorthand for -theme")
	binaryPath := flag.String("binary", "", "Path to h2kvmctl binary (default: auto-detect)")
	flag.StringVar(binaryPath, "b", "", "Shorthand for -binary")

	// Pre-fill flags.
	cmdFlag := flag.String("cmd", "", "Pre-fill command type")
	flag.StringVar(cmdFlag, "c", "", "Shorthand for -cmd")
	vmdkFlag := flag.String("vmdk", "", "Pre-fill VMDK path")
	flag.StringVar(vmdkFlag, "m", "", "Shorthand for -vmdk")
	outputDirFlag := flag.String("output-dir", "", "Pre-fill output directory")
	flag.StringVar(outputDirFlag, "o", "", "Shorthand for -output-dir")
	vcenterFlag := flag.String("vcenter", "", "Pre-fill vCenter host")
	vcUserFlag := flag.String("vc-user", "", "Pre-fill vCenter username")
	dcNameFlag := flag.String("dc-name", "", "Pre-fill datacenter name")
	vmNameFlag := flag.String("vm-name", "", "Pre-fill VM name")

	// Tabbed mode (requires backend socket).
	tabbedMode := flag.Bool("tabbed", false, "Run tabbed multi-tab mode (requires backend)")
	socketPath := flag.String("socket", "", "Backend Unix socket path (tabbed mode)")

	flag.Parse()

	if *showVersion {
		fmt.Printf("zkvm %s\n", version)
		os.Exit(0)
	}

	theme.SetTheme(*themeName)

	store := state.NewStore()
	store.Version = version
	_ = store.LoadConfigFromFile() // Restore persisted settings (ignore error, use defaults)

	// Default: standalone mode — runs h2kvmctl directly, no backend needed.
	if !*tabbedMode {
		pf := standalone.Prefill{
			Cmd:       *cmdFlag,
			VMDK:      *vmdkFlag,
			OutputDir: *outputDirFlag,
			VCenter:   *vcenterFlag,
			VCUser:    *vcUserFlag,
			DCName:    *dcNameFlag,
			VMName:    *vmNameFlag,
		}

		m := standalone.New(store, pf, *binaryPath)
		p := tea.NewProgram(m, tea.WithAltScreen())
		m.SetProgram(p)

		if _, err := p.Run(); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
		return
	}

	// Tabbed mode: connect to Python backend.
	client := protocol.NewClient(*socketPath)
	store.Client = client

	if err := client.Connect(); err == nil {
		store.SetConnected(true)
		_ = client.SendFireAndForget(protocol.NewSubscribeRequest("migrations", "logs", "metrics"))
	}

	tabs := []ui.TabModel{
		home.New(store),
		dashboard.New(store),
		wizard.New(store),
		browser.New(store),
		migrations.New(store),
		batch.New(store),
		settings.New(store),
	}

	app := ui.NewApp(store, tabs)
	p := tea.NewProgram(app, tea.WithAltScreen())

	if client.IsConnected() {
		go socketListener(client, store, p)
	}

	if _, err := p.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	_ = client.Close()
}

// socketListener reads events from the socket and dispatches them to the store.
func socketListener(client *protocol.Client, store *state.Store, p *tea.Program) {
	var reconnecting atomic.Bool
	for env := range client.EventCh {
		switch env.Type {
		case "_disconnected":
			store.SetConnected(false)
			p.Send(ui.DisconnectedMsg{})

			if reconnecting.CompareAndSwap(false, true) {
				go func() {
					defer reconnecting.Store(false)
					time.Sleep(3 * time.Second)
					if err := client.ConnectWithRetry(); err == nil {
						store.SetConnected(true)
						p.Send(ui.ConnectedMsg{})
						_ = client.SendFireAndForget(protocol.NewSubscribeRequest("migrations", "logs", "metrics"))
					}
				}()
			}

		case "migration_update":
			var data protocol.MigrationUpdateData
			if err := json.Unmarshal(env.Data, &data); err == nil {
				store.UpdateMigration(&models.MigrationRecord{
					ID:           data.ID,
					VMName:       data.VMName,
					Status:       models.MigrationStatus(data.Status),
					Progress:     data.Progress,
					CurrentStage: data.CurrentStage,
					Throughput:   data.Throughput,
					Elapsed:      data.Elapsed,
					ETA:          data.ETA,
					ErrorMessage: data.Error,
				})
			}
			p.Send(ui.SocketEventMsg{Envelope: env})

		case "log":
			var data protocol.LogData
			if err := json.Unmarshal(env.Data, &data); err == nil {
				store.AppendLog(data)
			}
			p.Send(ui.SocketEventMsg{Envelope: env})

		case "metrics":
			var data protocol.MetricsData
			if err := json.Unmarshal(env.Data, &data); err == nil {
				store.UpdateStats(models.Statistics{
					TotalMigrations:  data.TotalMigrations,
					ActiveMigrations: data.Active,
					CompletedToday:   data.CompletedToday,
					SuccessRate:      data.SuccessRate,
					TotalCompleted:   data.Completed,
					TotalFailed:      data.Failed,
					AvgDuration:      data.AvgDuration,
				})
			}
			p.Send(ui.SocketEventMsg{Envelope: env})

		default:
			p.Send(ui.SocketEventMsg{Envelope: env})
		}
	}
}
