# Shell Completion for h2kvm

This directory contains shell completion scripts for the `h2kvm` command. Shell completion provides intelligent command-line tab completion for all h2kvm arguments, options, and flags.

## Features

- **Argument completion**: Tab-complete all command-line arguments
- **Option completion**: Tab-complete option names (e.g., `--vmdk`, `--vcenter`)
- **Path completion**: Intelligent path completion for file arguments
- **Multi-shell support**: Works with bash, zsh, and fish shells

## Quick Installation

### Automatic Installation (Recommended)

Run the installation script to automatically install completions for your shell:

```bash
# Interactive installation
./completions/install-completions.sh

# Or install for a specific shell
./completions/install-completions.sh bash
./completions/install-completions.sh zsh
./completions/install-completions.sh fish

# Install for all shells
./completions/install-completions.sh all
```

### Prerequisites

The completion scripts require `argcomplete` to be installed:

```bash
# Install via pip
pip install argcomplete

# Or via system package manager
sudo dnf install python3-argcomplete  # Fedora/RHEL/CentOS
sudo apt install python3-argcomplete  # Debian/Ubuntu
sudo pacman -S python-argcomplete     # Arch Linux
```

## Manual Installation

### Bash

**System-wide installation:**
```bash
sudo cp completions/h2kvm.bash /etc/bash_completion.d/h2kvm
```

**User-local installation:**
```bash
mkdir -p ~/.bash_completion.d
cp completions/h2kvm.bash ~/.bash_completion.d/h2kvm
echo '[ -f ~/.bash_completion.d/h2kvm ] && source ~/.bash_completion.d/h2kvm' >> ~/.bashrc
source ~/.bashrc
```

**Temporary installation (current session only):**
```bash
source completions/h2kvm.bash
```

### Zsh

**System-wide installation:**
```bash
sudo cp completions/h2kvm.zsh /usr/share/zsh/site-functions/_h2kvm
exec zsh
```

**User-local installation:**
```bash
mkdir -p ~/.zsh/completion
cp completions/h2kvm.zsh ~/.zsh/completion/_h2kvm

# Add to ~/.zshrc (if not already present)
cat >> ~/.zshrc << 'EOF'

# h2kvm completion
fpath=(~/.zsh/completion $fpath)
autoload -Uz compinit && compinit
EOF

exec zsh
```

### Fish

**System-wide installation:**
```bash
sudo cp completions/h2kvm.fish /usr/share/fish/vendor_completions.d/
```

**User-local installation:**
```bash
mkdir -p ~/.config/fish/completions
cp completions/h2kvm.fish ~/.config/fish/completions/
```

Fish completions are loaded automatically and take effect immediately.

## Usage

After installation, you can use tab completion with the `h2kvm` command:

```bash
# Press TAB to see available options
h2kvm --<TAB>

# Press TAB to complete option names
h2kvm --vm<TAB>
# Completes to: h2kvm --vmdk

# Press TAB to complete paths
h2kvm --vmdk /path/to/<TAB>

# Works with all arguments
h2kvm --vcenter <TAB>
```

## Verifying Installation

To verify that completion is working:

1. **Bash/Zsh**: Type `h2kvm --` and press TAB twice. You should see a list of available options.
2. **Fish**: Type `h2kvm --` and press TAB once. You should see completions appear.

If completion doesn't work:

1. Verify `argcomplete` is installed: `pip show argcomplete`
2. Verify `h2kvm` is in your PATH: `which h2kvm`
3. For bash, ensure bash-completion is installed: `apt install bash-completion` or `dnf install bash-completion`
4. Check that the completion script is sourced in your shell configuration file

## Troubleshooting

### Bash: Completion not working

1. Check if bash-completion is installed and enabled:
   ```bash
   # Fedora/RHEL
   sudo dnf install bash-completion

   # Debian/Ubuntu
   sudo apt install bash-completion
   ```

2. Ensure `/etc/profile.d/bash_completion.sh` is being sourced in your shell

3. Manually source the completion file:
   ```bash
   source /etc/bash_completion.d/h2kvm
   # or
   source ~/.bash_completion.d/h2kvm
   ```

### Zsh: Completion not working

1. Verify `compinit` is loaded:
   ```bash
   echo $fpath
   autoload -Uz compinit && compinit
   ```

2. Rebuild completion cache:
   ```bash
   rm -f ~/.zcompdump*
   exec zsh
   ```

### Fish: Completion not working

1. Check fish version (requires Fish 3.0+):
   ```bash
   fish --version
   ```

2. Verify completion file location:
   ```bash
   ls ~/.config/fish/completions/h2kvm.fish
   # or
   ls /usr/share/fish/vendor_completions.d/h2kvm.fish
   ```

### Python argcomplete not found

If you see "command not found: register-python-argcomplete":

```bash
# Install argcomplete
pip install argcomplete

# Ensure it's in your PATH
which register-python-argcomplete
```

## Uninstallation

To remove shell completions:

**Bash:**
```bash
sudo rm /etc/bash_completion.d/h2kvm
# or
rm ~/.bash_completion.d/h2kvm
```

**Zsh:**
```bash
sudo rm /usr/share/zsh/site-functions/_h2kvm
# or
rm ~/.zsh/completion/_h2kvm
```

**Fish:**
```bash
sudo rm /usr/share/fish/vendor_completions.d/h2kvm.fish
# or
rm ~/.config/fish/completions/h2kvm.fish
```

## How It Works

The completion scripts use [argcomplete](https://github.com/kislyuk/argcomplete), which provides intelligent shell completion for Python argparse-based CLI tools. When you press TAB:

1. The shell calls `register-python-argcomplete`
2. argcomplete invokes `h2kvm` with special environment variables
3. h2kvm's argument parser provides completion suggestions
4. The shell displays the suggestions

## Development

To test completion during development:

```bash
# Activate development environment
source venv/bin/activate

# Install h2kvm in development mode
pip install -e .

# Source the completion script
source completions/h2kvm.bash  # for bash
# or
source completions/h2kvm.zsh   # for zsh
```

## References

- [argcomplete documentation](https://kislyuk.github.io/argcomplete/)
- [Bash completion guide](https://www.gnu.org/software/bash/manual/html_node/Programmable-Completion.html)
- [Zsh completion guide](http://zsh.sourceforge.net/Doc/Release/Completion-System.html)
- [Fish completion guide](https://fishshell.com/docs/current/completions.html)

## License

These completion scripts are part of h2kvm and are licensed under Apache-2.0.
