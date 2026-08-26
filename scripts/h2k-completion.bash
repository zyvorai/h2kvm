#!/bin/bash
# Bash completion for h2k CLI
# Install: source scripts/h2k-completion.bash
# Or:      cp scripts/h2k-completion.bash /etc/bash_completion.d/h2k

_h2k_completions() {
    local cur prev commands
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    commands="setup migrate deploy-operator status teardown health preflight logs debug-bundle backup help"

    case "$prev" in
        h2k)
            COMPREPLY=($(compgen -W "$commands" -- "$cur"))
            return 0
            ;;
        migrate)
            # Complete with .vmdk files or --operator flag
            COMPREPLY=($(compgen -f -X '!*.vmdk' -- "$cur"))
            COMPREPLY+=($(compgen -W "--operator" -- "$cur"))
            return 0
            ;;
        --operator)
            # Complete with http URLs (no completion, just hint)
            COMPREPLY=()
            return 0
            ;;
        teardown|remove|uninstall)
            COMPREPLY=($(compgen -W "--all --operator --workers --migrations" -- "$cur"))
            return 0
            ;;
        preflight)
            COMPREPLY=($(compgen -W "--fix" -- "$cur"))
            return 0
            ;;
        debug-bundle)
            COMPREPLY=($(compgen -d -- "$cur"))
            return 0
            ;;
    esac

    # Default: complete with commands
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=($(compgen -W "$commands" -- "$cur"))
    fi
}

complete -F _h2k_completions h2k
complete -F _h2k_completions ./scripts/h2k
