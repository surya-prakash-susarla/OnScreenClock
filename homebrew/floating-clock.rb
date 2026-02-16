# Homebrew Cask formula for Floating Clock
#
# To use this:
# 1. Create a repo: github.com/surya-prakash-susarla/homebrew-tap
# 2. Place this file at: Casks/floating-clock.rb
# 3. Users install with:
#      brew tap surya-prakash-susarla/tap
#      brew install --cask floating-clock
#
# After creating a GitHub release, update the url and sha256 below.
# Generate sha256 with: shasum -a 256 FloatingClock.zip

cask "floating-clock" do
  version "0.0.1"
  sha256 "e97ed08a4717681ace8e35476ebafa7e7c7c5c78c7f1181951b91c7e120a1d0a"

  url "https://github.com/surya-prakash-susarla/OnScreenClock/releases/download/v#{version}/FloatingClock.zip"
  name "Floating Clock"
  desc "Always-on-top floating clock for macOS with timer, network stats, and system monitoring"
  homepage "https://github.com/surya-prakash-susarla/OnScreenClock"

  app "FloatingClock.app"

  zap trash: [
    "~/.config/floating-clock",
    "~/Library/LaunchAgents/com.suryaprakash.floatingclock.plist",
  ]
end
