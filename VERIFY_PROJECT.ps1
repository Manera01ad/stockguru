# STOCKGURU PROJECT VERIFICATION SCRIPT
# Run this in PowerShell at: c:\Users\Hp\projects\stockguru\

Write-Host "===================================" -ForegroundColor Cyan
Write-Host "STOCKGURU PROJECT AUDIT - 2026-03-25" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""

# Check if in correct directory
if (-not (Test-Path "app.py")) {
    Write-Host "❌ ERROR: app.py not found. Please run from: c:\Users\Hp\projects\stockguru\" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Found app.py - in correct directory" -ForegroundColor Green
Write-Host ""

# Phase 2.5 Files Check
Write-Host "📋 PHASE 2.5 FILES CHECK:" -ForegroundColor Yellow
Write-Host "==================================" -ForegroundColor Yellow

$phase25Files = @(
    "conviction_filter.py",
    "PHASE_2.5_QUICK_REFERENCE.md",
    "INTEGRATION_GUIDE_PHASE_2.5.md",
    "PHASE_2.5_SUMMARY.md",
    "PHASE_2.5_CONVICTION_HARDENING_REPORT.md",
    "PHASE_2.5_COMPLETION_VERIFICATION.md",
    "NEXT_STEPS_ACTION_PLAN.md",
    "PROGRESS_SUMMARY_2026_03_25.md",
    "00_START_HERE.md"
)

$foundCount = 0
foreach ($file in $phase25Files) {
    if (Test-Path $file) {
        Write-Host "✅ $file" -ForegroundColor Green
        $foundCount++
    } else {
        Write-Host "❌ MISSING: $file" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Files Found: $foundCount / $($phase25Files.Count)" -ForegroundColor Cyan
Write-Host ""

# Core Infrastructure Check
Write-Host "🔧 CORE INFRASTRUCTURE:" -ForegroundColor Yellow
Write-Host "==================================" -ForegroundColor Yellow

$coreFiles = @(
    @("app.py", "Flask server"),
    @("paper_trader.py", "Trading engine"),
    @("conviction_filter.py", "8-gate filter (Phase 2.5)")
)

$coreDirs = @(
    @("stockguru_agents", "Agent modules"),
    @("static", "Frontend UI"),
    @("data", "Data directory")
)

foreach ($item in $coreFiles) {
    if (Test-Path $item[0]) {
        Write-Host "✅ $($item[0]) - $($item[1])" -ForegroundColor Green
    } else {
        Write-Host "❌ MISSING: $($item[0]) - $($item[1])" -ForegroundColor Red
    }
}

foreach ($item in $coreDirs) {
    if (Test-Path $item[0]) {
        Write-Host "✅ $($item[0])/ - $($item[1])" -ForegroundColor Green
    } else {
        Write-Host "❌ MISSING: $($item[0])/ - $($item[1])" -ForegroundColor Red
    }
}

if (Test-Path "data\stockguru.db") {
    Write-Host "✅ data\stockguru.db (Database)" -ForegroundColor Green
}

Write-Host ""

# Git Status
Write-Host "🔄 GIT STATUS:" -ForegroundColor Yellow
Write-Host "==================================" -ForegroundColor Yellow

$gitStatus = git status --short
$changeCount = ($gitStatus | Measure-Object -Line).Lines

if ($changeCount -gt 0) {
    Write-Host "Uncommitted changes: $changeCount" -ForegroundColor Red
    Write-Host "First 10 changes:" -ForegroundColor Cyan
    $gitStatus | Select-Object -First 10 | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "✅ No uncommitted changes - all pushed to git!" -ForegroundColor Green
}

Write-Host ""

# Last Commit
Write-Host "📅 LAST COMMIT:" -ForegroundColor Yellow
Write-Host "==================================" -ForegroundColor Yellow
git log -1 --oneline
Write-Host ""

# Branches
Write-Host "🌿 GIT BRANCHES:" -ForegroundColor Yellow
Write-Host "==================================" -ForegroundColor Yellow
git branch -a
Write-Host ""

# Summary
Write-Host "📊 PHASE STATUS:" -ForegroundColor Yellow
Write-Host "==================================" -ForegroundColor Yellow

if ($foundCount -eq $phase25Files.Count) {
    Write-Host "✅ ALL PHASE 2.5 FILES PRESENT" -ForegroundColor Green
    Write-Host "Status: PHASE 2.5 COMPLETE" -ForegroundColor Green
} else {
    $missing = $phase25Files.Count - $foundCount
    Write-Host "⚠️  MISSING $missing PHASE 2.5 FILES" -ForegroundColor Yellow
    Write-Host "Status: PHASE 2.5 INCOMPLETE - FILES NEED TO BE COPIED" -ForegroundColor Yellow
}

Write-Host ""
if ($changeCount -eq 0) {
    Write-Host "✅ ALL CHANGES PUSHED TO GIT" -ForegroundColor Green
} else {
    Write-Host "⚠️  $changeCount changes NOT YET PUSHED TO GIT" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "✅ AUDIT COMPLETE" -ForegroundColor Cyan
Write-Host ""
