#compdef hyper2kvm
# zsh completion for hyper2kvm
# SPDX-License-Identifier: Apache-2.0
#
# This file provides zsh completion for the hyper2kvm command.
# It is generated using argcomplete and provides intelligent completion
# for all hyper2kvm arguments and options.
#
# Installation:
#   sudo cp completions/hyper2kvm.zsh /usr/share/zsh/site-functions/_hyper2kvm
#   # or for user-local installation:
#   mkdir -p ~/.zsh/completion
#   cp completions/hyper2kvm.zsh ~/.zsh/completion/_hyper2kvm
#   # Add to ~/.zshrc:
#   fpath=(~/.zsh/completion $fpath)
#   autoload -Uz compinit && compinit
#
# Or use the install-completions.sh script to install for all shells.

# Enable bashcompinit for argcomplete compatibility
autoload -U bashcompinit
bashcompinit

eval "$(register-python-argcomplete hyper2kvm)"
