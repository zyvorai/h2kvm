# GitHub Labels

This document describes the labels used in this repository.

## How to Create Labels

### Option 1: Automatic (GitHub CLI)

If you have [GitHub CLI](https://cli.github.com/) installed:

```bash
# Run the label creation script
.github/create-labels.sh
```

### Option 2: Manual (Web Interface)

1. Go to https://github.com/ssahani/hyper2kvm/labels
2. Click "New label"
3. Create each label from the list below

### Option 3: Skip Labels (Simplest)

If you don't want to use labels, they're already removed from `dependabot.yml` in the latest version. No action needed!

---

## Required Labels for Dependabot

These labels are used by Dependabot for automatic dependency updates:

| Label | Color | Description |
|-------|-------|-------------|
| `dependencies` | `#0366d6` | Pull requests that update a dependency file |
| `github-actions` | `#000000` | Pull requests that update GitHub Actions workflows |
| `python` | `#2b67c6` | Python dependency updates |

---

## Standard Issue Labels

| Label | Color | Description |
|-------|-------|-------------|
| `bug` | `#d73a4a` | Something isn't working |
| `enhancement` | `#a2eeef` | New feature or request |
| `documentation` | `#0075ca` | Improvements or additions to documentation |
| `good first issue` | `#7057ff` | Good for newcomers |
| `help wanted` | `#008672` | Extra attention is needed |
| `question` | `#d876e3` | Further information is requested |
| `wontfix` | `#ffffff` | This will not be worked on |
| `duplicate` | `#cfd3d7` | This issue or pull request already exists |
| `invalid` | `#e4e669` | This doesn't seem right |

---

## Priority Labels

| Label | Color | Description |
|-------|-------|-------------|
| `priority: critical` | `#b60205` | Critical priority - blocking issue |
| `priority: high` | `#d93f0b` | High priority |
| `priority: medium` | `#fbca04` | Medium priority |
| `priority: low` | `#0e8a16` | Low priority |

---

## Type Labels

| Label | Color | Description |
|-------|-------|-------------|
| `type: security` | `#ee0701` | Security-related issue |
| `type: performance` | `#1d76db` | Performance improvement |
| `type: refactor` | `#ededed` | Code refactoring |
| `type: test` | `#c5def5` | Testing-related |

---

## Using Labels in Issues and PRs

### For Contributors

When creating an issue, add appropriate labels:
- Bug report → `bug` + priority label
- Feature request → `enhancement`
- Documentation → `documentation`
- Question → `question`

### For Maintainers

**Triage process:**
1. Add type label (`bug`, `enhancement`, etc.)
2. Add priority label if urgent
3. Add specialty labels (`type: security`, etc.)
4. Assign to milestone if applicable

**Dependabot PRs:**
- Automatically labeled with `dependencies`
- GitHub Actions updates: `github-actions`
- Python updates: `python`

---

## Label Maintenance

### Adding New Labels

```bash
# Using gh CLI
gh label create "new-label" --color "ffffff" --description "Description"

# Or via web interface
# https://github.com/ssahani/hyper2kvm/labels/new
```

### Editing Existing Labels

```bash
# Using gh CLI
gh label edit "label-name" --color "new-color" --description "New description"
```

### Deleting Labels

```bash
# Using gh CLI
gh label delete "label-name"
```

---

## Current Dependabot Configuration

The `dependabot.yml` file is configured to work **with or without labels**.

**Current configuration:** Labels are optional (removed in latest version)

**If you want to use labels:** Uncomment the `labels:` sections in `.github/dependabot.yml` after creating the labels.

---

## Related Documentation

- [GitHub Labels Documentation](https://docs.github.com/en/issues/using-labels-and-milestones-to-track-work/managing-labels)
- [Dependabot Configuration](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file)
