# HLD Breakdown: Document → Sections → Commits → CRs

## Overview

Read a design document (HLD, BRD, etc.), break it into logically separated markdown sections with diagrams under `Projects/`, create one commit per section, and create one CR per commit.

## Step 1: Read the Source Document

```
Read the Quip/SharePoint document URL provided by the user.
```

Also check the existing `Projects/` folder structure (e.g., `PrefetchRevamp/`) to match the established pattern: numbered folders, markdown files, diagrams directory.

## Step 2: Plan the Breakdown

Break the HLD into logical sections. Typical pattern:

```
Projects/<ProjectName>/
├── 00-RawSourceDocument/
│   └── README.md          # Index, metadata, key decisions, pre-reads
├── 01-Overview/
│   └── Overview.md        # Problem statement, requirements, scope, LOE
├── 02-<CoreDesign>/
│   └── <CoreDesign>.md    # Architecture, assumptions, principles
├── 03-<Component1>/
│   └── <Component1>.md    # Detailed component changes
├── 04-<Component2>/
│   └── <Component2>.md    # Detailed component changes
├── ...
├── NN-OperationalReadiness/
│   └── OperationalReadiness.md  # Metrics, risks, tech debt, open questions
└── diagrams/
    ├── README.md           # Diagram index
    └── *.md                # Mermaid diagrams per flow
```

**Rules:**
- Each section should be self-contained and reviewable independently
- Use numbered prefixes (`01-`, `02-`, ...) for ordering
- Diagrams go in a single `diagrams/` folder with Mermaid syntax
- Each markdown file starts with a header block: Source link, Scope, See-also references

## Step 3: Create the Files

Write all markdown files. Each section should include:
- Source reference (Quip link + section numbers)
- Tables for structured info (requirements, metrics, comparisons)
- Code blocks for models, configs, wire formats
- Cross-references to diagram files

For diagrams, use Mermaid syntax:
- `sequenceDiagram` for flows between components
- `flowchart TD` for decision logic
- `graph TB` for component ownership/architecture
- `gantt` for timelines

## Step 4: Commit One Section at a Time

```bash
# Commit each folder as a separate commit
git add Projects/<ProjectName>/00-RawSourceDocument/
git commit -m "Added raw document for <Project> HLD"

git add Projects/<ProjectName>/01-Overview/
git commit -m "Added overview for <Project> HLD"

git add Projects/<ProjectName>/02-<Section>/
git commit -m "Added <section description> for <Project> HLD"

# ... repeat for each section ...

git add Projects/<ProjectName>/diagrams/
git commit -m "Added Mermaid diagrams for <Project> HLD"
```

**Rules:**
- One logical section per commit
- Commit message format: `Added <section description> for <Project> HLD`
- Do NOT push commits — they stay local until CRs are created

## Step 5: Create One CR per Commit

```bash
# Get the list of new commits
git log --oneline <base_commit>..HEAD

# Create CRs in a loop
for commit in $(git rev-list --reverse <base_commit>..HEAD); do
  parent=$(git rev-parse "$commit^")
  cr --range "$parent:$commit"
done
```

Where `<base_commit>` is the last commit before your new work (i.e., the commit already on mainline or in a prior CR).

**Alternative (one at a time):**
```bash
cr --range <parent_sha>:<commit_sha>
```

**Notes:**
- `cr --range` does NOT push commits — only uploads a snapshot for review
- `cr --range` does NOT amend commits with CR link (cosmetic only, CR still tracks the SHA)
- If you want CR link in commit body, use `cr --parent HEAD^` immediately after each commit (only works for HEAD)

## Example: Full Workflow

```bash
# 1. Read document (done by AI)
# 2. AI creates files under Projects/<Name>/

# 3. Commit per section
git add Projects/MPP-NonEntitled-Supply/00-RawSourceDocument/
git commit -m "Added raw document for MPP Non Entitled supply HLD"

git add Projects/MPP-NonEntitled-Supply/01-Overview/
git commit -m "Added overview for MPP Non Entitled supply HLD"

# ... etc ...

# 4. Create CRs (find base commit first)
BASE=$(git log --oneline | grep -m1 "some known prior commit" | cut -d' ' -f1)

for commit in $(git rev-list --reverse $BASE..HEAD); do
  parent=$(git rev-parse "$commit^")
  cr --range "$parent:$commit"
done
```

## Tips

- Keep each section under ~200 lines for easy CR review
- Diagrams section can be larger since Mermaid is self-documenting
- Use the `00-RawSourceDocument/README.md` as the table of contents linking all sections
- For very large HLDs, consider splitting component changes by team ownership (request vs response)
