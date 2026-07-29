# Debug/Fix Integration Tests

## Overview

PAS integration tests run in the `MarioServiceTests` package against live gamma/prod endpoints. They validate ad responses using configurable validators. When they fail, it's either a real PAS bug or a flaky test due to demand/creative rotation.

## Quick Triage

1. **Check if pipeline is actually blocked** — the ticket may be a false positive
2. **Replay the request locally** — use the PAS V2 API call skill (`shared_skill/pas_v2_api_call.md`)
3. **Determine if transient** — run multiple times to see if it's creative-rotation-dependent

## Test Structure

```
MarioServiceTests/
├── src/com/amazon/marioservice/
│   ├── AlexaHomeScreenDisplayIntegrationTests.java
│   ├── TwitchIntegrationTest.java
│   ├── PrimeVideoVODIntegrationTests.java
│   └── validation/responsevalidator/
│       └── adresponse/
│           ├── NativeResponseValidator.java
│           ├── AuctionsValidator.java
│           ├── AAXRequestValidator.java
│           └── CatsResponseValidator.java
└── tst-resources/cats/{publisher}/{program}/{region}/
    └── test_*_config.json   ← request + expected validators
```

## Test Config Format

Each `test_*_config.json` contains:
- `requestEnvelope` — the PAS request to send
- `responseValidators` — list of validator class names to run against the response
- `aaxRtbRequest` — expected AAX request (for AAXRequestValidator)
- `publisherName`, `programType`, `testName` — metadata

## Replay a Test Locally

```python
import json, urllib.request, ssl

# Load test config
with open('tst-resources/cats/{publisher}/{program}/{region}/test_config.json') as f:
    config = json.load(f)

# Call PAS (see pas_v2_api_call.md for details)
req_envelope = json.dumps(config['requestEnvelope'], separators=(',', ':'))
body = json.dumps({'payload': req_envelope})
url = 'https://api.{tenant}.{region}.gamma.mario.imdbtv.amazon.dev/1.0.0/ads'

req = urllib.request.Request(url, data=body.encode('utf-8'), method='POST')
req.add_header('Content-Type', 'application/json')
ctx = ssl.create_default_context()
resp = urllib.request.urlopen(req, timeout=15, context=ctx)
response = json.loads(resp.read().decode('utf-8'))

# Inspect response
items = response.get('response', {}).get('item', [])
for i, item in enumerate(items):
    ad = item.get('media', {}).get('ad', {})
    print(f'Item {i}: has_ad={bool(ad)}')
```

## Run Multiple Times to Detect Flakiness

```python
for attempt in range(20):
    # ... make request ...
    # Categorize: no_ad, has_native, has_video, etc.
    print(f'{attempt}: {result}')
```

If results vary across runs → **flaky test** (demand/creative rotation dependent).

## Common Failure Patterns

### 1. Creative-rotation flakiness
- **Symptom**: Test passes sometimes, fails other times
- **Cause**: ADSP returns different creatives each time; test asserts on specific creative structure
- **Fix**: Make validator tolerant of creative variation (skip when expected structure absent)

### 2. No-fill during low-traffic hours
- **Symptom**: Test fails with empty response during off-peak
- **Cause**: ADSP has no demand for the test's geo/device/time combination
- **Fix**: Usually transient; retry or adjust test to use high-demand geo

### 3. Validator too strict
- **Symptom**: Consistent failure on specific assertion
- **Cause**: Validator hardcodes counts or structures that vary legitimately
- **Fix**: Relax assertion (e.g., `assertFalse(isEmpty)` instead of `assertEquals(3, count)`)

### 4. Config/deployment change
- **Symptom**: Test started failing after a specific deployment
- **Cause**: Code change affected response format or behavior
- **Fix**: Investigate the deployment; may need to update test expectations

## Fixing a Validator

1. Read the validator source in `MarioServiceTests/src/.../validation/responsevalidator/`
2. Understand what it asserts
3. Replay the request to see what the actual response looks like
4. Determine if the assertion is too strict or if there's a real bug
5. If flaky: relax the assertion with a comment explaining why (include replay evidence)

## Key Validators

| Validator | What it checks |
|-----------|---------------|
| NativeResponseValidator | Native ad assets (images, assetspecs, alttext) |
| AuctionsValidator | Auction ran correctly, winner selected |
| AAXRequestValidator | AAX request matches expected format |
| AAXResponseValidator | AAX response parsed correctly |
| CatsResponseValidator | CATS response envelope structure |
| InventoryPluginValidator | Inventory plugin executed |

## Pipeline Context

- **Pipeline**: `MarioService-awsappconfig` or `MarioService-cellular`
- **Stage**: Gamma workflows run integration tests after deployment
- **Retry**: Tests have `retryAnalyzer = RetryAnalyzer.class` — they auto-retry once
- **Timeout**: 30 seconds per test (`timeOut = TIMEOUT_IN_MILLISECONDS`)

## When to Close as Transient

- Pipeline approval workflow is NOT blocked
- Ticket says "IF THE APPROVAL WORKFLOW STEP HAS NOT FAILED... PLEASE REACH OUT TO THE INDEX ONCALL"
- Multiple replays show the test passes most of the time
- No recent code changes that could cause the failure

## ⚠️ Never Modify the Test Request

Do NOT change the `requestEnvelope` in test configs to "fix" a failing test. The request represents a real client call — modifying it changes the nature of what's being tested. The only exception is confirmed schema changes where the old request format is no longer valid.

If the test fails, fix the **validator logic** or **service code** — not the request.

## Automated Fix with Kiro CLI

For service-side bugs that manifest as integration test failures (e.g., `NoClassDefFoundError`, class initialization failures, dependency issues), use:

```bash
kiro-cli chat --model=claude-opus-4.6 --trust-tools=@builder-mcp/ReadRemoteTestRun,@builder-mcp/InternalCodeSearch,@builder-mcp/ReadInternalWebsites,subagent "@fix-integration-test <TEST_RUN_ID>"
```

**What it does**: Systematically investigates the test failure through 9 phases — extracts metadata, analyzes logs/stacktraces, reads source code at exact commits, identifies root cause, implements fix, and raises a CR.

**Best for**:
- Service-side bugs causing plugin failures (like `DealsPlugInPublisherMappingUtil` NoClassDefFoundError)
- Class initialization failures due to environment config (empty TENANT, missing env vars)
- Dependency/classpath issues in PubtechDealsResolver or other transitive deps

**Not ideal for**:
- No-demand/no-fill failures (creative rotation, low traffic) — those need manual replay
- Flaky tests that pass on retry — those are transient

**Example** (from P444905995):
```bash
kiro-cli chat --model=claude-opus-4.6 --trust-tools=@builder-mcp/ReadRemoteTestRun,@builder-mcp/InternalCodeSearch,@builder-mcp/ReadInternalWebsites,subagent "@fix-integration-test 850223472938-9da53ecb08869853bb0868a97d2af029-1389f73f-PQPkQeUHdC-1780371853"
```
This identified the `Exception` vs `Throwable` gap in `safeResolveTenantSupplyIdentities()` and raised CR-278974757.
