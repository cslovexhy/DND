# GAM Serverside Doubleclick VAST Tag Testing

## Overview

This skill documents how to fetch a live `serverside.doubleclick.net` VAST tag URI from PAS application logs, retrieve the GAM client certificate for mTLS authentication, and call the URL to get a VAST XML response.

The `serverside.doubleclick.net` endpoints require **mutual TLS (mTLS)** — a client certificate issued by Google DCM (DoubleClick Campaign Manager). Without the cert, the endpoint returns: `Authentication Error. No certificate found for the partner.`

---

## Step 1: Get a Recent serverside.doubleclick URL from Athena

### 1.1 Authenticate to the IAD_PVC Account

```bash
ada credentials update --account=879302171300 --provider=conduit --role=ConduitLimitedAccessRole --once
```

This is the **IAD_PVC** cell (us-east-1). For other cells, see `aws_auth.md` for account IDs.

### 1.2 Run the Athena Query

Use the `mario_application_logs_database.mario_application_logs` table in the `primary` workgroup.

**Critical query rules:**
- Always use `LIMIT 1` — these queries scan large datasets
- Always filter by `hour` to reduce scan cost (hours are in UTC)
- Don't wait more than ~10 seconds for results; if it hasn't finished, check back
- The `log` column contains the full JSON log entry as a string

**Query:**

```sql
SELECT log
FROM mario_application_logs_database.mario_application_logs
WHERE log LIKE '%serverside.doubleclick%'
  AND year = '2026'
  AND month = '06'
  AND day = '03'
  AND hour in ('14')
LIMIT 1
```

Adjust `year`, `month`, `day`, `hour` to the current date/time in UTC.

**Note:** You do NOT need to filter by `vastTagUri` — just `serverside.doubleclick` is sufficient to get a hit. Adding `vastTagUri` narrows too much and may cause the query to scan excessively before finding a match.

### 1.3 Extract the URL from Results

The log entry is a large JSON object. The `serverside.doubleclick.net` URLs appear as VAST tag URIs within the combined log. Extract them with:

```bash
aws athena get-query-results --query-execution-id <QUERY_ID> --region us-east-1 --output text | \
  sed 's/\\"/"/g' | \
  grep -o 'https*://[^"]*serverside\.doubleclick[^"]*' | head -5
```

### 1.4 Example URLs

URLs follow this pattern:
```
https://serverside.doubleclick.net/ddm/pfadx/N2207823.4466337AMAZONADVERTISIN/B34714557.437053572;sz=0x0;ord=${u.getRandomNumber()};dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;dc_tdv=1;dcmt=text/xml;dc_sdk_apis=[APIFRAMEWORKS];dc_omid_p=[OMIDPARTNER];dc_vast=3;gdpr=0;gdpr_consent=;dc_mpos=[BREAKPOSITION];ltd=
```

When calling the URL manually, replace macros:
- `${u.getRandomNumber()}` → any integer (e.g., `12345`)
- `[APIFRAMEWORKS]` → leave empty or remove
- `[OMIDPARTNER]` → leave empty or remove
- `[BREAKPOSITION]` → use `1` or leave empty

---

## Step 2: Retrieve the GAM Client Certificate

### 2.1 Where the Secret Lives

The GAM certificate and private key are stored in **AWS Secrets Manager** under:
- **Secret Name:** `GAM-Secret`
- **Account:** `850223472938` (MarioService alpha/shared account)
- **Region:** `us-east-1`

The secret is a JSON map with two keys:
- `"CERTIFICATE"` — base64-encoded X.509 certificate
- `"RSA PRIVATE KEY"` — base64-encoded PKCS8 private key

### 2.2 Authenticate with Admin Role

The `ConduitLimitedAccessRole` cannot read this secret. You need admin access:

```bash
ada credentials update --account=850223472938 --provider=conduit --role=IibsAdminAccess-DO-NOT-DELETE --once
```

### 2.3 Fetch the Secret

```bash
aws secretsmanager get-secret-value --secret-id GAM-Secret --region us-east-1
```

The response contains a `SecretString` field which is a JSON string with the `CERTIFICATE` and `RSA PRIVATE KEY` values.

### 2.4 Save Certificate and Key to PEM Files

Extract the base64 values from the secret and wrap them with PEM headers:

**Certificate (`/tmp/gam_cert.pem`):**
```
-----BEGIN CERTIFICATE-----
<base64 content from CERTIFICATE field>
-----END CERTIFICATE-----
```

**Private Key (`/tmp/gam_key.pem`):**
```
-----BEGIN RSA PRIVATE KEY-----
<base64 content from RSA PRIVATE KEY field>
-----END RSA PRIVATE KEY-----
```

The base64 content should be wrapped at 64 characters per line (standard PEM format).

---

## Step 3: Call the serverside.doubleclick URL with mTLS

### 3.1 The curl Command

```bash
curl -g -s \
  --cert /tmp/gam_cert.pem \
  --key /tmp/gam_key.pem \
  "https://serverside.doubleclick.net/ddm/pfadx/N2207823.4466337AMAZONADVERTISIN/B34714557.437053572;sz=0x0;ord=12345;dc_lat=;dc_rdid=;tag_for_child_directed_treatment=;tfua=;dc_tdv=1;dcmt=text/xml;dc_sdk_apis=;dc_omid_p=;dc_vast=3;gdpr=0;gdpr_consent=;dc_mpos=1;ltd="
```

**Important curl flags:**
- `-g` (or `--globoff`) — **required** — disables curl's globbing parser so square brackets and semicolons in the URL are not interpreted
- `--cert` — path to the client certificate PEM file
- `--key` — path to the private key PEM file

### 3.2 Expected Responses

| HTTP Code | Meaning |
|-----------|---------|
| 200 | Success — VAST XML response with ad creative |
| 204 | No ad available for this placement |
| 400 + "Authentication Error. No certificate found for the partner." | mTLS cert missing or invalid |
| 403 | Cert valid but not authorized for this placement |

### 3.3 Successful Response

A 200 response returns VAST 3.0 XML containing:
- `<Ad>` element with an InLine ad
- `<MediaFiles>` with video URLs (typically MP4)
- `<TrackingEvents>` for start, quartiles, complete, etc.
- `<VideoClicks>` with click-through URL
- `<Impression>` pixels

---

## Architecture Reference

### How the Service Does It (Code Path)

1. **`AdsUnwrappingControllerImpl.java`** — orchestrates the unwrapping flow
2. **`UnwrapOkHttpClient.java`** — makes the HTTP call using OkHttp with mTLS
3. **`HttpModule.java`** (`MarioService`) — builds the `OkHttpClient` with SSL context:
   - Injects `@Named("GAMSecret") Map<String, String>` (cert + key)
   - Uses `GAMLoadedKeyManagerSupplier` to parse cert/key into `KeyManager[]`
   - Creates `SSLContext` with the key managers
   - Attaches to `OkHttpClient.Builder.sslSocketFactory()`
4. **`GAMSecretModule.java`** — fetches the secret at service startup:
   - Assumes `ReadGAMSecretRole` via STS (role ARN from env var `GAMSecretRoleArn`)
   - Reads `GAM-Secret` from Secrets Manager
   - Returns as `Map<String, String>`

### Key File Locations

| File | Package | Purpose |
|------|---------|---------|
| `UnwrapOkHttpClient.java` | ACCCoreLibrary | HTTP client that makes the mTLS call |
| `AdsUnwrappingControllerImpl.java` | ACCCoreLibrary | Unwrapping orchestration |
| `HttpModule.java` | MarioService | Dagger module building OkHttpClient with SSL |
| `GAMSecretModule.java` | MarioService | Fetches cert/key from Secrets Manager |
| `GAMLoadedKeyManagerSupplier.java` | MarioService | Parses base64 cert/key into Java KeyManagers |

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| curl exit code 3 | Semicolons in URL interpreted by curl | Add `-g` flag |
| "Authentication Error. No certificate found" | Missing or wrong client cert | Verify cert/key PEM files are correct |
| AccessDenied on Secrets Manager | Using ConduitLimitedAccessRole | Use `IibsAdminAccess-DO-NOT-DELETE` role |
| Athena query running forever | Missing hour partition filter | Always include `hour in (...)` |
| Empty Athena results | Wrong day/hour or no traffic | Try broader hour range or previous day |

---

## Cleanup

After testing, remove the cert/key files:

```bash
rm -f /tmp/gam_cert.pem /tmp/gam_key.pem /tmp/gam_response.xml
```
