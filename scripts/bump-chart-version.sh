#!/bin/bash
#
# Bump Helm Chart Version
#
# This script increments the version of one or more Helm charts.
# Supports semantic versioning (major.minor.patch) and updates both
# Chart.yaml version and appVersion.
#
# Usage:
#   ./scripts/bump-chart-version.sh [--chart CHART] [--type TYPE] [--version VERSION]
#

set -e

# Colors for output

# Default configuration
CHART=""
BUMP_TYPE="patch"
NEW_VERSION=""
UPDATE_APP_VERSION=true
DRY_RUN=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --chart)
            CHART="$2"
            shift 2
            ;;
        --type)
            BUMP_TYPE="$2"
            shift 2
            ;;
        --version)
            NEW_VERSION="$2"
            shift 2
            ;;
        --no-app-version)
            UPDATE_APP_VERSION=false
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            cat <<EOF
Usage: $0 [OPTIONS]

Bump Helm chart version(s) following semantic versioning.

OPTIONS:
    --chart CHART        Chart name (e.g., h2kvm-operator, h2kvm-worker)
                         If not specified, bumps all charts
    --type TYPE          Bump type: major, minor, patch (default: patch)
    --version VERSION    Set specific version (overrides --type)
    --no-app-version     Don't update appVersion (only update chart version)
    --dry-run            Show what would be changed without modifying files
    -h, --help           Show this help message

EXAMPLES:
    # Bump patch version of all charts (1.6.0 -> 1.6.1)
    $0 --type patch

    # Bump minor version of operator chart (1.6.0 -> 1.7.0)
    $0 --chart h2kvm-operator --type minor

    # Set specific version
    $0 --chart h2kvm-operator --version 2.0.0

    # Dry run to see changes
    $0 --type minor --dry-run

SEMANTIC VERSIONING:
    major    X.0.0    Breaking changes
    minor    1.X.0    New features (backwards compatible)
    patch    1.6.X    Bug fixes

EOF
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

log_info() {
    echo "[INFO] $1"
}

log_success() {
    echo "[SUCCESS] $1"
}

log_error() {
    echo "[ERROR] $1"
}

log_warning() {
    echo "[WARNING] $1"
}

# Validate bump type
validate_bump_type() {
    case "$BUMP_TYPE" in
        major|minor|patch)
            return 0
            ;;
        *)
            log_error "Invalid bump type: $BUMP_TYPE (must be: major, minor, patch)"
            exit 1
            ;;
    esac
}

# Parse semantic version
parse_version() {
    local version=$1

    if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        log_error "Invalid version format: $version (expected: X.Y.Z)"
        return 1
    fi

    local major=$(echo "$version" | cut -d. -f1)
    local minor=$(echo "$version" | cut -d. -f2)
    local patch=$(echo "$version" | cut -d. -f3)

    echo "$major $minor $patch"
}

# Bump version
bump_version() {
    local current_version=$1
    local bump_type=$2

    local version_parts=($(parse_version "$current_version"))
    local major=${version_parts[0]}
    local minor=${version_parts[1]}
    local patch=${version_parts[2]}

    case "$bump_type" in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
    esac

    echo "${major}.${minor}.${patch}"
}

# Find all Helm charts
find_charts() {
    local charts=()

    # Find all Chart.yaml files
    while IFS= read -r chart_file; do
        local chart_dir=$(dirname "$chart_file")
        local chart_name=$(basename "$chart_dir")
        charts+=("$chart_name:$chart_dir")
    done < <(find helm -name "Chart.yaml" -type f)

    printf '%s\n' "${charts[@]}"
}

# Update chart version
update_chart_version() {
    local chart_name=$1
    local chart_dir=$2
    local chart_file="$chart_dir/Chart.yaml"

    if [ ! -f "$chart_file" ]; then
        log_error "Chart.yaml not found: $chart_file"
        return 1
    fi

    # Get current version
    local current_version=$(grep '^version:' "$chart_file" | awk '{print $2}')

    if [ -z "$current_version" ]; then
        log_error "Could not read current version from $chart_file"
        return 1
    fi

    # Calculate new version
    local new_version=""
    if [ -n "$NEW_VERSION" ]; then
        new_version="$NEW_VERSION"
        log_info "Setting version for $chart_name to $new_version (manual)"
    else
        new_version=$(bump_version "$current_version" "$BUMP_TYPE")
        log_info "Bumping version for $chart_name: $current_version -> $new_version ($BUMP_TYPE)"
    fi

    # Validate new version
    parse_version "$new_version" > /dev/null || return 1

    if [ "$DRY_RUN" = true ]; then
        log_warning "[DRY RUN] Would update $chart_name:"
        log_warning "  Chart version: $current_version -> $new_version"
        if [ "$UPDATE_APP_VERSION" = true ]; then
            local current_app_version=$(grep '^appVersion:' "$chart_file" | awk '{print $2}' | tr -d '"')
            log_warning "  App version:   $current_app_version -> $new_version"
        fi
        return 0
    fi

    # Update Chart.yaml
    # macOS and Linux have different sed syntax, so use a temp file approach
    sed "s/^version: .*/version: $new_version/" "$chart_file" > "${chart_file}.tmp"
    mv "${chart_file}.tmp" "$chart_file"

    if [ "$UPDATE_APP_VERSION" = true ]; then
        sed "s/^appVersion: .*/appVersion: \"$new_version\"/" "$chart_file" > "${chart_file}.tmp"
        mv "${chart_file}.tmp" "$chart_file"
    fi

    log_success "Updated $chart_name: $current_version -> $new_version"

    # Show diff
    log_info "Changes:"
    echo "  version: $current_version -> $new_version"
    if [ "$UPDATE_APP_VERSION" = true ]; then
        echo "  appVersion: \"$current_version\" -> \"$new_version\""
    fi
}

# Main execution
main() {
    echo "======================================"
    echo " Helm Chart Version Bump"
    echo "======================================"
    echo "Bump Type:        $BUMP_TYPE"
    echo "Target Chart:     ${CHART:-all}"
    echo "New Version:      ${NEW_VERSION:-auto}"
    echo "Update appVersion: $UPDATE_APP_VERSION"
    echo "Dry Run:          $DRY_RUN"
    echo "======================================"
    echo ""

    # Validate bump type
    if [ -z "$NEW_VERSION" ]; then
        validate_bump_type
    fi

    # Find all charts
    local all_charts=()
    while IFS= read -r entry; do
        [[ -n "$entry" ]] && all_charts+=("$entry")
    done < <(find_charts)

    if [ ${#all_charts[@]} -eq 0 ]; then
        log_error "No Helm charts found in helm/ directory"
        exit 1
    fi

    # Filter charts if specific chart requested
    local charts_to_update=()

    if [ -n "$CHART" ]; then
        local found=false
        for chart_entry in "${all_charts[@]}"; do
            local chart_name=$(echo "$chart_entry" | cut -d: -f1)
            if [ "$chart_name" = "$CHART" ]; then
                charts_to_update+=("$chart_entry")
                found=true
                break
            fi
        done

        if [ "$found" = false ]; then
            log_error "Chart not found: $CHART"
            log_info "Available charts:"
            for chart_entry in "${all_charts[@]}"; do
                local chart_name=$(echo "$chart_entry" | cut -d: -f1)
                echo "  - $chart_name"
            done
            exit 1
        fi
    else
        charts_to_update=("${all_charts[@]}")
    fi

    # Update charts
    local updated=0
    local failed=0

    for chart_entry in "${charts_to_update[@]}"; do
        local chart_name=$(echo "$chart_entry" | cut -d: -f1)
        local chart_dir=$(echo "$chart_entry" | cut -d: -f2)

        if update_chart_version "$chart_name" "$chart_dir"; then
            updated=$((updated + 1))
        else
            failed=$((failed + 1))
        fi
        echo ""
    done

    # Summary
    echo "======================================"
    echo " Version Bump Summary"
    echo "======================================"
    if [ "$DRY_RUN" = true ]; then
        echo "DRY RUN - No files modified"
    fi
    echo "Updated: $updated chart(s)"
    echo "Failed:  $failed chart(s)"
    echo "======================================"

    if [ $failed -eq 0 ]; then
        if [ "$DRY_RUN" = false ]; then
            log_success "All charts updated successfully!"

            echo ""
            echo "Next steps:"
            echo "  1. Review changes: git diff helm/"
            echo "  2. Package charts: ./scripts/package-charts.sh"
            echo "  3. Commit changes:"
            echo "     git add helm/"
            echo "     git commit -m 'chore: bump chart version to ${NEW_VERSION:-\$NEW_VERSION}'"
            echo "  4. Create tag: git tag v${NEW_VERSION:-\$NEW_VERSION}"
            echo "  5. Push: git push && git push --tags"
        fi
        return 0
    else
        log_error "Some charts failed to update"
        return 1
    fi
}

# Run main
main "$@"
