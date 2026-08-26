// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

package standalone

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"unicode/utf8"

	"github.com/charmbracelet/lipgloss"
	"github.com/h2kvm/zkvm/internal/theme"
)

// fileEntry represents a directory listing item.
type fileEntry struct {
	Name  string
	IsDir bool
	Size  int64
}

// FileBrowser is a modal file/directory picker with fuzzy search.
type FileBrowser struct {
	cwd        string
	allEntries []fileEntry // unfiltered listing
	filtered   []fileEntry // after fuzzy filter
	cursor     int
	offset     int // scroll offset
	maxVisible int
	selected   string // final selected path (empty until confirmed)
	active     bool
	extensions []string
	dirOnly    bool
	title      string
	search     string // fuzzy search query
	searching  bool   // whether search input is active
	showHidden bool   // show dotfiles
}

// NewFileBrowser creates a file browser starting at the given directory.
func NewFileBrowser(startDir string, extensions []string, dirOnly bool) *FileBrowser {
	if startDir == "" {
		startDir, _ = os.Getwd()
	}
	if strings.HasPrefix(startDir, "~") {
		if home, err := os.UserHomeDir(); err == nil {
			startDir = filepath.Join(home, startDir[1:])
		}
	}
	if info, err := os.Stat(startDir); err == nil && !info.IsDir() {
		startDir = filepath.Dir(startDir)
	}

	fb := &FileBrowser{
		cwd:        startDir,
		maxVisible: 20,
		extensions: extensions,
		dirOnly:    dirOnly,
		active:     true,
	}
	if dirOnly {
		fb.title = "Select Directory"
	} else if len(extensions) > 0 {
		fb.title = "Select File (" + strings.Join(extensions, ", ") + ")"
	} else {
		fb.title = "Select File"
	}
	fb.readDir()
	return fb
}

// readDir loads the current directory listing.
func (fb *FileBrowser) readDir() {
	fb.allEntries = nil
	fb.cursor = 0
	fb.offset = 0

	if fb.cwd != "/" {
		fb.allEntries = append(fb.allEntries, fileEntry{Name: "..", IsDir: true})
	}

	dirEntries, err := os.ReadDir(fb.cwd)
	if err != nil {
		fb.applyFilter()
		return
	}

	var dirs, files []fileEntry
	for _, de := range dirEntries {
		if !fb.showHidden && strings.HasPrefix(de.Name(), ".") {
			continue
		}
		info, _ := de.Info()
		size := int64(0)
		if info != nil {
			size = info.Size()
		}

		if de.IsDir() {
			dirs = append(dirs, fileEntry{Name: de.Name(), IsDir: true})
		} else if !fb.dirOnly {
			if fb.matchesExtension(de.Name()) {
				files = append(files, fileEntry{Name: de.Name(), Size: size})
			}
		}
	}

	sort.Slice(dirs, func(i, j int) bool { return dirs[i].Name < dirs[j].Name })
	sort.Slice(files, func(i, j int) bool { return files[i].Name < files[j].Name })
	fb.allEntries = append(fb.allEntries, dirs...)
	fb.allEntries = append(fb.allEntries, files...)
	fb.applyFilter()
}

func (fb *FileBrowser) matchesExtension(name string) bool {
	if len(fb.extensions) == 0 {
		return true
	}
	lower := strings.ToLower(name)
	for _, ext := range fb.extensions {
		if strings.HasSuffix(lower, strings.ToLower(ext)) {
			return true
		}
	}
	return false
}

// applyFilter filters allEntries by fuzzy search query.
func (fb *FileBrowser) applyFilter() {
	if fb.search == "" {
		fb.filtered = fb.allEntries
	} else {
		fb.filtered = nil
		q := strings.ToLower(fb.search)
		for _, e := range fb.allEntries {
			if e.Name == ".." || fuzzyMatch(q, strings.ToLower(e.Name)) {
				fb.filtered = append(fb.filtered, e)
			}
		}
	}
	fb.cursor = 0
	fb.offset = 0
}

// fuzzyMatch checks if all chars in pattern appear in str in order.
func fuzzyMatch(pattern, str string) bool {
	pi := 0
	for i := 0; i < len(str) && pi < len(pattern); i++ {
		if str[i] == pattern[pi] {
			pi++
		}
	}
	return pi == len(pattern)
}

// fuzzyHighlight returns the name with matched characters highlighted.
func fuzzyHighlight(pattern, name string, matchStyle, normalStyle lipgloss.Style) string {
	if pattern == "" {
		return normalStyle.Render(name)
	}
	lower := strings.ToLower(name)
	q := strings.ToLower(pattern)
	var b strings.Builder
	pi := 0
	for i, ch := range name {
		if pi < len(q) && i < len(lower) && lower[i] == q[pi] {
			b.WriteString(matchStyle.Render(string(ch)))
			pi++
		} else {
			b.WriteString(normalStyle.Render(string(ch)))
		}
	}
	return b.String()
}

// HandleKey processes a key press. Returns true if the browser should close.
func (fb *FileBrowser) HandleKey(key string) bool {
	// In search mode, capture typing.
	if fb.searching {
		switch key {
		case "esc":
			fb.searching = false
			fb.search = ""
			fb.applyFilter()
			return false
		case "enter":
			fb.searching = false
			return false
		case "backspace":
			if len(fb.search) > 0 {
				_, size := utf8.DecodeLastRuneInString(fb.search)
				fb.search = fb.search[:len(fb.search)-size]
				fb.applyFilter()
			}
			return false
		case "up", "down":
			// Allow navigation while searching.
		default:
			if len(key) == 1 || (len(key) > 1 && !strings.HasPrefix(key, "ctrl+")) {
				fb.search += key
				fb.applyFilter()
				return false
			}
		}
	}

	switch key {
	case "up", "k":
		if fb.cursor > 0 {
			fb.cursor--
			fb.adjustScroll()
		}
	case "down", "j":
		if fb.cursor < len(fb.filtered)-1 {
			fb.cursor++
			fb.adjustScroll()
		}
	case "enter":
		if fb.cursor >= 0 && fb.cursor < len(fb.filtered) {
			e := fb.filtered[fb.cursor]
			if e.IsDir {
				if e.Name == ".." {
					fb.cwd = filepath.Dir(fb.cwd)
				} else {
					fb.cwd = filepath.Join(fb.cwd, e.Name)
				}
				fb.search = ""
				fb.readDir()
			} else {
				fb.selected = filepath.Join(fb.cwd, e.Name)
				fb.active = false
				return true
			}
		}
	case "backspace":
		if fb.search != "" {
			_, size := utf8.DecodeLastRuneInString(fb.search)
			fb.search = fb.search[:len(fb.search)-size]
			fb.applyFilter()
		} else {
			fb.cwd = filepath.Dir(fb.cwd)
			fb.readDir()
		}
	case "/":
		if fb.searching {
			fb.search += "/"
			fb.applyFilter()
		} else {
			fb.searching = true
			fb.search = ""
		}
	case "~":
		if !fb.searching {
			if home, err := os.UserHomeDir(); err == nil {
				fb.cwd = home
				fb.search = ""
				fb.readDir()
			}
		}
	case "ctrl+h":
		fb.showHidden = !fb.showHidden
		fb.readDir()
	case "esc", "q":
		if fb.search != "" {
			fb.search = ""
			fb.applyFilter()
			return false
		}
		fb.active = false
		return true
	case " ":
		if fb.dirOnly {
			fb.selected = fb.cwd
			fb.active = false
			return true
		}
	}
	return false
}

func (fb *FileBrowser) adjustScroll() {
	if fb.cursor < fb.offset {
		fb.offset = fb.cursor
	}
	if fb.cursor >= fb.offset+fb.maxVisible {
		fb.offset = fb.cursor - fb.maxVisible + 1
	}
}

// Selected returns the chosen path, or "" if cancelled.
func (fb *FileBrowser) Selected() string { return fb.selected }

// IsActive returns whether the browser is still open.
func (fb *FileBrowser) IsActive() bool { return fb.active }

// Render draws the file browser as an overlay panel.
func (fb *FileBrowser) Render(width, height int) string {
	panelW := width - 10
	if panelW < 40 {
		panelW = 40
	}
	if panelW > 80 {
		panelW = 80
	}

	headerStyle := lipgloss.NewStyle().Bold(true).Foreground(theme.Active.Primary)
	pathStyle := lipgloss.NewStyle().Foreground(theme.Active.Fg).Bold(true)
	dirStyle := lipgloss.NewStyle().Foreground(theme.Active.Primary).Bold(true)
	fileStyle := lipgloss.NewStyle().Foreground(theme.Active.Fg)
	matchStyle := lipgloss.NewStyle().Foreground(theme.Active.Warning).Bold(true).Underline(true)
	sizeStyle := lipgloss.NewStyle().Foreground(theme.Active.Muted).Width(8).Align(lipgloss.Right)
	cursorBgStyle := lipgloss.NewStyle().Bold(true).Foreground(theme.Active.Bg).Background(theme.Active.Primary)
	hintStyle := lipgloss.NewStyle().Foreground(theme.Active.Muted)
	searchStyle := lipgloss.NewStyle().Foreground(theme.Active.Warning).Bold(true)
	countStyle := lipgloss.NewStyle().Foreground(theme.Active.Muted)
	dividerStyle := lipgloss.NewStyle().Foreground(theme.Active.Border)

	var b strings.Builder

	// Header.
	b.WriteString(headerStyle.Render("📂 " + fb.title))
	if fb.showHidden {
		b.WriteString(hintStyle.Render("  [hidden: on]"))
	}
	b.WriteString("\n")
	b.WriteString(pathStyle.Render(fb.cwd) + "\n")

	// Search bar.
	if fb.search != "" || fb.searching {
		cursor := ""
		if fb.searching {
			cursor = "█"
		}
		b.WriteString(searchStyle.Render("🔍 "+fb.search+cursor) + " ")
		b.WriteString(countStyle.Render(fmt.Sprintf("(%d results)", len(fb.filtered))))
		b.WriteString("\n")
	}

	b.WriteString(dividerStyle.Render(strings.Repeat("─", panelW)) + "\n")

	end := fb.offset + fb.maxVisible
	if end > len(fb.filtered) {
		end = len(fb.filtered)
	}

	if fb.offset > 0 {
		b.WriteString(hintStyle.Render(fmt.Sprintf("  ↑ %d more above", fb.offset)) + "\n")
	}

	for i := fb.offset; i < end; i++ {
		e := fb.filtered[i]
		var icon, name, size string

		if e.IsDir {
			icon = "📁 "
			name = fuzzyHighlight(fb.search, e.Name+"/", matchStyle, dirStyle)
			size = ""
		} else {
			icon = "   "
			name = fuzzyHighlight(fb.search, e.Name, matchStyle, fileStyle)
			size = sizeStyle.Render(fmtSize(e.Size))
		}

		line := fmt.Sprintf(" %s%s %s", icon, name, size)

		if i == fb.cursor {
			b.WriteString(cursorBgStyle.Width(panelW).Render(line))
		} else {
			b.WriteString(line)
		}
		b.WriteString("\n")
	}

	if len(fb.filtered) == 0 {
		b.WriteString(hintStyle.Render("  No matching files") + "\n")
	}

	if end < len(fb.filtered) {
		b.WriteString(hintStyle.Render(fmt.Sprintf("  ↓ %d more below", len(fb.filtered)-end)) + "\n")
	}

	b.WriteString(dividerStyle.Render(strings.Repeat("─", panelW)) + "\n")
	hints := "j/k Navigate  Enter Open/Select  / Search  Backspace Up  ~ Home  Ctrl+H Hidden  Esc Cancel"
	b.WriteString(hintStyle.Render(hints))

	panelStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(theme.Active.Primary).
		Padding(1, 2).
		Width(panelW + 6)

	return panelStyle.Render(b.String())
}

// fmtSize returns a human-readable file size.
func fmtSize(b int64) string {
	switch {
	case b >= 1024*1024*1024:
		return fmt.Sprintf("%.1fG", float64(b)/(1024*1024*1024))
	case b >= 1024*1024:
		return fmt.Sprintf("%.0fM", float64(b)/(1024*1024))
	case b >= 1024:
		return fmt.Sprintf("%.0fK", float64(b)/1024)
	default:
		return fmt.Sprintf("%dB", b)
	}
}
