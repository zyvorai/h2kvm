# fish completion for hyper2kvm
# SPDX-License-Identifier: Apache-2.0
#
# This file provides fish completion for the hyper2kvm command.
# It is generated using argcomplete and provides intelligent completion
# for all hyper2kvm arguments and options.
#
# Installation:
#   sudo cp completions/hyper2kvm.fish /usr/share/fish/vendor_completions.d/
#   # or for user-local installation:
#   mkdir -p ~/.config/fish/completions
#   cp completions/hyper2kvm.fish ~/.config/fish/completions/
#
# Or use the install-completions.sh script to install for all shells.

register-python-argcomplete --shell fish hyper2kvm | source
