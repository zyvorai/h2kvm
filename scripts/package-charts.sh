#!/bin/bash
#
# Package Helm Charts and Update Repository Index
#
# This script packages all Helm charts and generates/updates the Helm repository index.
# Designed for both local testing and CI/CD automation.
#
# Usage:
#   ./scripts/package-charts.sh [--output-dir DIR] [--update-index]
#

set -e

# Default configuration
OUTPUT_DIR="${OUTPUT_DIR:-./charts}"
UPDATE_INDEX="${UPDATE_INDEX:-false}"
REPO_URL="${REPO_URL:-https://ssahani.github.io/h2kvm}"

# Colors for output

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --update-index)
            UPDATE_INDEX=true
            shift
            ;;
        --repo-url)
            REPO_URL="$2"
            shift 2
            ;;
        -h|--help)
            cat <<EOF
Usage: $0 [OPTIONS]

Package Helm charts and generate repository index.

OPTIONS:
    --output-dir DIR     Output directory for packaged charts (default: ./charts)
    --update-index       Update existing index.yaml instead of creating new one
    --repo-url URL       Repository URL for index.yaml (default: https://ssahani.github.io/h2kvm)
    -h, --help           Show this help message

EXAMPLES:
    # Package charts to ./charts directory
    $0

    # Package and update existing index
    $0 --update-index

    # Package to custom directory
    $0 --output-dir /tmp/charts

    # Package for custom repository URL
    $0 --repo-url https://example.com/charts

ENVIRONMENT VARIABLES:
    OUTPUT_DIR           Override default output directory
    UPDATE_INDEX         Set to 'true' to update existing index
    REPO_URL             Override default repository URL

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

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v helm &> /dev/null; then
        log_error "helm not found. Please install Helm 3.8+"
        exit 1
    fi

    local helm_version=$(helm version --short | grep -oE 'v[0-9]+\.[0-9]+' | sed 's/v//')
    local helm_major=$(echo "$helm_version" | cut -d. -f1)
    local helm_minor=$(echo "$helm_version" | cut -d. -f2)

    if [ "$helm_major" -lt 3 ] || ([ "$helm_major" -eq 3 ] && [ "$helm_minor" -lt 8 ]); then
        log_error "Helm 3.8+ required, found version $helm_version"
        exit 1
    fi

    log_success "Helm version: $(helm version --short)"
}

# Find all Helm charts
find_charts() {
    log_info "Searching for Helm charts..." >&2

    local charts=()

    # Find all Chart.yaml files
    while IFS= read -r chart_file; do
        local chart_dir=$(dirname "$chart_file")
        charts+=("$chart_dir")
    done < <(find helm -name "Chart.yaml" -type f)

    if [ ${#charts[@]} -eq 0 ]; then
        log_error "No Helm charts found in helm/ directory" >&2
        exit 1
    fi

    log_success "Found ${#charts[@]} chart(s): ${charts[*]}" >&2
    printf '%s\n' "${charts[@]}"
}

# Lint chart
lint_chart() {
    local chart_dir=$1
    local chart_name=$(basename "$chart_dir")

    log_info "Linting chart: $chart_name"

    if helm lint "$chart_dir" &> /dev/null; then
        log_success "Chart $chart_name passed linting"
        return 0
    else
        log_error "Chart $chart_name failed linting"
        helm lint "$chart_dir"
        return 1
    fi
}

# Package chart
package_chart() {
    local chart_dir=$1
    local chart_name=$(basename "$chart_dir")

    log_info "Packaging chart: $chart_name"

    # Create output directory if it doesn't exist
    mkdir -p "$OUTPUT_DIR"

    # Package the chart
    if helm package "$chart_dir" --destination "$OUTPUT_DIR" &> /dev/null; then
        local version=$(helm show chart "$chart_dir" | grep '^version:' | awk '{print $2}')
        local package_file="${chart_name}-${version}.tgz"

        log_success "Packaged $chart_name:$version -> $OUTPUT_DIR/$package_file"

        # Calculate and display package size
        if [ -f "$OUTPUT_DIR/$package_file" ]; then
            local size=$(du -h "$OUTPUT_DIR/$package_file" | cut -f1)
            log_info "Package size: $size"
        fi

        return 0
    else
        log_error "Failed to package chart $chart_name"
        helm package "$chart_dir" --destination "$OUTPUT_DIR"
        return 1
    fi
}

# Generate or update repository index
generate_index() {
    log_info "Generating repository index..."

    if [ "$UPDATE_INDEX" = true ] && [ -f "$OUTPUT_DIR/index.yaml" ]; then
        log_info "Updating existing index.yaml"
        helm repo index "$OUTPUT_DIR" --url "$REPO_URL" --merge "$OUTPUT_DIR/index.yaml"
    else
        log_info "Creating new index.yaml"
        helm repo index "$OUTPUT_DIR" --url "$REPO_URL"
    fi

    if [ -f "$OUTPUT_DIR/index.yaml" ]; then
        log_success "Repository index generated: $OUTPUT_DIR/index.yaml"

        # Display index statistics
        local chart_count=$(grep -c "^  [a-zA-Z]" "$OUTPUT_DIR/index.yaml" || true)
        local version_count=$(grep -c "  - " "$OUTPUT_DIR/index.yaml" || true)

        log_info "Index contains $chart_count chart(s) with $version_count version(s)"
    else
        log_error "Failed to generate index.yaml"
        return 1
    fi
}

# Verify packaged charts
verify_packages() {
    log_info "Verifying packaged charts..."

    local failed=0

    for package in "$OUTPUT_DIR"/*.tgz; do
        if [ ! -f "$package" ]; then
            continue
        fi

        local package_name=$(basename "$package")

        # Test extraction
        if tar -tzf "$package" &> /dev/null; then
            log_success "Verified: $package_name"
        else
            log_error "Corrupt package: $package_name"
            failed=$((failed + 1))
        fi
    done

    if [ $failed -eq 0 ]; then
        log_success "All packages verified successfully"
        return 0
    else
        log_error "$failed package(s) failed verification"
        return 1
    fi
}

# Main execution
main() {
    echo "======================================"
    echo " Helm Chart Packaging"
    echo "======================================"
    echo "Output Directory: $OUTPUT_DIR"
    echo "Repository URL:   $REPO_URL"
    echo "Update Index:     $UPDATE_INDEX"
    echo "======================================"
    echo ""

    check_prerequisites

    # Find all charts
    local charts=()
    while IFS= read -r entry; do
        [[ -n "$entry" ]] && charts+=("$entry")
    done < <(find_charts)

    # Lint and package each chart
    local packaged=0
    local failed=0

    for chart_dir in "${charts[@]}"; do
        if lint_chart "$chart_dir"; then
            if package_chart "$chart_dir"; then
                packaged=$((packaged + 1))
            else
                failed=$((failed + 1))
            fi
        else
            failed=$((failed + 1))
        fi
        echo ""
    done

    # Verify packages
    verify_packages
    echo ""

    # Generate index
    generate_index
    echo ""

    # Summary
    echo "======================================"
    echo " Packaging Summary"
    echo "======================================"
    echo "Packaged: $packaged chart(s)"
    echo "Failed:   $failed chart(s)"
    echo "Output:    $OUTPUT_DIR"
    echo "======================================"

    if [ $failed -eq 0 ]; then
        log_success "All charts packaged successfully!"

        echo ""
        echo "Next steps:"
        echo "  1. Review packaged charts in $OUTPUT_DIR"
        echo "  2. Test installation:"
        echo "     helm install test-release $OUTPUT_DIR/<chart>.tgz"
        echo "  3. Publish to GitHub Pages:"
        echo "     git checkout gh-pages"
        echo "     cp $OUTPUT_DIR/* ."
        echo "     git add ."
        echo "     git commit -m 'Release charts'"
        echo "     git push origin gh-pages"

        return 0
    else
        log_error "Some charts failed to package"
        return 1
    fi
}

# Run main
main "$@"
