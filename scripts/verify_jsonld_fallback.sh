#!/usr/bin/env bash
# Quick verification script for JSON-LD fallback implementation
# 用法: ./scripts/verify_jsonld_fallback.sh

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

echo "=========================================="
echo "JSON-LD Fallback Layer Verification"
echo "=========================================="
echo ""

# 1. Check syntax
echo "✓ Checking Python syntax..."
python3 -m py_compile common/instagram_extract.py
echo "  ✅ No syntax errors"
echo ""

# 2. Run unit tests
echo "✓ Running unit tests..."
source .venv/bin/activate 2>/dev/null || true
python3 scripts/test_jsonld_unit.py
echo ""

# 3. Check integration
echo "✓ Checking configuration..."
grep -q "IG_ENABLE_JSONLD_FALLBACK" common/instagram_extract.py && echo "  ✅ JSON-LD switch found" || echo "  ❌ Warning: JSON-LD switch not found"
grep -q "IG_JSONLD_TIMEOUT_SEC" common/instagram_extract.py && echo "  ✅ Timeout config found" || echo "  ❌ Warning: Timeout config not found"
grep -q "_run_jsonld" common/instagram_extract.py && echo "  ✅ JSON-LD function defined" || echo "  ❌ Warning: JSON-LD function not found"
echo ""

# 4. List related files
echo "✓ Related files:"
echo "  - Implementation: common/instagram_extract.py"
echo "  - Unit tests: scripts/test_jsonld_unit.py"
echo "  - Smoke test: scripts/test_jsonld_fallback.py"
echo "  - Documentation: truth-source/2026-03-17-jsonld-fallback-implementation.md"
echo "  - Analysis: memory/lightpanda-decision-analysis-2026-03-17.md"
echo ""

# 5. Environment variables
echo "✓ Environment variables (add to .env if needed):"
echo "  IG_ENABLE_JSONLD_FALLBACK=1        # Enable JSON-LD fallback (default: 1)"
echo "  IG_JSONLD_TIMEOUT_SEC=15           # JSON-LD timeout in seconds (default: 15)"
echo ""

echo "=========================================="
echo "✅ Verification complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Monitor IG extraction metrics (next 7 days):"
echo "    ./scripts/health_check.py"
echo ""
echo "2. Review extraction logs:"
echo "    tail -f memory/ig-extract-cache.json"
echo ""
echo "3. Re-evaluate effectiveness (2026-03-24):"
echo "    - If media_count completeness >= 85%: Continue monitoring"
echo "    - If < 85%: Consider Lightpanda (P3 upgrade)"
echo ""
