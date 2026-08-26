# Pre/Post Conversion Hooks Examples

This directory contains example configurations and scripts demonstrating hyper2kvm's pre/post conversion hooks feature.

## Overview

Hooks allow you to execute custom scripts, Python functions, or HTTP webhooks at various stages of the conversion pipeline:

- **pre_extraction**: Before disk extraction/manifest loading
- **post_extraction**: After manifest load, before offline fixes
- **pre_fix**: Before offline filesystem fixes
- **post_fix**: After fixes, before conversion
- **pre_convert**: Before format conversion
- **post_convert**: After conversion, before validation
- **post_validate**: After validation complete

## Hook Types

### 1. Script Hooks

Execute shell scripts with environment variables and arguments.

```json
{
  "type": "script",
  "path": "/path/to/script.sh",
  "args": ["arg1", "{{ variable }}"],
  "env": {
    "VM_NAME": "{{ vm_name }}",
    "SOURCE_PATH": "{{ source_path }}"
  },
  "timeout": 300,
  "continue_on_error": false,
  "working_directory": "/tmp"
}
```

### 2. Python Hooks

Call Python functions from importable modules.

```json
{
  "type": "python",
  "module": "migration_validators",
  "function": "verify_boot_config",
  "args": {
    "disk_path": "{{ source_path }}",
    "vm_name": "{{ vm_name }}"
  },
  "timeout": 300,
  "continue_on_error": false
}
```

### 3. HTTP Hooks

Send HTTP requests to webhooks or APIs.

```json
{
  "type": "http",
  "url": "https://api.example.com/webhook",
  "method": "POST",
  "headers": {
    "Authorization": "Bearer TOKEN"
  },
  "body": {
    "vm_name": "{{ vm_name }}",
    "stage": "{{ stage }}"
  },
  "timeout": 30,
  "continue_on_error": true
}
```

## Template Variables

Hooks support Jinja2-style variable substitution with `{{ variable }}`:

### Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `stage` | Current pipeline stage | `"pre_fix"` |
| `vm_name` | VM name from manifest | `"web-server-prod"` |
| `source_path` | Boot disk source path | `"/data/vm.vmdk"` |
| `output_path` | Converted disk path | `"/converted/boot.qcow2"` |
| `source_dir` | Source directory | `"/data"` |
| `source_filename` | Source filename | `"vm.vmdk"` |
| `output_dir` | Output directory | `"/converted"` |
| `output_filename` | Output filename | `"boot.qcow2"` |
| `timestamp` | Unix timestamp | `1737547200` |
| `timestamp_iso` | ISO 8601 timestamp | `"2026-01-22T10:00:00Z"` |
| `user` | Current user | `"root"` |
| `hostname` | System hostname | `"migration-host"` |
| `pwd` | Working directory | `"/work"` |
| `manifest_path` | Manifest file path | `"/work/manifest.json"` |

## Example Files

### Manifests

- **`manifest-with-hooks.json`**: Comprehensive example with all hook types
- **`manifest-simple-hooks.yaml`**: Simple notification hooks example

### Scripts

Located in `sample-hooks/`:

- **`notify-start.sh`**: Pre-extraction notification hook
- **`backup-disk.sh`**: Pre-fix disk backup hook
- **`migration_validators.py`**: Python validation functions

## Usage

### 1. Basic Script Hook

```bash
# Create a simple notification script
cat > /usr/local/bin/notify-start.sh <<'EOF'
#!/bin/bash
echo "Migration starting for $VM_NAME at $(date)"
logger -t hyper2kvm "Starting migration: $VM_NAME"
EOF

chmod +x /usr/local/bin/notify-start.sh

# Add to manifest
{
  "hooks": {
    "pre_extraction": [
      {
        "type": "script",
        "path": "/usr/local/bin/notify-start.sh",
        "env": {"VM_NAME": "{{ vm_name }}"},
        "timeout": 60
      }
    ]
  }
}
```

### 2. Python Validation Hook

```bash
# Create Python module (ensure it's importable)
cp sample-hooks/migration_validators.py /usr/local/lib/python3/dist-packages/

# Add to manifest
{
  "hooks": {
    "post_convert": [
      {
        "type": "python",
        "module": "migration_validators",
        "function": "verify_qcow2_integrity",
        "args": {"disk_path": "{{ output_path }}"},
        "timeout": 300
      }
    ]
  }
}
```

### 3. HTTP Webhook

```bash
# Send status updates to external API
{
  "hooks": {
    "post_convert": [
      {
        "type": "http",
        "url": "https://webhook.site/your-uuid",
        "method": "POST",
        "body": {
          "vm": "{{ vm_name }}",
          "status": "converted",
          "path": "{{ output_path }}"
        }
      }
    ]
  }
}
```

## Running Conversions with Hooks

```bash
# Run conversion with hooks enabled
sudo hyper2kvm --config manifest-with-hooks.json local

# Hooks will execute automatically at each stage
# Check logs for hook execution details:
# - "🪝 Executing N hook(s) for stage: pre_fix"
# - "⚡ Executing script hook: pre_fix[0]"
# - "✅ Hook pre_fix[0] succeeded in 2.34s"
```

## Hook Options

### `continue_on_error`

- `true`: Hook failure logged as warning, pipeline continues
- `false`: Hook failure stops pipeline (default)

```json
{
  "type": "script",
  "path": "/optional/notification.sh",
  "continue_on_error": true  // Don't fail pipeline if notification fails
}
```

### `timeout`

Maximum execution time in seconds (default: 300).

```json
{
  "type": "script",
  "path": "/long/backup.sh",
  "timeout": 3600  // 1 hour timeout
}
```

## Security Considerations

1. **Path Validation**: Script paths are validated with `U.safe_path()`
2. **Timeout Enforcement**: All hooks have timeouts to prevent hangs
3. **Process Isolation**: Scripts run in separate processes
4. **Environment Control**: Only explicitly configured env vars are passed

## Common Use Cases

### 1. Pre-Migration Backup

```json
{
  "hooks": {
    "pre_fix": [
      {
        "type": "script",
        "path": "/opt/scripts/backup-disk.sh",
        "args": ["{{ source_path }}", "/backups/{{ vm_name }}"],
        "timeout": 1800
      }
    ]
  }
}
```

### 2. Migration Tracking

```json
{
  "hooks": {
    "post_extraction": [
      {
        "type": "http",
        "url": "https://tracker.example.com/api/migrations",
        "method": "POST",
        "body": {
          "vm": "{{ vm_name }}",
          "stage": "started",
          "timestamp": "{{ timestamp_iso }}"
        }
      }
    ],
    "post_validate": [
      {
        "type": "http",
        "url": "https://tracker.example.com/api/migrations",
        "method": "POST",
        "body": {
          "vm": "{{ vm_name }}",
          "stage": "completed",
          "output": "{{ output_path }}"
        }
      }
    ]
  }
}
```

### 3. Custom Validation

```json
{
  "hooks": {
    "post_fix": [
      {
        "type": "python",
        "module": "custom_validators",
        "function": "check_bootloader",
        "args": {"disk": "{{ source_path }}"}
      }
    ],
    "post_convert": [
      {
        "type": "python",
        "module": "custom_validators",
        "function": "verify_disk_format",
        "args": {"disk": "{{ output_path }}", "format": "qcow2"}
      }
    ]
  }
}
```

## Troubleshooting

### Hook Not Executing

Check:
- Hook configuration is in `hooks` section of manifest
- Stage name is correct (e.g., `"pre_fix"`, not `"prefix"`)
- Script path exists and is executable
- Python module is importable

### Hook Timing Out

- Increase `timeout` value
- Check script/function for hangs
- Verify network connectivity for HTTP hooks

### Hook Failing

- Check hyper2kvm logs for detailed error messages
- Test script/function independently
- Use `continue_on_error: true` for non-critical hooks

## See Also

- Artifact Manifest v1 Specification: `docs/06-Artifact-Manifest-Spec-v1.md`
- Hook System Implementation: `hyper2kvm/hooks/`
- Hook Runner Source: `hyper2kvm/hooks/hook_runner.py`
