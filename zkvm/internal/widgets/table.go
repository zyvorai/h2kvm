// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package widgets

import (
	"sort"

	"github.com/charmbracelet/bubbles/table"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/hyper2kvm/zkvm/internal/theme"
)

// SortDirection indicates the sort order.
type SortDirection int

const (
	SortAsc  SortDirection = iota
	SortDesc
)

// SortableTable wraps the bubbles table with column-based sorting.
type SortableTable struct {
	table     table.Model
	columns   []table.Column
	rows      []table.Row
	sortCol   int
	sortDir   SortDirection
	height    int
}

// NewSortableTable creates a new sortable table with the given columns and height.
func NewSortableTable(columns []table.Column, height int) SortableTable {
	t := table.New(
		table.WithColumns(columns),
		table.WithFocused(true),
		table.WithHeight(height),
	)

	s := table.DefaultStyles()
	s.Header = s.Header.
		BorderStyle(lipgloss.NormalBorder()).
		BorderForeground(theme.Coral).
		BorderBottom(true).
		Bold(true).
		Foreground(theme.Orange)

	s.Selected = s.Selected.
		Foreground(lipgloss.Color("#FFFFFF")).
		Background(theme.Coral).
		Bold(true)

	t.SetStyles(s)

	return SortableTable{
		table:   t,
		columns: columns,
		sortCol: -1,
		height:  height,
	}
}

// SetRows replaces the table data and re-applies the current sort.
func (st SortableTable) SetRows(rows []table.Row) SortableTable {
	st.rows = make([]table.Row, len(rows))
	copy(st.rows, rows)

	if st.sortCol >= 0 {
		st = st.applySortInternal()
	}
	st.table.SetRows(st.rows)
	return st
}

// SortBy sorts the table by the given column index, toggling direction
// if the same column is sorted again.
func (st SortableTable) SortBy(col int) SortableTable {
	if col < 0 || col >= len(st.columns) {
		return st
	}

	if st.sortCol == col {
		if st.sortDir == SortAsc {
			st.sortDir = SortDesc
		} else {
			st.sortDir = SortAsc
		}
	} else {
		st.sortCol = col
		st.sortDir = SortAsc
	}

	st = st.applySortInternal()
	st.table.SetRows(st.rows)
	return st
}

// applySortInternal sorts the internal rows slice.
func (st SortableTable) applySortInternal() SortableTable {
	col := st.sortCol
	dir := st.sortDir

	sort.SliceStable(st.rows, func(i, j int) bool {
		if col >= len(st.rows[i]) || col >= len(st.rows[j]) {
			return false
		}
		if dir == SortAsc {
			return st.rows[i][col] < st.rows[j][col]
		}
		return st.rows[i][col] > st.rows[j][col]
	})
	return st
}

// SelectedRow returns the currently selected row, or nil if none.
func (st SortableTable) SelectedRow() table.Row {
	return st.table.SelectedRow()
}

// Cursor returns the current cursor position.
func (st SortableTable) Cursor() int {
	return st.table.Cursor()
}

// Init implements tea.Model.
func (st SortableTable) Init() tea.Cmd {
	return nil
}

// Update implements tea.Model.
func (st SortableTable) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	st.table, cmd = st.table.Update(msg)
	return st, cmd
}

// View implements tea.Model.
func (st SortableTable) View() string {
	return st.table.View()
}

// UpdateTable provides typed access to Update that returns SortableTable
// instead of tea.Model, for convenience when embedding.
func (st SortableTable) UpdateTable(msg tea.Msg) (SortableTable, tea.Cmd) {
	var cmd tea.Cmd
	st.table, cmd = st.table.Update(msg)
	return st, cmd
}
