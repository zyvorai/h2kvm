#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Shell completion installation script for hyper2kvm

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}hyper2kvm Shell Completion Installer${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Check if argcomplete is installed
check_argcomplete() {
    if ! command -v register-python-argcomplete &> /dev/null; then
        print_error "argcomplete is not installed"
        echo
        echo "Please install argcomplete first:"
        echo "  pip install argcomplete"
        echo "  # or"
        echo "  sudo dnf install python3-argcomplete  # Fedora/RHEL"
        echo "  sudo apt install python3-argcomplete  # Debian/Ubuntu"
        exit 1
    fi
}

# Install bash completion
install_bash() {
    print_info "Installing bash completion..."

    # Try system-wide installation first
    if [ -w /etc/bash_completion.d/ ]; then
        sudo cp "${SCRIPT_DIR}/hyper2kvm.bash" /etc/bash_completion.d/hyper2kvm
        print_success "Installed system-wide bash completion to /etc/bash_completion.d/"
        echo "  Completion will be available in new bash sessions"
    # Fallback to user-local installation
    elif [ -d "${HOME}/.bash_completion.d" ] || mkdir -p "${HOME}/.bash_completion.d"; then
        cp "${SCRIPT_DIR}/hyper2kvm.bash" "${HOME}/.bash_completion.d/hyper2kvm"
        print_success "Installed user-local bash completion to ~/.bash_completion.d/"

        # Add sourcing to .bashrc if not already present
        if ! grep -q ".bash_completion.d/hyper2kvm" "${HOME}/.bashrc" 2>/dev/null; then
            echo "" >> "${HOME}/.bashrc"
            echo "# hyper2kvm completion" >> "${HOME}/.bashrc"
            echo "[ -f ~/.bash_completion.d/hyper2kvm ] && source ~/.bash_completion.d/hyper2kvm" >> "${HOME}/.bashrc"
            print_info "Added source line to ~/.bashrc"
        fi
        echo "  Run: source ~/.bashrc"
    else
        print_error "Could not find or create bash completion directory"
        print_info "Manual installation: source ${SCRIPT_DIR}/hyper2kvm.bash"
        return 1
    fi
}

# Install zsh completion
install_zsh() {
    print_info "Installing zsh completion..."

    # Try system-wide installation first
    if [ -w /usr/share/zsh/site-functions/ ]; then
        sudo cp "${SCRIPT_DIR}/hyper2kvm.zsh" /usr/share/zsh/site-functions/_hyper2kvm
        print_success "Installed system-wide zsh completion to /usr/share/zsh/site-functions/"
        echo "  Run: exec zsh"
    # Fallback to user-local installation
    else
        mkdir -p "${HOME}/.zsh/completion"
        cp "${SCRIPT_DIR}/hyper2kvm.zsh" "${HOME}/.zsh/completion/_hyper2kvm"
        print_success "Installed user-local zsh completion to ~/.zsh/completion/"

        # Add to fpath in .zshrc if not already present
        if ! grep -q "fpath.*zsh/completion" "${HOME}/.zshrc" 2>/dev/null; then
            echo "" >> "${HOME}/.zshrc"
            echo "# hyper2kvm completion" >> "${HOME}/.zshrc"
            echo 'fpath=(~/.zsh/completion $fpath)' >> "${HOME}/.zshrc"
            echo "autoload -Uz compinit && compinit" >> "${HOME}/.zshrc"
            print_info "Added completion configuration to ~/.zshrc"
        fi
        echo "  Run: exec zsh"
    fi
}

# Install fish completion
install_fish() {
    print_info "Installing fish completion..."

    # Try system-wide installation first
    if [ -w /usr/share/fish/vendor_completions.d/ ]; then
        sudo cp "${SCRIPT_DIR}/hyper2kvm.fish" /usr/share/fish/vendor_completions.d/
        print_success "Installed system-wide fish completion to /usr/share/fish/vendor_completions.d/"
        echo "  Completion will be available immediately"
    # Fallback to user-local installation
    else
        mkdir -p "${HOME}/.config/fish/completions"
        cp "${SCRIPT_DIR}/hyper2kvm.fish" "${HOME}/.config/fish/completions/"
        print_success "Installed user-local fish completion to ~/.config/fish/completions/"
        echo "  Completion will be available immediately"
    fi
}

# Detect current shell
detect_shell() {
    if [ -n "$BASH_VERSION" ]; then
        echo "bash"
    elif [ -n "$ZSH_VERSION" ]; then
        echo "zsh"
    elif [ -n "$FISH_VERSION" ]; then
        echo "fish"
    else
        # Fallback to $SHELL variable
        basename "$SHELL"
    fi
}

# Main installation
main() {
    print_header
    check_argcomplete
    echo

    CURRENT_SHELL=$(detect_shell)
    print_info "Detected shell: $CURRENT_SHELL"
    echo

    # Check for command line argument
    if [ $# -eq 1 ]; then
        case "$1" in
            bash)
                install_bash
                ;;
            zsh)
                install_zsh
                ;;
            fish)
                install_fish
                ;;
            all)
                install_bash
                echo
                install_zsh
                echo
                install_fish
                ;;
            *)
                print_error "Unknown shell: $1"
                echo "Usage: $0 [bash|zsh|fish|all]"
                exit 1
                ;;
        esac
    else
        # Interactive mode
        echo "Which shell completion would you like to install?"
        echo "  1) Bash"
        echo "  2) Zsh"
        echo "  3) Fish"
        echo "  4) All shells"
        echo "  5) Current shell only ($CURRENT_SHELL)"
        echo
        read -p "Enter your choice [1-5]: " choice

        case $choice in
            1)
                install_bash
                ;;
            2)
                install_zsh
                ;;
            3)
                install_fish
                ;;
            4)
                install_bash
                echo
                install_zsh
                echo
                install_fish
                ;;
            5)
                case "$CURRENT_SHELL" in
                    bash)
                        install_bash
                        ;;
                    zsh)
                        install_zsh
                        ;;
                    fish)
                        install_fish
                        ;;
                    *)
                        print_error "Unsupported shell: $CURRENT_SHELL"
                        exit 1
                        ;;
                esac
                ;;
            *)
                print_error "Invalid choice"
                exit 1
                ;;
        esac
    fi

    echo
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}Installation complete!${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo
    echo "To enable completion in your current session:"
    echo "  Bash: source ~/.bashrc"
    echo "  Zsh:  exec zsh"
    echo "  Fish: Completions are immediately available"
    echo
}

# Run main function
main "$@"
