# Development Container

Pre-configured development environment for hyper2kvm using VS Code Dev Containers
or GitHub Codespaces.

## Features

### Development Tools

- **Python 3.12** (configurable via build args)
- **Ruff** - Fast Python linter and formatter
- **Mypy** - Static type checker
- **Pre-commit** - Git hook framework
- **Pytest** - Testing framework with coverage

### System Dependencies

- **libvirt/KVM** - Virtualization libraries
- **NBD** - Network Block Device tools
- **LVM** - Logical Volume Manager
- **guestfs** - Guest filesystem access
- **QEMU** - Emulator and virtualizer
- **Cryptsetup** - LUKS encryption tools

### VS Code Extensions

Automatically installed:

- Python language support (Pylance)
- Ruff integration
- Mypy type checker
- Test adapter
- GitLens
- Markdown support
- YAML/TOML/JSON support
- Docker support
- EditorConfig support
- Spell checker

### Shell Environment

- Zsh with Oh My Zsh
- Git with LFS support
- GitHub CLI
- Docker-in-Docker
- Common utilities (ripgrep, fd, jq, htop, tree)

## Quick Start

### VS Code Dev Containers

1. **Prerequisites**:
   - [VS Code](https://code.visualstudio.com/)
   - [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
   - [Docker Desktop](https://www.docker.com/products/docker-desktop)

2. **Open in Container**:

   ```bash
   # Clone repository
   git clone https://github.com/ssahani/hyper2kvm.git
   cd hyper2kvm

   # Open in VS Code
   code .
   ```

3. **Reopen in Container**:
   - Press `F1` or `Ctrl+Shift+P`
   - Select: `Dev Containers: Reopen in Container`
   - Wait for container to build (first time: ~5-10 minutes)

4. **Start Developing**:
   - All dependencies are pre-installed
   - Pre-commit hooks are configured
   - Tests are ready to run

### GitHub Codespaces

1. **Create Codespace**:
   - Go to repository on GitHub
   - Click `Code` → `Codespaces` → `Create codespace on main`
   - Wait for environment to initialize

2. **Develop in Browser or VS Code**:
   - Browser: Automatic
   - Desktop: Click `Open in VS Code` in codespace

## Usage

### Running Tests

```bash
# Unit tests only
pytest tests/unit/

# With coverage
pytest --cov=hyper2kvm --cov-report=html

# Specific test
pytest tests/unit/test_vmcraft/test_block_device.py -v

# Parallel execution
pytest -n auto
```

### Code Quality

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Auto-fix issues
ruff check --fix .

# Type check
mypy hyper2kvm/

# Run all pre-commit hooks
pre-commit run --all-files
```

### Development Workflow

```bash
# Create branch
git checkout -b feature/my-feature

# Make changes
vim hyper2kvm/mymodule.py

# Run quality checks (automatic on commit)
git add .
git commit -m "feat: add new feature"

# Push
git push origin feature/my-feature
```

## Configuration

### Python Version

To use a different Python version, edit `.devcontainer/devcontainer.json`:

```json
{
  "build": {
    "args": {
      "PYTHON_VERSION": "3.11"  // Change here
    }
  }
}
```

### Additional Extensions

Add extensions to `.devcontainer/devcontainer.json`:

```json
{
  "customizations": {
    "vscode": {
      "extensions": [
        "your.extension.id"
      ]
    }
  }
}
```

### Container Features

Add features to `.devcontainer/devcontainer.json`:

```json
{
  "features": {
    "ghcr.io/devcontainers/features/node:1": {}
  }
}
```

## Mounted Directories

The container mounts your host's SSH and GPG directories (read-only) for:

- Git commit signing
- SSH key access for GitHub/GitLab
- GPG key access

## Privileged Mode

The container runs in privileged mode to support:

- KVM/libvirt operations
- NBD device management
- LVM operations
- Block device access

**Security Note**: Only use this container in trusted environments.

## Performance Tips

### First Build

The initial build takes 5-10 minutes to:

- Download base Python image (~500MB)
- Install system dependencies
- Install Python packages
- Configure environment

**Subsequent builds are much faster** (~30 seconds) due to Docker layer caching.

### Rebuild Container

If you modify Dockerfile or devcontainer.json:

```text
F1 → Dev Containers: Rebuild Container
```

### Clear Cache

If you encounter issues:

```text
F1 → Dev Containers: Rebuild Container Without Cache
```

## Troubleshooting

### Container Fails to Start

1. Check Docker is running:

   ```bash
   docker ps
   ```

2. Check Docker resources:
   - Minimum: 4GB RAM, 2 CPU cores
   - Recommended: 8GB RAM, 4 CPU cores

3. Check logs:

   ```text
   F1 → Dev Containers: Show Container Log
   ```

### Import Errors

Rebuild container or reinstall:

```bash
pip install -e ".[dev,test]" --force-reinstall
```

### Pre-commit Hooks Not Working

Reinstall hooks:

```bash
pre-commit uninstall
pre-commit install
```

### libvirt/KVM Not Working

Check user permissions:

```bash
groups  # Should include: libvirt, kvm
sudo usermod -a -G libvirt,kvm vscode
```

## Differences from Local Development

### Advantages

- ✅ Consistent environment across team
- ✅ Pre-configured tools and extensions
- ✅ Isolated from host system
- ✅ Easy to reset/rebuild
- ✅ Works on any OS (Windows/Mac/Linux)

### Limitations

- ⚠️ Slower than native on some operations
- ⚠️ Requires Docker Desktop
- ⚠️ Initial build time
- ⚠️ Privileged mode security consideration

## Advanced

### Custom Post-Create Commands

Edit `.devcontainer/post-create.sh` to add custom setup:

```bash
# Install additional tools
pip install my-tool

# Configure environment
echo "export MY_VAR=value" >> ~/.bashrc
```

### Docker Compose

For complex setups (databases, services), create
`.devcontainer/docker-compose.yml` and reference it in `devcontainer.json`.

### SSH Agent Forwarding

Add to `devcontainer.json`:

```json
{
  "mounts": [
    "source=/run/host-services/ssh-auth.sock,target=/ssh-agent,type=bind"
  ],
  "containerEnv": {
    "SSH_AUTH_SOCK": "/ssh-agent"
  }
}
```

## Resources

- [VS Code Dev Containers](https://code.visualstudio.com/docs/devcontainers/containers)
- [GitHub Codespaces](https://github.com/features/codespaces)
- [Dev Container Specification](https://containers.dev/)
- [Dev Container Features](https://github.com/devcontainers/features)

## Support

For issues or questions:

- GitHub Issues: <https://github.com/ssahani/hyper2kvm/issues>
- Documentation: [HACKING.md](../docs/HACKING.md)
