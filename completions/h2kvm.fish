# fish completion for h2kvm
# SPDX-License-Identifier: Apache-2.0
#
# This file provides fish completion for the h2kvm command.
# It is generated using argcomplete and provides intelligent completion
# for all h2kvm arguments and options.
#
# Installation:
#   sudo cp completions/h2kvm.fish /usr/share/fish/vendor_completions.d/
#   # or for user-local installation:
#   mkdir -p ~/.config/fish/completions
#   cp completions/h2kvm.fish ~/.config/fish/completions/
#
# Or use the install-completions.sh script to install for all shells.

register-python-argcomplete --shell fish h2kvm | source
