# Replay PVC VOD Request from Athena

End-to-end skill for fetching a real PVC VOD request from Athena logs and replaying it against PAS v2 to verify ad fill.

## Overview

1. Authenticate to the PVC IAD AWS account
2. Query Athena for a combined log containing a PVC VOD request
3. Parse the request body from the combined log
4. Add required fields (IP address) stripped during logging
5. Wrap in a RequestEnvelope and call PAS v2
6. Verify whether ads are returned

---

## Step 1: Authenticate to IAD_PVC

Reference `aws_auth.md` for full account table. IAD_PVC is a **non-live** cell.

```bash
ada credentials update --account=879302171300 --provider=conduit --role=ConduitLimitedAccessRole --once
```

This writes short-lived credentials to the `default` AWS profile.

---

## Step 2: Query Athena for a PVC VOD Combined Log

### Database and Table

- **Database**: `mario_application_logs_database`
- **Table**: `mario_application_logs`
- **Columns**: `date` (string), `log` (string)
- **Partition keys**: `stream`, `year`, `month`, `day`, `hour`
- **Workgroup**: `primary`

### Query

```sql
SELECT log
FROM mario_application_logs_database.mario_application_logs
WHERE log LIKE '%COMBINED%'
AND log LIKE '%"programid":"VOD"%'
AND year = '2026'
AND month = '06'
AND day = '04'
AND hour in ('16')
LIMIT 1
```

**Key filters**:
- `%COMBINED%` — matches `_COMBINED_LOG_V2_` entries which contain the full request+response
- `%"programid":"VOD"%` — filters for VOD program (as opposed to DISPLAY, LINEAR, etc.)

**Adjust `year`, `month`, `day`, `hour`** to recent values. Use UTC hour. Narrower partitions = faster queries (<10s for a single hour).

### Execution via AWS CLI

```bash
# Start query
QUERY_ID=$(aws athena start-query-execution \
  --query-string "SELECT log FROM mario_application_logs_database.mario_application_logs WHERE log LIKE '%COMBINED%' AND log LIKE '%\"programid\":\"VOD\"%' AND year = '2026' AND month = '06' AND day = '04' AND hour in ('16') LIMIT 1" \
  --work-group primary \
  --region us-east-1 \
  --query 'QueryExecutionId' --output text)

# Poll until SUCCEEDED (typically 5-20s)
aws athena get-query-execution --query-execution-id $QUERY_ID --region us-east-1 --query 'QueryExecution.Status.State' --output text

# Get results
aws athena get-query-results --query-execution-id $QUERY_ID --region us-east-1 --query 'ResultSet.Rows[1].Data[0].VarCharValue' --output text
```

### Alternative: Download CSV from Athena Console

Query results are also saved to S3 as CSV files. If you already have a downloaded CSV (e.g., from the Athena console), you can read it directly. The CSV has a `log` column header and one row of data.

### Filtering for Other Programs

| Program | Filter |
|---------|--------|
| VOD | `log LIKE '%"programid":"VOD"%'` |
| DISPLAY | `log LIKE '%"programid":"DISPLAY"%'` |
| LINEAR | `log LIKE '%"programid":"LINEAR"%'` |

### Filtering for Other Publishers (same account)

The IAD_PVC account only serves PVC traffic. For other publishers, authenticate to the appropriate account (see `aws_auth.md`).

---

## Step 3: Parse the Request Body from the Combined Log

The combined log line has this structure:
```
<timestamp> [INFO] <requestId> [XRAY_TRACE=...] [PARTNER_NAME=PVC] [PROGRAM_NAME=VOD] ... [_COMBINED_LOG_V2_] {JSON}
```

The JSON blob starts at `{"requestId":"...` and contains:
- `requestId` — the PAS request ID
- `requestDetails` — **this is the PAS request body** (the inner `request` object for the RequestEnvelope)
- `publisherEnrichmentDetails` — enrichment context
- `returnedAds` — what ads were served
- Various execution context fields

### Extraction (Python)

```python
import json, csv

# From Athena CLI output (text)
log_line = "<the log text>"

# Or from downloaded CSV
with open('path/to/result.csv', 'r') as f:
    reader = csv.reader(f)
    next(reader)  # skip header
    log_line = next(reader)[0]

# Extract JSON - find the start of the JSON object
start = log_line.index('{"requestId"')
combined_log = json.loads(log_line[start:])

# The request body
request_details = combined_log['requestDetails']
```

### Key Fields in `requestDetails`

```json
{
  "context": {
    "app": {
      "pub": {"ext": {"programid": "VOD"}, "id": "pvc", "name": "PVC"},
      "content": {"id": "amzn1.dv.pvid...", "genre": "...", "len": 6187, ...}
    },
    "device": {"type": 3, "geo": {"country": "US"}, "ua": "...", "lmt": 0|1},
    "regs": {...},
    "user": {...}
  },
  "ext": {
    "pasRequestId": "...",
    "partnerProgramGeoC": "PVC-VOD-US"
  },
  "id": "...",
  "item": [{...}],  // ad slots requested
  "source": {"ts": ...},
  "test": 0,
  "debug": false
}
```

---

## Step 4: Add Required Fields

The combined log **strips the IP address** during logging. You must add it back for the request to pass validation.

```python
# Add a valid US IP address
request_details['context']['device']['ip'] = '72.21.198.66'
```

**IP by geo**:
| Country | Example IP |
|---------|-----------|
| US | `72.21.198.66` |
| GB | `185.86.151.11` |
| DE | `52.58.0.1` |
| JP | `52.68.0.1` |
| IN | `13.126.0.1` |

Use an IP matching the `device.geo.country` in the request.

### Optional: Set debug mode

```python
# Enable debug output in response (includes AAX request/response details)
request_details['debug'] = True
```

---

## Step 5: Wrap in RequestEnvelope and Call PAS v2

The `requestDetails` is the inner `request` field. It must be wrapped in a `RequestEnvelope`:

```python
import json

envelope = {
    'dataspec': {'model': 'adcom', 'ver': '1.0'},
    'request': request_details,
    'ver': '1.0.0'
}

# Double-encode as payload string
payload_str = json.dumps(envelope, separators=(',', ':'))
body = json.dumps({'payload': payload_str})

# Save for curl
with open('/tmp/pas_vod_req.json', 'w') as f:
    f.write(body)
```

### Call the endpoint

```bash
curl -s -X POST \
  "https://api.pvc.us-east-1.prod.mario.imdbtv.amazon.dev/1.0.0/ads" \
  -H "Content-Type: application/json" \
  -d @/tmp/pas_vod_req.json
```

### Endpoint mapping

| Cell | Endpoint |
|------|----------|
| IAD PVC Prod | `https://api.pvc.us-east-1.prod.mario.imdbtv.amazon.dev/1.0.0/ads` |
| PDX PVC Prod | `https://api.pvc.us-west-2.prod.mario.imdbtv.amazon.dev/1.0.0/ads` |
| DUB PVC Prod | `https://api.pvc.eu-west-1.prod.mario.imdbtv.amazon.dev/1.0.0/ads` |
| IAD PVC Gamma | `https://api.pvc.us-east-1.gamma.mario.imdbtv.amazon.dev/1.0.0/ads` |

No authentication is required — endpoints are accessible from the internal network.

---

## Step 6: Verify Ad Fill

### Python verification

```python
import json, urllib.request, ssl

# Call PAS
url = 'https://api.pvc.us-east-1.prod.mario.imdbtv.amazon.dev/1.0.0/ads'
req = urllib.request.Request(url, data=body.encode('utf-8'), method='POST')
req.add_header('Content-Type', 'application/json')

ctx = ssl.create_default_context()
resp = urllib.request.urlopen(req, timeout=15, context=ctx)
response = json.loads(resp.read().decode('utf-8'))

# Check for errors
if 'errorMessage' in response:
    print(f"ERROR: {response['errorMessage']}")
else:
    items = response.get('response', {}).get('item', [])
    print(f"Response items: {len(items)}")
    for i, item in enumerate(items):
        media = item.get('media')
        if media and media.get('ad'):
            ad = media['ad']
            # VOD ads have video.adm (VMAP XML)
            adm = ad.get('video', {}).get('adm', '') or ad.get('display', {}).get('adm', '')
            print(f"  Item {i}: AD RETURNED (adm length: {len(adm)})")
        else:
            print(f"  Item {i}: NO FILL")
```

### Expected response structure (VOD)

```json
{
  "dataspec": {"model": "adcom", "ver": "1.0"},
  "response": {
    "id": "<requestId>",
    "item": [
      {
        "id": "amzn1.adslot.<uuid>",
        "media": {
          "ad": {
            "id": "amzn1.adslot.<uuid>",
            "video": {
              "adm": "<vmap:VMAP ...>...</vmap:VMAP>"
            }
          }
        }
      }
    ]
  },
  "ver": "1.0.0"
}
```

The `video.adm` field contains VMAP XML with one or more `<vmap:AdBreak>` elements, each containing VAST `<Ad>` entries with video `<MediaFile>` URLs.

### Common error responses

| Error | Cause | Fix |
|-------|-------|-----|
| `Request cannot be null inside RequestEnvelope` | Missing `request` wrapper | Wrap `requestDetails` in envelope with `dataspec`, `request`, `ver` |
| `ip (ipAddress) in the request is not valid` | Missing/empty IP | Add `context.device.ip` with a valid IP |
| Empty items `[]` or no media | No ad fill | Normal — try different hour/content or check if `lmt=1` |

---

## Full End-to-End Script

```python
#!/usr/bin/env python3
"""Replay a PVC VOD request from Athena logs against PAS v2."""
import json, csv, subprocess, time, urllib.request, ssl, sys

# --- Config ---
ACCOUNT_ID = '879302171300'  # IAD_PVC
REGION = 'us-east-1'
YEAR, MONTH, DAY, HOUR = '2026', '06', '04', '16'  # Adjust to recent UTC time
IP_ADDRESS = '72.21.198.66'  # US IP
ENDPOINT = 'https://api.pvc.us-east-1.prod.mario.imdbtv.amazon.dev/1.0.0/ads'

# --- Step 1: Auth ---
print("[1/5] Authenticating...")
subprocess.run([
    'ada', 'credentials', 'update',
    f'--account={ACCOUNT_ID}', '--provider=conduit',
    '--role=ConduitLimitedAccessRole', '--once'
], check=True, capture_output=True)

# --- Step 2: Query Athena ---
print("[2/5] Querying Athena...")
query = f"""SELECT log FROM mario_application_logs_database.mario_application_logs
WHERE log LIKE '%COMBINED%' AND log LIKE '%"programid":"VOD"%'
AND year = '{YEAR}' AND month = '{MONTH}' AND day = '{DAY}' AND hour in ('{HOUR}')
LIMIT 1"""

result = subprocess.run([
    'aws', 'athena', 'start-query-execution',
    '--query-string', query,
    '--work-group', 'primary',
    '--region', REGION,
    '--query', 'QueryExecutionId', '--output', 'text'
], capture_output=True, text=True, check=True)
query_id = result.stdout.strip()

# Poll for completion
for _ in range(30):
    time.sleep(2)
    result = subprocess.run([
        'aws', 'athena', 'get-query-execution',
        '--query-execution-id', query_id,
        '--region', REGION,
        '--query', 'QueryExecution.Status.State', '--output', 'text'
    ], capture_output=True, text=True, check=True)
    state = result.stdout.strip()
    if state == 'SUCCEEDED':
        break
    elif state == 'FAILED':
        sys.exit("Athena query failed!")
else:
    sys.exit("Athena query timed out")

# Get results
result = subprocess.run([
    'aws', 'athena', 'get-query-results',
    '--query-execution-id', query_id,
    '--region', REGION,
    '--query', 'ResultSet.Rows[1].Data[0].VarCharValue', '--output', 'text'
], capture_output=True, text=True, check=True)
log_line = result.stdout

# --- Step 3: Parse request body ---
print("[3/5] Parsing request body...")
start = log_line.index('{"requestId"')
combined_log = json.loads(log_line[start:])
request_details = combined_log['requestDetails']
print(f"  Request ID: {request_details.get('ext', {}).get('pasRequestId')}")
print(f"  Program: {request_details['context']['app']['pub']['ext']['programid']}")
print(f"  Geo: {request_details.get('ext', {}).get('partnerProgramGeoC')}")

# --- Step 4: Add IP ---
print("[4/5] Adding IP address...")
request_details['context']['device']['ip'] = IP_ADDRESS

# --- Step 5: Call PAS v2 ---
print("[5/5] Calling PAS v2...")
envelope = {
    'dataspec': {'model': 'adcom', 'ver': '1.0'},
    'request': request_details,
    'ver': '1.0.0'
}
payload_str = json.dumps(envelope, separators=(',', ':'))
body = json.dumps({'payload': payload_str})

req = urllib.request.Request(ENDPOINT, data=body.encode('utf-8'), method='POST')
req.add_header('Content-Type', 'application/json')
ctx = ssl.create_default_context()
resp = urllib.request.urlopen(req, timeout=15, context=ctx)
response = json.loads(resp.read().decode('utf-8'))

# --- Results ---
if 'errorMessage' in response:
    print(f"\n❌ ERROR: {response['errorMessage']}")
    sys.exit(1)

items = response.get('response', {}).get('item', [])
filled = sum(1 for item in items if item.get('media', {}).get('ad'))
print(f"\n{'✅' if filled > 0 else '❌'} Result: {filled}/{len(items)} items filled")
for i, item in enumerate(items):
    media = item.get('media')
    if media and media.get('ad'):
        ad = media['ad']
        adm = ad.get('video', {}).get('adm', '') or ad.get('display', {}).get('adm', '')
        print(f"  Item {i}: AD RETURNED (adm length: {len(adm)})")
    else:
        print(f"  Item {i}: NO FILL")
```

---

## Notes

- **Athena costs**: Each query scans data. Narrowing by `hour` keeps scans small (~5-15 GB per hour partition).
- **No-fill is normal**: Not every request fills. VOD fill rates are high but not 100%. If you get no-fill, try a different hour or re-run (pacing/frequency capping can cause transient no-fill).
- **`lmt: 1`** (Limit Ad Tracking): Reduces fill since targeting is restricted. Flip to `0` if testing fill.
- **Prod vs Gamma**: Prod has real demand. Gamma may have limited/no demand inventory — prefer prod for fill testing.
- **Credential expiry**: `ada` credentials are short-lived. Re-run the auth command if Athena queries fail with auth errors.
- **Content rating**: R-rated or `NOT_FAMILY_FRIENDLY` content may have reduced demand from some advertisers.
