#!/bin/bash
# Script to create GitHub labels for Dependabot and issue management
# Run this once to set up labels in your repository

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Creating GitHub labels...${NC}\n"

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo -e "${RED}Error: GitHub CLI (gh) is not installed.${NC}"
    echo "Install it from: https://cli.github.com/"
    echo ""
    echo "Or create labels manually via GitHub web interface:"
    echo "  https://github.com/ssahani/hyper2kvm/labels"
    exit 1
fi

# Create labels using gh CLI
create_label() {
    local name=$1
    local color=$2
    local description=$3

    echo -e "Creating label: ${GREEN}${name}${NC}"
    gh label create "$name" --color "$color" --description "$description" 2>/dev/null

    if [ $? -eq 0 ]; then
        echo -e "  ✓ Created successfully\n"
    else
        echo -e "  ℹ Label already exists or creation failed\n"
    fi
}

# Dependabot labels
create_label "dependencies" "0366d6" "Pull requests that update a dependency file"
create_label "github-actions" "000000" "Pull requests that update GitHub Actions workflows"
create_label "python" "2b67c6" "Python dependency updates"

# Standard issue labels
create_label "bug" "d73a4a" "Something isn't working"
create_label "enhancement" "a2eeef" "New feature or request"
create_label "documentation" "0075ca" "Improvements or additions to documentation"
create_label "good first issue" "7057ff" "Good for newcomers"
create_label "help wanted" "008672" "Extra attention is needed"
create_label "question" "d876e3" "Further information is requested"
create_label "wontfix" "ffffff" "This will not be worked on"
create_label "duplicate" "cfd3d7" "This issue or pull request already exists"
create_label "invalid" "e4e669" "This doesn't seem right"

# Priority labels
create_label "priority: critical" "b60205" "Critical priority - blocking issue"
create_label "priority: high" "d93f0b" "High priority"
create_label "priority: medium" "fbca04" "Medium priority"
create_label "priority: low" "0e8a16" "Low priority"

# Type labels
create_label "type: security" "ee0701" "Security-related issue"
create_label "type: performance" "1d76db" "Performance improvement"
create_label "type: refactor" "ededed" "Code refactoring"
create_label "type: test" "c5def5" "Testing-related"

echo -e "${GREEN}✓ Label creation complete!${NC}"
echo ""
echo "You can view all labels at:"
echo "  https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/labels"
