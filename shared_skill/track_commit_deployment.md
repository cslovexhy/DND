# Track Commit Deployment Status

## When to Use

When checking whether a specific CR/commit has been fully deployed to production cells in a pipeline.

## How to Check

### Step 1: Get the commit SHA from the CR

From a CR page (e.g., `https://code.amazon.com/reviews/CR-XXXXXXXX`), find the commit SHA in the merge DAG section.

### Step 2: Open Track Changes in the pipeline

Construct and open this URL:

```
https://pipelines.amazon.com/pipelines/{PIPELINE_NAME}/change_history_v2?changes=GitFarmCommit:{PACKAGE_NAME}/mainline:{COMMIT_SHA}
```

**Example:**
```
https://pipelines.amazon.com/pipelines/MarioService-cellular/change_history_v2?changes=GitFarmCommit:MarioCommonTypes/mainline:53d6aa3db67742330de335e7f411f38197842f46
```

This shows a grid of exactly which pipeline stages the commit has reached.

### Step 3: Interpret the results

The Track Changes view shows columns for each pipeline stage group:
- VersionSet → PipelineUpdate → Packaging → GlobalTargets → Alpha → Gamma-onebox → Gamma → Prod-wave1-onebox → Prod-wave1 → Prod-wave2-onebox → Prod-wave2 → Prod-wave3-onebox → Prod-wave3 → Prod-wave4-onebox → Prod-wave4

Each cell shows whether the commit has been deployed to that stage.

## ⚠️ Do NOT Use GetPipelineDetails for This

`GetPipelineDetails` shows the **current pipeline state** — what's blocked or queued *right now*. It tells you about the *latest* revision being promoted, NOT where a specific older commit has already landed.

A commit merged days ago has likely already deployed through most stages. The blocked promotions you see in `GetPipelineDetails` are for **newer changes**, not the commit you're checking.

**Wrong approach:**
- Using `GetPipelineDetails` and inferring "these cells are blocked" → misleading for older commits

**Correct approach:**
- Use the Track Changes URL above to see actual per-stage deployment history for a specific commit

## Limitation

The Track Changes page relies on JavaScript to render the deployment grid. When fetched via `ReadInternalWebsites`, the status data may not render. In that case, provide the user with the Track Changes URL directly rather than guessing from `GetPipelineDetails`.

## Common Pipelines

| Pipeline | Package | Use Case |
|----------|---------|----------|
| MarioService-cellular | MarioCommonTypes, MarioService, ACCCoreLibrary | Main PAS service |
| PublisherAdServer | MarioServiceCDK | Multi-tenant CDK infra |
