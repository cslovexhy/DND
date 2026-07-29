#!/bin/bash
# download_crs.sh — Download all CR JSON files for a reviewer within a date range.
#
# Usage: bash download_crs.sh <reviewer_alias> [start_date] [end_date]
#   reviewer_alias: The Amazon login of the reviewer (e.g., schenam)
#   start_date: Optional, ISO date like 2026-03-27 (defaults to 4 months ago)
#   end_date: Optional, ISO date like 2026-07-27 (defaults to today)
#
# Output: /tmp/cr_data/<CR-ID>.json for each CR

set -euo pipefail

ALIAS="${1:?Usage: $0 <reviewer_alias> [start_date] [end_date]}"
START_DATE="${2:-$(date -v-4m +%Y-%m-%d 2>/dev/null || date -d '4 months ago' +%Y-%m-%d)}"
END_DATE="${3:-$(date +%Y-%m-%d)}"
OUTPUT_DIR="/tmp/cr_data"
COOKIE="$HOME/.midway/cookie"

mkdir -p "$OUTPUT_DIR"

echo "=== CR Comment Tracker: Download Phase ==="
echo "Reviewer: $ALIAS"
echo "Date range: $START_DATE to $END_DATE"
echo "Output dir: $OUTPUT_DIR"
echo ""

# Step 1: Get CR list (shipped + open + pending)
echo "Fetching CR list from code.amazon.com..."
CR_LIST_HTML=$(curl -s -L --negotiate -u : -b "$COOKIE" -c "$COOKIE" \
    "https://code.amazon.com/reviews/to-user/${ALIAS}?shipped=true&open=true&pending=true&start_time=${START_DATE}&end_time=${END_DATE}")

# Extract CR IDs from the HTML/markdown response
CR_IDS=($(echo "$CR_LIST_HTML" | grep -oE 'CR-[0-9]+' | sort -u))

if [ ${#CR_IDS[@]} -eq 0 ]; then
    echo "ERROR: No CR IDs found. Check your midway session (mwinit) and alias."
    exit 1
fi

TOTAL=${#CR_IDS[@]}
echo "Found $TOTAL unique CRs."
echo ""

# Step 2: Download each CR's JSON with comments
DONE=0
SKIPPED=0
FAILED=0

for CR in "${CR_IDS[@]}"; do
    FILE="${OUTPUT_DIR}/${CR}.json"
    
    # Skip if already downloaded and non-empty
    if [ -f "$FILE" ] && [ -s "$FILE" ]; then
        SKIPPED=$((SKIPPED + 1))
        DONE=$((DONE + 1))
        continue
    fi
    
    HTTP_CODE=$(curl -s -L --negotiate -u : -b "$COOKIE" -c "$COOKIE" \
        "https://code.amazon.com/reviews/${CR}?include-all-comments=true" \
        -H "Accept: application/json" \
        -o "$FILE" -w "%{http_code}" 2>/dev/null)
    
    DONE=$((DONE + 1))
    
    if [ "$HTTP_CODE" != "200" ] || [ ! -s "$FILE" ]; then
        FAILED=$((FAILED + 1))
        rm -f "$FILE"
        echo "[${DONE}/${TOTAL}] FAILED ${CR} (HTTP $HTTP_CODE)"
    else
        echo "[${DONE}/${TOTAL}] Downloaded ${CR}"
    fi
    
    sleep 0.15
done

echo ""
echo "=== Download Complete ==="
echo "Total CRs: $TOTAL"
echo "Downloaded: $((DONE - SKIPPED - FAILED))"
echo "Skipped (already exists): $SKIPPED"
echo "Failed: $FAILED"
echo ""
echo "Next step: python3 $(dirname "$0")/analyze_cr_comments.py $ALIAS"
