#compdef h2kvm
# zsh completion for h2kvm
# SPDX-License-Identifier: Apache-2.0
#
# This file provides zsh completion for the h2kvm command.
# It is generated using argcomplete and provides intelligent completion
# for all h2kvm arguments and options.
#
# Installation:
#   sudo cp completions/h2kvm.zsh /usr/share/zsh/site-functions/_h2kvm
#   # or for user-local installation:
#   mkdir -p ~/.zsh/completion
#   cp completions/h2kvm.zsh ~/.zsh/completion/_h2kvm
#   # Add to ~/.zshrc:
#   fpath=(~/.zsh/completion $fpath)
#   autoload -Uz compinit && compinit
#
# Or use the install-completions.sh script to install for all shells.

# Enable bashcompinit for argcomplete compatibility
autoload -U bashcompinit
bashcompinit

eval "$(register-python-argcomplete h2kvm)"
