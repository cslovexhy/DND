#!/usr/bin/env python3
"""
analyze_cr_comments.py — Find unresponded CR comments for a given reviewer.

Usage: python3 analyze_cr_comments.py <reviewer_alias> [--data-dir /tmp/cr_data] [--json]

Reads all CR JSON files from the data directory (downloaded by download_crs.sh),
finds comments authored by the target alias, and reports which ones received no reply.

Output is grouped by CR owner, sorted by unresponded count descending.
"""

import argparse
import json
import os
import glob
from collections import defaultdict

# Bot/system authors to exclude from reply detection
BOT_AUTHORS = frozenset([
    "AutoSDE", "CoverlayWorker", "GK-CRUX-Analyzer", "MergeService",
    "ChangeGuardianCodeAnalyzer", "CodeApprovers", "CriticService",
])


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze CR comments for unresponded feedback")
    parser.add_argument("alias", help="The reviewer alias to analyze (e.g., schenam)")
    parser.add_argument("--data-dir", default="/tmp/cr_data",
                        help="Directory containing CR JSON files (default: /tmp/cr_data)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON instead of human-readable text")
    parser.add_argument("--include-fixed", action="store_true",
                        help="Include comments marked as fixed in the unresponded list")
    return parser.parse_args()


def extract_comments(cr_rev):
    """Extract a flat list of comment metadata from a cr_revision object."""
    comments = []
    for c in cr_rev.get("comments", []):
        cc = c.get("cr_comment", {})
        loc = cc.get("location", {}).get("comment_location", {})
        comments.append({
            "author": cc.get("author", {}).get("entity_id", {}).get("id", ""),
            "content": cc.get("content", ""),
            "location": loc.get("location", ""),
            "post": loc.get("post"),
            "parent": cc.get("parent"),
            "fixed": cc.get("fixed", False),
            "published": cc.get("published", True),
        })
    return comments


def has_human_reply(comment, all_comments):
    """Check if a comment received a reply from a non-bot, non-self author."""
    post_id = comment.get("post")
    if post_id is None:
        return False
    return any(
        c.get("parent") == post_id
        and c["author"] != comment["author"]
        and c["author"] not in BOT_AUTHORS
        for c in all_comments
    )


def analyze_cr(filepath, alias, include_fixed=False):
    """Analyze a single CR file. Returns (cr_author, status, unresponded_comments)."""
    with open(filepath) as f:
        data = json.load(f)

    cr_rev = data.get("revision", {}).get("cr_revision", {})
    status = cr_rev.get("status", "UNKNOWN")
    cr_author = cr_rev.get("author", {}).get("entity_id", {}).get("id", "unknown")

    all_comments = extract_comments(cr_rev)
    alias_comments = [c for c in all_comments if c["author"] == alias and c.get("published", True)]

    unresponded = []
    for comment in alias_comments:
        if not include_fixed and comment.get("fixed", False):
            continue
        if not has_human_reply(comment, all_comments):
            unresponded.append(comment["content"][:200].replace("\n", " ").strip())

    return {
        "cr_author": cr_author,
        "status": status,
        "total_comments": len(alias_comments),
        "unresponded": unresponded,
    }


def main():
    args = parse_args()
    alias = args.alias
    data_dir = args.data_dir

    files = sorted(glob.glob(os.path.join(data_dir, "CR-*.json")))
    if not files:
        print(f"ERROR: No CR files found in {data_dir}")
        print(f"Run download_crs.sh first: bash download_crs.sh {alias}")
        return

    # Process all files
    grouped = defaultdict(list)
    total_comments = 0
    total_unresponded = 0
    total_crs = 0
    errors = []

    for filepath in files:
        cr_id = os.path.basename(filepath).replace(".json", "")
        try:
            result = analyze_cr(filepath, alias, args.include_fixed)
            total_comments += result["total_comments"]
            total_unresponded += len(result["unresponded"])
            total_crs += 1

            if result["unresponded"]:
                grouped[result["cr_author"]].append({
                    "cr_id": cr_id,
                    "status": result["status"],
                    "comments": result["unresponded"],
                })
        except Exception as e:
            errors.append(f"{cr_id}: {str(e)[:80]}")

    # Output
    if args.json:
        output = {
            "alias": alias,
            "total_crs_analyzed": total_crs,
            "total_comments_by_alias": total_comments,
            "total_unresponded": total_unresponded,
            "unresponded_rate": f"{total_unresponded / total_comments * 100:.1f}%" if total_comments > 0 else "N/A",
            "by_cr_owner": {
                owner: {
                    "count": sum(len(item["comments"]) for item in items),
                    "crs": items,
                }
                for owner, items in sorted(grouped.items(), key=lambda x: -sum(len(i["comments"]) for i in x[1]))
            },
            "errors": errors,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"=== UNRESPONDED CR COMMENTS: {alias} ===")
        print(f"CRs analyzed: {total_crs}")
        print(f"Total comments by {alias}: {total_comments}")
        print(f"Unresponded: {total_unresponded} ({total_unresponded / total_comments * 100:.1f}%)" if total_comments > 0 else "Unresponded: 0")
        print(f"Grouped by {len(grouped)} CR owners\n")

        for owner, items in sorted(grouped.items(), key=lambda x: -sum(len(i["comments"]) for i in x[1])):
            count = sum(len(item["comments"]) for item in items)
            print(f"## {owner} — {count} unresponded")
            for item in items:
                print(f"  [{item['status']}] https://code.amazon.com/reviews/{item['cr_id']}")
                for comment in item["comments"]:
                    print(f"    \"{comment[:140]}\"")
            print()

        if errors:
            print(f"\n--- {len(errors)} errors ---")
            for e in errors[:10]:
                print(f"  {e}")


if __name__ == "__main__":
    main()
