#!/bin/bash
# Script to check fragmentation progress
# Works both from host and inside container

# Detect if running inside container
if [ -f /.dockerenv ] || [ -n "$DOCKER_CONTAINER" ]; then
    # Running inside container - use direct paths
    FRAGMENT_DIR="/app/data/16tgk"
    DOCKER_CMD=""
else
    # Running from host - use docker compose
    FRAGMENT_DIR="/app/data/16tgk"
    DOCKER_CMD="docker compose exec app"
fi

echo "=== Fragmentation Progress ==="
echo ""

# Count fragments
if [ -n "$DOCKER_CMD" ]; then
    FRAGMENT_COUNT=$($DOCKER_CMD find $FRAGMENT_DIR -name "*.geojson" 2>/dev/null | wc -l)
    TOTAL_SIZE=$($DOCKER_CMD du -sh $FRAGMENT_DIR 2>/dev/null | awk '{print $1}')
    LAST_FRAGMENTS=$($DOCKER_CMD ls -lth $FRAGMENT_DIR/*.geojson 2>/dev/null | head -4 | tail -3)
    BY_ROW=$($DOCKER_CMD bash -c "cd $FRAGMENT_DIR && ls -1 *.geojson 2>/dev/null | sed 's/.*fragment_//' | sed 's/_.*//' | sort -n | uniq -c | awk '{print \"  Row \" \$2 \": \" \$1 \" fragments\"}'")
    IS_RUNNING=$($DOCKER_CMD ps aux | grep -q "[f]ragment_tile" && echo "yes" || echo "no")
else
    FRAGMENT_COUNT=$(find $FRAGMENT_DIR -name "*.geojson" 2>/dev/null | wc -l)
    TOTAL_SIZE=$(du -sh $FRAGMENT_DIR 2>/dev/null | awk '{print $1}')
    LAST_FRAGMENTS=$(ls -lth $FRAGMENT_DIR/*.geojson 2>/dev/null | head -4 | tail -3)
    BY_ROW=$(cd $FRAGMENT_DIR && ls -1 *.geojson 2>/dev/null | sed 's/.*fragment_//' | sed 's/_.*//' | sort -n | uniq -c | awk '{print "  Row " $2 ": " $1 " fragments"}')
    IS_RUNNING=$(ps aux | grep -q "[f]ragment_tile" && echo "yes" || echo "no")
fi

EXPECTED_FRAGMENTS=64  # 8x8 grid

# Calculate progress percentage using awk (more portable than bc)
PROGRESS_PCT=$(awk "BEGIN {printf \"%.1f\", ($FRAGMENT_COUNT * 100) / $EXPECTED_FRAGMENTS}" 2>/dev/null || echo "0.0")

echo "📊 Fragments created: $FRAGMENT_COUNT / $EXPECTED_FRAGMENTS"
echo "📈 Progress: ${PROGRESS_PCT}%"
echo ""

if [ -n "$TOTAL_SIZE" ]; then
    echo "💾 Total size: $TOTAL_SIZE"
else
    echo "💾 Total size: (calculating...)"
fi
echo ""

if [ -n "$BY_ROW" ]; then
    echo "📋 Fragments by row:"
    echo "$BY_ROW"
    echo ""
fi

if [ -n "$LAST_FRAGMENTS" ]; then
    echo "🕒 Last 3 fragments created:"
    echo "$LAST_FRAGMENTS" | awk '{split($9, a, "/"); print "  " a[length(a)] " - " $5 " - " $6 " " $7 " " $8}'
    echo ""
fi

# Check if process is running
if [ "$IS_RUNNING" = "yes" ]; then
    echo "✅ Process running"
    echo ""
    echo "💡 Run this command again to see updated progress"
else
    echo "❌ Process not running"
    if [ "$FRAGMENT_COUNT" -eq "$EXPECTED_FRAGMENTS" ]; then
        echo "✅ Fragmentation completed!"
    else
        echo "⚠️  Fragmentation incomplete. An error may have occurred."
    fi
fi
