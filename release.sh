#!/bin/bash
#
# Creates a GitHub release with the built zip and updates the Homebrew cask formula.
# Prerequisites: gh CLI authenticated, dist/FloatingClock.zip exists (run build.sh first)
#
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VERSION=$(cat VERSION | tr -d '[:space:]')
TAG="v$VERSION"
ZIP="dist/FloatingClock.zip"

if [ ! -f "$ZIP" ]; then
    echo "Error: $ZIP not found. Run build.sh first."
    exit 1
fi

SHA=$(shasum -a 256 "$ZIP" | cut -d ' ' -f 1)

echo "==> Releasing FloatingClock $TAG"
echo "    SHA-256: $SHA"

# ---------------------------------------------------------------------------
# Git: commit version bump + tag
# ---------------------------------------------------------------------------
echo "==> Committing version bump..."
git add VERSION
git commit -m "Bump version to $VERSION" --allow-empty 2>/dev/null || true
git tag -a "$TAG" -m "Release $VERSION"
git push origin HEAD
git push origin "$TAG"

# ---------------------------------------------------------------------------
# GitHub Release
# ---------------------------------------------------------------------------
echo "==> Creating GitHub release $TAG..."
gh release create "$TAG" "$ZIP" \
    --title "Floating Clock $VERSION" \
    --notes "Floating Clock $VERSION

## Install

**Homebrew:**
\`\`\`
brew tap surya-prakash-susarla/tap
brew install --cask floating-clock
\`\`\`

**curl:**
\`\`\`
curl -fsSL https://raw.githubusercontent.com/surya-prakash-susarla/OnScreenClock/main/install.sh | bash
\`\`\`

**Manual:** Download \`FloatingClock.zip\`, extract, move to Applications."

# ---------------------------------------------------------------------------
# Update Homebrew cask formula
# ---------------------------------------------------------------------------
echo "==> Updating Homebrew cask formula..."
CASK_FILE="homebrew/floating-clock.rb"
sed -i '' "s/version \".*\"/version \"$VERSION\"/" "$CASK_FILE"
sed -i '' "s/sha256 \".*\"/sha256 \"$SHA\"/" "$CASK_FILE"

echo ""
echo "Done! Released $TAG"
echo ""
echo "Next steps:"
echo "  1. Copy homebrew/floating-clock.rb to your homebrew-tap repo:"
echo "     surya-prakash-susarla/homebrew-tap → Casks/floating-clock.rb"
echo "  2. Commit and push that repo"
echo "  3. Users can then: brew tap surya-prakash-susarla/tap && brew install --cask floating-clock"
