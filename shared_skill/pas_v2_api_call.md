# PAS V2 API Call

## Endpoint Format

```
POST https://api.{tenant}.{region}.{stage}.mario.imdbtv.amazon.dev/1.0.0/ads
```

**Examples**:
- Gamma DUB Alexa: `https://api.alexa.eu-west-1.gamma.mario.imdbtv.amazon.dev/1.0.0/ads`
- Gamma IAD PVC: `https://api.pvc.us-east-1.gamma.mario.imdbtv.amazon.dev/1.0.0/ads`
- Prod IAD PVC: `https://api.pvc.us-east-1.prod.mario.imdbtv.amazon.dev/1.0.0/ads`
- Gamma DUB ITV: `https://api.itv.eu-west-1.gamma.mario.imdbtv.amazon.dev/1.0.0/ads`
- Gamma PDX Twitch: `https://api.twitch.us-west-2.gamma.mario.imdbtv.amazon.dev/1.0.0/ads`

**Tenant names**: pvc, itv, twitch, firetv, alexa, imdb, minitv, goodreads, shared, stores, ask, aecs, 3pstvapps
**Regions**: us-east-1, us-west-2, eu-west-1, ap-northeast-1, eu-south-2
**Stages**: gamma, prod

## Request Format

```
POST /1.0.0/ads
Content-Type: application/json

{"payload": "<stringified requestEnvelope JSON>"}
```

The `payload` field is a **JSON string** (double-encoded). The inner JSON is the CATS `RequestEnvelope` object.

### Building the request body

```python
import json

# request_envelope is a dict (the CATS RequestEnvelope)
payload_str = json.dumps(request_envelope, separators=(',', ':'))
body = json.dumps({"payload": payload_str})
```

### Where to find test request envelopes

Integration test configs in `MarioServiceTests`:
```
tst-resources/cats/{publisher}/{program}/{region}/test_*.json
```
The `requestEnvelope` field in these JSON files is the request to send.

## Response Format

The response is a **direct JSON object** (NOT wrapped in `{"payload": ...}`):

```json
{
  "dataspec": {"model": "adcom", "ver": "1.0"},
  "response": {
    "item": [...],
    "ext": {
      "debugOutput": "..."
    }
  },
  "ver": "1.0.0"
}
```

- `response.item[]` — array of response items, one per request item
- `response.item[].media.ad` — the ad object (if an ad was returned)
- `response.ext.debugOutput` — JSON string with debug info (only when `request.debug: true`)

## Python Example (full)

```python
import json, urllib.request, ssl

# Load test config
with open('path/to/test_config.json') as f:
    config = json.load(f)

# Build request
req_envelope = json.dumps(config['requestEnvelope'], separators=(',', ':'))
body = json.dumps({'payload': req_envelope})

# Call PAS
url = 'https://api.alexa.eu-west-1.gamma.mario.imdbtv.amazon.dev/1.0.0/ads'
req = urllib.request.Request(url, data=body.encode('utf-8'), method='POST')
req.add_header('Content-Type', 'application/json')

ctx = ssl.create_default_context()
resp = urllib.request.urlopen(req, timeout=15, context=ctx)
response = json.loads(resp.read().decode('utf-8'))

# Parse response
items = response.get('response', {}).get('item', [])
for item in items:
    ad = item.get('media', {}).get('ad', {})
    # ... inspect ad
```

## curl Example

```bash
# Build payload (stringify the request envelope)
jq -c '.' request_envelope.json | jq -Rs '{payload: .}' > /tmp/pas_req.json

# Call PAS
curl -s -X POST \
  "https://api.alexa.eu-west-1.gamma.mario.imdbtv.amazon.dev/1.0.0/ads" \
  -H "Content-Type: application/json" \
  -d @/tmp/pas_req.json | jq .
```

## Notes

- No authentication required for gamma endpoints (internal network only)
- No gzip required for simple replay calls (the integration test framework uses gzip for performance, but plain JSON works)
- Set `"debug": true` in the request to get `debugOutput` in the response (includes AAX request/response, combined log, etc.)
- Set `"test": 1` in the request to mark as test traffic (won't count in metrics)
- Response is NOT gzipped when called without `Accept-Encoding: gzip`
- The `/GetAdsV2` path is the Coral RPC endpoint (requires gzip + Coral wrapping) — use `/1.0.0/ads` for REST-style calls

## Common Response Structures

### VOD/Linear (video ads)
```
response.item[].media.ad.display.adm  → VMAP/VAST XML string
```

### Display (native ads, e.g., Alexa)
```
response.item[].media.ad.display.native.asset[]  → array of native assets
  .image  → image asset (type=1: icon, type=3: main image)
  .title  → title asset
  .data   → data asset
  .video  → video asset
```

### No-fill
```
response.item[].media  → null or empty (no ad returned for this slot)
```
