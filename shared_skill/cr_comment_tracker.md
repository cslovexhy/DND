# CR Comment Tracker

Analyze unresponded code review comments left by a specific reviewer across all their reviewed CRs in a given time window.

## Prerequisites

- Active Midway session (`mwinit` if expired)
- `curl`, `python3`, `jq` on PATH

## Usage

```bash
# 1. Download all CR JSON files for a reviewer
bash ~/workplace/AIScripts/src/PubTechPASAdResponseAIScripts/shared_skill/scripts/download_crs.sh <reviewer_alias> <start_date> <end_date>

# 2. Analyze downloaded CRs for unresponded comments
python3 ~/workplace/AIScripts/src/PubTechPASAdResponseAIScripts/shared_skill/scripts/analyze_cr_comments.py <reviewer_alias>
```

### Example

```bash
# Download CRs where schenam was a reviewer in the past 4 months
bash ~/workplace/AIScripts/src/PubTechPASAdResponseAIScripts/shared_skill/scripts/download_crs.sh schenam 2026-03-27 2026-07-27

# Analyze for unresponded comments
python3 ~/workplace/AIScripts/src/PubTechPASAdResponseAIScripts/shared_skill/scripts/analyze_cr_comments.py schenam
```

## How It Works

1. **download_crs.sh** — Fetches the reviewer's CR list from `code.amazon.com/reviews/to-user/<alias>`, extracts CR IDs, then downloads each CR's full JSON (with comments) to `/tmp/cr_data/<CR-ID>.json`. Skips files that already exist and are non-empty.

2. **analyze_cr_comments.py** — Parses all downloaded JSON files, finds comments authored by the target alias, determines if each comment received a reply (non-bot, non-self), and reports unresponded comments grouped by CR owner.

## Output

The analyzer outputs:
- Total comments found
- Total unresponded (no reply, not marked as fixed)
- Grouped breakdown by CR owner with CR links and comment previews

## Why curl Instead of Built-in Tools

The `ReadInternalWebsites` MCP tool returns the **full CR JSON into the conversation context** — each CR response includes analyzer output, GK violations, Coverlay reports, full diffs, and hundreds of lines of bot comments. Processing just 10 CRs this way consumed 41% of the entire context window, making it impossible to analyze all 150+ CRs in a single session.

### Why MCP tool I/O kills context so fast

Every MCP tool call's output is inserted as a message in the conversation history. The model must carry all prior messages forward on every turn — there is no way to discard them. A single CR JSON response is 50-200KB (~40-50K tokens) because it includes:
- Full diffs of every file changed
- Every analyzer's verbose report (GK lists 30+ dependency violations with URLs)
- Coverlay coverage tables and Dry Run Build logs
- CR Description Generator's multi-paragraph summaries
- All bot comments (AutoSDE, GK-CRUX-Analyzer, etc.)

5 CR fetches via MCP = ~200K tokens permanently in context. That's why 10 CRs hit 41%.

### Why shell + curl avoids this

When the `shell` tool runs `curl -o /tmp/file.json`, the JSON goes to **disk**, not into the conversation. The only text returned to context is whatever prints to stdout — a single line like `[5/231] Downloaded CR-290577402`. A few hundred bytes vs 150KB per CR.

Similarly, the Python analysis script reads from disk and only prints the final summary table. Raw data never enters the conversation.

### Result

| Approach | 231 CRs | Context cost |
|----------|---------|-------------|
| MCP ReadInternalWebsites | Impossible (blows context at ~10) | ~40-50K tokens per CR |
| curl → disk + Python | 35 seconds total | ~2K tokens total (progress + results) |

Using `curl` directly with Midway auth (`~/.midway/cookie`) we:
- Download to **disk**, not into conversation context — zero token cost
- Bulk download all 231 CRs in ~35 seconds
- Save each CR as a separate file so re-runs skip already-fetched files
- Process everything locally with a Python script — no token/context limits
- Run the analysis repeatedly with different filters without re-downloading

CRUX has no bulk "get all comments by user" API — comments live on individual CR endpoints, so we must fetch each CR individually regardless of method.

## Notes

- Requires active Midway session — run `mwinit` if cookies are expired
- Bot authors are excluded from reply detection: `AutoSDE`, `CoverlayWorker`, `GK-CRUX-Analyzer`, `MergeService`, `ChangeGuardianCodeAnalyzer`, `CodeApprovers`
- Comments marked as `"fixed": true` by the CR owner are considered addressed
- The `parent` field in CRUX comments indicates a reply to a specific `post` number at the same location
- Rate limiting: 150ms sleep between downloads to avoid hammering code.amazon.com
- Re-running download is safe — it skips already-downloaded files
