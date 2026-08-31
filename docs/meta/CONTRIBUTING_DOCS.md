# Contributing to Documentation

Guide for contributing to H2KVM documentation.

---

## Quick Links

- [Documentation Standards](#documentation-standards)
- [File Organization](#file-organization)
- [Writing Guidelines](#writing-guidelines)
- [Adding New Documentation](#adding-new-documentation)
- [Updating Existing Docs](#updating-existing-docs)
- [Review Process](#review-process)

---

## Documentation Standards

### Structure Requirements

Every documentation directory must have:
- **README.md** or **index.md** as the entry point
- Clear navigation to child documents
- Links back to parent/related documentation
- Consistent formatting and style

### File Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| **Index/Hub** | `README.md` or `index.md` | `features/README.md` |
| **Numbered Guides** | `##-description.md` | `01-Installation.md` |
| **Feature Docs** | `feature-name.md` | `vmdk-inspector.md` |
| **Topic Docs** | `topic-name.md` | `security-best-practices.md` |
| **Versioned** | `NAME_v#.#.#.md` | `RELEASE_NOTES_v0.3.1.md` |

### Markdown Standards

```markdown
# Document Title (H1 - Only One Per Document)

Brief description of what this document covers.

---

## Section (H2)

Content here.

### Subsection (H3)

More specific content.

---

## Related Documentation

- [Link Text](relative/path.md) - Description
```

**Rules**:
- ✅ Use relative links for internal docs
- ✅ Use `---` horizontal rules to separate major sections
- ✅ Include "Related Documentation" section at the end
- ✅ One H1 heading per document
- ✅ Consistent emoji usage (see emoji guide below)
- ❌ Don't use HTML unless absolutely necessary
- ❌ Don't embed large images (link to them instead)

---

## File Organization

### Current Structure

```
docs/
├── index.md                  # Main hub - links to everything
├── FAQ.md                    # Frequently asked questions
├── GLOSSARY.md              # Complete terminology
├── QUICK_REFERENCE.md       # One-page command reference
│
├── getting-started/         # New user documentation
│   ├── README.md           # Getting started hub
│   └── ##-*.md            # Numbered guides
│
├── tutorials/               # Step-by-step learning
│   ├── README.md           # Tutorials hub
│   └── ##-*.md            # Numbered tutorials
│
├── recipes/                 # Quick solutions
│   ├── README.md           # Recipes hub
│   └── ##-*.md            # Recipe collections
│
├── guides/                  # Task-oriented guides
│   ├── README.md           # Guides hub
│   ├── cli/                # CLI documentation
│   ├── migration/          # Migration workflows
│   ├── tui/                # Terminal UI guides
│   └── configuration/      # Configuration guides
│
├── features/                # Feature documentation
│   ├── README.md           # Features hub
│   └── guestkit/           # GuestKit engine docs
│
├── os-support/             # OS-specific guides
│   ├── README.md           # OS support hub
│   └── windows/           # Windows-specific docs
│
├── deployment/             # Deployment guides
│   ├── README.md           # Deployment hub
│   ├── openshift/         # OpenShift-specific
│   └── releases/          # Release notes
│
├── worker/                 # Worker protocol
│   └── README.md           # Worker protocol hub
│
├── test-results/           # Test reports
│   └── README.md           # Test results hub
│
├── reference/              # Technical reference
│   ├── README.md           # Reference hub
│   └── api/               # API documentation
│
└── development/            # Development guides
    └── README.md           # Development hub
```

### Where to Add Documentation

| Content Type | Location | Example |
|--------------|----------|---------|
| **Getting Started** | `getting-started/` | Installation, quick start |
| **Step-by-Step Tutorial** | `tutorials/` | Beginner migration tutorial |
| **Quick Recipe** | `recipes/` | "Migrate Ubuntu VM" recipe |
| **Task Guide** | `guides/` | "Batch Migration" guide |
| **Feature Documentation** | `features/` | "VMDK Inspector" feature |
| **OS-Specific** | `os-support/` | "Windows Migration" guide |
| **Deployment** | `deployment/` | "OpenShift Deployment" |
| **API Reference** | `reference/api/` | "GuestKit API" reference |
| **Test Results** | `test-results/` | "CentOS 9 Test Results" |
| **Worker Protocol** | `worker/` | "REST API Specification" |

---

## Writing Guidelines

### Voice and Tone

- **Use active voice**: "Run the command" not "The command should be run"
- **Be concise**: Get to the point quickly
- **Be specific**: Use concrete examples
- **Be helpful**: Anticipate user questions
- **Be professional**: Avoid slang and informal language

### Structure for Different Document Types

#### 1. Getting Started Guide

```markdown
# Guide Title

Brief description (1-2 sentences).

**Time**: 10 minutes
**Level**: Beginner
**Prerequisites**: List what's needed

---

## Quick Start

Fastest path to success (3-5 steps).

---

## Detailed Steps

### Step 1: First Thing

Instructions...

### Step 2: Second Thing

Instructions...

---

## Troubleshooting

Common issues and solutions.

---

## Next Steps

- [Related Guide 1](link)
- [Related Guide 2](link)
```

#### 2. Feature Documentation

```markdown
# Feature Name

Brief description and use case.

**Status**: ✅ Production Ready
**Since**: v1.0.0

---

## Overview

What this feature does and why it exists.

---

## Usage

### Basic Usage

```yaml
# Configuration example
```

### Advanced Usage

```yaml
# Advanced configuration
```

---

## Examples

### Example 1: Common Scenario

Description and code.

### Example 2: Advanced Scenario

Description and code.

---

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `name` | string | - | What it does |

---

## Troubleshooting

Common issues and solutions.

---

## Related Features

- [Feature 1](link)
- [Feature 2](link)
```

#### 3. Tutorial

```markdown
# Tutorial Title

What you'll learn in this tutorial.

**Time**: 30 minutes
**Level**: Intermediate
**Prerequisites**:
- Prerequisite 1
- Prerequisite 2

---

## Learning Objectives

By the end of this tutorial, you will:
1. Objective 1
2. Objective 2
3. Objective 3

---

## Step 1: Setup

Instructions...

## Step 2: Main Task

Instructions...

## Step 3: Validation

How to verify it worked.

---

## Summary

What you accomplished.

---

## Next Steps

- [Next Tutorial](link)
- [Related Topic](link)
```

#### 4. Recipe

```markdown
# Recipe Title

One-sentence description of what this recipe does.

**Time**: 10 min | **Difficulty**: ⭐⭐ | **Platform**: Linux

---

## Use Case

When to use this recipe.

---

## Quick Steps

```bash
# Step 1: Command
command here

# Step 2: Another command
another command
```

---

## Complete Example

```yaml
# Full configuration
command: local
vmdk: /path/to/vm.vmdk
# ... rest of config
```

---

## Customization

How to adapt this recipe:
- Change X for Y scenario
- Add Z option for additional features

---

## Troubleshooting

Quick fixes for common issues.
```

---

## Emoji Usage Guide

Use emojis consistently for visual navigation:

| Emoji | Meaning | Usage |
|-------|---------|-------|
| 🚀 | Getting Started | Installation, quick start |
| 📚 | Documentation | Guides, references |
| 🎓 | Learning | Tutorials, education |
| 🍳 | Recipes | Quick solutions |
| 🛠️ | Tools | CLI, utilities |
| 🔧 | Features | Feature documentation |
| 🖥️ | OS-Specific | Operating system guides |
| 🚢 | Deployment | Deployment guides |
| 🔄 | Worker/Jobs | Worker protocol, jobs |
| 🔬 | Testing | Test results, validation |
| ⚡ | Quick Access | Fast reference |
| ✅ | Success/Done | Completed, working |
| ❌ | Error/No | Not working, don't do |
| ⭐ | Featured/Important | Highlighted content |
| 💡 | Tip | Helpful information |
| ⚠️ | Warning | Caution required |
| 🔗 | Links | Related documentation |
| 📊 | Metrics/Stats | Performance, statistics |
| 🎯 | Goal/Target | Objectives, use cases |

---

## Adding New Documentation

### Process

1. **Identify the type** of documentation (guide, tutorial, recipe, reference)
2. **Choose the location** based on the file organization guide
3. **Create the file** with appropriate naming
4. **Write content** following the structure templates
5. **Add navigation** - update parent README.md
6. **Cross-reference** - link from related docs
7. **Update indexes** - add to docs/index.md if major
8. **Test links** - verify all links work
9. **Submit PR** - for review

### Checklist for New Documentation

- [ ] File created in correct directory
- [ ] Follows naming convention
- [ ] Uses correct structure template
- [ ] Includes all required sections
- [ ] Has clear, concise content
- [ ] Includes code examples (if applicable)
- [ ] Links to related documentation
- [ ] Added to parent README.md
- [ ] Added to docs/index.md (if major)
- [ ] All links tested and working
- [ ] Spelling and grammar checked
- [ ] Follows emoji usage guide
- [ ] Screenshots/diagrams added (if needed)

---

## Updating Existing Docs

### When to Update

- New features added
- Bugs fixed or behavior changed
- Better examples discovered
- User feedback indicates confusion
- Links broken or outdated
- New best practices emerge

### Update Process

1. **Read the existing doc** completely
2. **Identify what needs updating** (content, links, examples)
3. **Make changes** while maintaining consistency
4. **Test all examples** to ensure they work
5. **Update "Last Updated"** date at bottom
6. **Submit PR** with clear description of changes

### Major vs Minor Updates

**Minor Updates** (direct commit):
- Fix typos
- Update broken links
- Clarify existing content
- Update dates/versions

**Major Updates** (PR required):
- Restructure document
- Add/remove major sections
- Change examples significantly
- Update architecture/design docs

---

## Code Examples

### YAML Examples

```yaml
# migration.yaml - Description of what this does
command: local
vmdk: /path/to/vm.vmdk
output_dir: /output
to_output: vm.qcow2

# Enable features
fstab_mode: stabilize-all  # Comment explaining why
regen_initramfs: true      # Another helpful comment
```

**Rules**:
- Include comments explaining non-obvious options
- Use realistic paths and names
- Show complete, working examples
- Indicate which parts users should customize

### Command Examples

```bash
# Description of what this command does
h2kvmctl migrate local /path/to/vm.vmdk --output /output/vm.qcow2

# Multi-line command with explanation
h2kvmctl --config << EOF
command: local
vmdk: /path/to/vm.vmdk
output_dir: /output
EOF
```

**Rules**:
- Start with a comment describing the command
- Use realistic paths
- Show output when helpful
- Include error handling if relevant

### Python Examples

```python
from h2kvm import Migration

# Create a migration instance
migration = Migration(
    vmdk="/path/to/vm.vmdk",
    output_dir="/output"
)

# Execute the migration
result = migration.run()
print(f"Migration complete: {result.success}")
```

**Rules**:
- Include imports
- Add comments for clarity
- Show complete, runnable examples
- Handle errors appropriately

---

## Tables and Lists

### Comparison Tables

Use tables for comparing options:

```markdown
| Feature | Option A | Option B |
|---------|----------|----------|
| Speed | Fast | Slower |
| Size | Large | Small |
| Use Case | Production | Testing |
```

### Configuration Tables

Use tables for documenting options:

```markdown
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `timeout` | integer | 300 | Operation timeout in seconds |
| `retry` | integer | 3 | Number of retry attempts |
```

### Ordered Lists

Use for sequential steps:

```markdown
1. First step
2. Second step
3. Third step
```

### Unordered Lists

Use for non-sequential items:

```markdown
- Item one
- Item two
- Item three
```

---

## Link Guidelines

### Internal Links

Use relative paths:

```markdown
- [Installation Guide](../getting-started/01-Installation.md)
- [API Reference](../reference/api/API-Reference.md)
```

### External Links

Include description:

```markdown
- [QEMU Documentation](https://www.qemu.org/docs/) - Official QEMU docs
```

### Anchor Links

For same-page navigation:

```markdown
- [Overview](#overview)
- [Examples](#examples)
```

---

## Images and Diagrams

### When to Include Images

- Architecture diagrams
- Workflow diagrams
- Screenshots (sparingly)
- Complex visualizations

### Image Guidelines

- Keep images small (<500 KB)
- Use PNG for screenshots
- Use SVG for diagrams (preferred)
- Store in `docs/images/` directory
- Use descriptive filenames

### Image Syntax

```markdown
![Alt text describing the image](../images/diagram-name.png)
```

---

## Review Process

### Self-Review Checklist

Before submitting:

- [ ] Spell-check completed
- [ ] Grammar checked
- [ ] All links tested
- [ ] Code examples tested
- [ ] Follows style guide
- [ ] Navigation updated
- [ ] Cross-references added

### Peer Review

Reviewers should check:

- [ ] Content accuracy
- [ ] Clarity and readability
- [ ] Completeness
- [ ] Consistency with existing docs
- [ ] All examples work
- [ ] Links functional
- [ ] Proper structure

---

## Documentation Testing

### Link Testing

```bash
# Check for broken links
find docs -name "*.md" -exec grep -H "](.*)" {} \; | \
  grep -v "http" | cut -d: -f2 | cut -d\( -f2 | cut -d\) -f1 | \
  while read link; do [ -f "$link" ] || echo "Broken: $link"; done
```

### Spell Checking

```bash
# Using aspell
find docs -name "*.md" -exec aspell check {} \;
```

### Example Testing

Always test code examples:

```bash
# Test YAML examples
yamllint docs/**/*.md

# Test bash examples (manually)
# Copy each bash example and run it
```

---

## Version Information

### Document Versioning

Include at the bottom of major documents:

```markdown
---

**Last Updated**: March 2026
**H2KVM Version**: 0.3.0
**Documentation Version**: 0.3.0
```

### Deprecated Documentation

For deprecated features:

```markdown
> ⚠️ **DEPRECATED**: This feature is deprecated as of v2.0.0.
> Use [New Feature](link-to-new.md) instead.
```

---

## Getting Help

### Questions About Documentation

- Check [Documentation Index](index.md)
- Review [Existing Examples](tutorials/)
- Ask in [GitHub Discussions](https://github.com/ssahani/h2kvm/discussions)

### Suggesting Improvements

- Open an issue: [GitHub Issues](https://github.com/ssahani/h2kvm/issues)
- Describe what's unclear
- Suggest improvements
- Submit a PR if you can

---

## Quick Reference

### Common Tasks

| Task | Command/Action |
|------|----------------|
| **Create new guide** | Add to appropriate directory, update README |
| **Update existing** | Edit file, test examples, update date |
| **Add to index** | Update docs/index.md |
| **Test links** | Run link checker or manual testing |
| **Submit changes** | Create PR with description |

---

## Examples of Good Documentation

### Well-Structured Documents

- [Getting Started Guide](getting-started/README.md) - Clear navigation and progression
- [Quick Reference](QUICK_REFERENCE.md) - Concise and scannable
- [Glossary](GLOSSARY.md) - Comprehensive and organized
- [GuestKit integration guide](features/architecture/GUESTKIT.md) - Thorough feature documentation

### Study These for Style

- Clear headings and structure
- Consistent formatting
- Helpful examples
- Good cross-referencing
- Professional tone
- User-focused content

---

**Last Updated**: March 2026
**Documentation Version**: 0.3.0
