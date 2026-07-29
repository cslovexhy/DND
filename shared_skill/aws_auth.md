# AWS Account Authentication

## Command

**Multi-Tenant cells (PublisherAdServer pipeline):**
```bash
ada credentials update --account={accountId} --provider=conduit --role=IibsAdminAccess-DO-NOT-DELETE --once
```

**Non-Live cells:**
```bash
ada credentials update --account={accountId} --provider=conduit --role=ConduitLimitedAccessRole --once
```

**Live cells (CRITICAL — different role per region):**
```bash
ada credentials update --account={accountId} --provider=conduit --role=ConduitLimitedAccessRole-{region_code} --once
```

| Region | Region Code | Role |
|--------|-------------|------|
| us-east-1 | iad | `ConduitLimitedAccessRole-iad` |
| us-west-2 | pdx | `ConduitLimitedAccessRole-pdx` |
| eu-west-1 | dub | `ConduitLimitedAccessRole-dub` |
| eu-south-2 | zaz | `ConduitLimitedAccessRole-zaz` |
| ap-northeast-1 | nrt | `ConduitLimitedAccessRole-nrt` |
| ap-southeast-1 | sin | `ConduitLimitedAccessRole-sin` |
| ap-southeast-2 | syd | `ConduitLimitedAccessRole-syd` |

**The plain `ConduitLimitedAccessRole` (no suffix) does NOT work for Live accounts.**

## Notes

- `--once` is required to prevent the command from running indefinitely
- Credentials are written to the `default` AWS profile
- After auth, use standard AWS CLI or `use_aws` tool with the appropriate region
- Credentials are short-lived; re-run before each batch of queries if needed

## All PAS Prod Accounts

### Alpha

| Cell | Account ID | Region |
|------|-----------|--------|
| ALPHA_IAD_LIVE | 590183788136 | us-east-1 |

### IAD (us-east-1)

| Cell | Account ID |
|------|-----------|
| IAD_PVC | 879302171300 |
| IAD_ITV | 153420359174 |
| IAD_ITV_DISPLAY | 227212439672 |
| IAD_TWITCH | 501943571949 |
| IAD_FIRETV | 917618614651 |
| IAD_GOODREADS | 090597479335 |
| IAD_ALEXA | 923427001389 |
| IAD_ALEXASKILLKIT | 717140067167 |
| IAD_AECS | 913094629860 |
| IAD_SHARED | 097766909876 |
| IAD_STORES | 245700518979 |
| IAD_LIVE_CELL001 | 144479903299 |
| IAD_LIVE_CELL002 | 657725064607 |
| IAD_LIVE_CELL003 | 113703410743 |
| IAD_LIVE_CELL004 | 705106558385 |
| IAD_LIVE_HYDRA_CELL001 | 010928219862 |
| IAD_LIVE_HYDRA_CELL002 | 010928219817 |
| IAD_LIVE_SHARED_CELL001 | 767397804526 |
| IAD_LIVE_SHARED_CELL002 | 654654367924 |

### PDX (us-west-2)

| Cell | Account ID |
|------|-----------|
| PDX_PVC | 905418296279 |
| PDX_ITV | 937476253340 |
| PDX_TWITCH | 496452323762 |
| PDX_FIRETV | 533266966049 |
| PDX_ALEXA | 730335257574 |
| PDX_SHARED | 637423511293 |
| PDX_STORES | 386706540079 |
| PDX_LIVE_CELL001 | 144479903299 |
| PDX_LIVE_CELL002 | 657725064607 |
| PDX_LIVE_CELL003 | 113703410743 |
| PDX_LIVE_CELL004 | 705106558385 |
| PDX_LIVE_HYDRA_CELL001 | 010928219862 |
| PDX_LIVE_HYDRA_CELL002 | 010928219817 |
| PDX_LIVE_SHARED_CELL001 | 767397804526 |
| PDX_LIVE_SHARED_CELL002 | 654654367924 |

### DUB (eu-west-1)

| Cell | Account ID |
|------|-----------|
| DUB_PVC | 317681948638 |
| DUB_ITV | 005628044282 |
| DUB_TWITCH | 581909520251 |
| DUB_FIRETV | 829665362950 |
| DUB_MINITV | 249444658829 |
| DUB_ALEXA | 100447011681 |
| DUB_SHARED | 767398104311 |
| DUB_STORES | 768333854519 |
| DUB_3PSTVAPPS | 746413875128 |
| DUB_LIVE_CELL001 | 144479903299 |
| DUB_LIVE_CELL002 | 657725064607 |
| DUB_LIVE_CELL003 | 113703410743 |
| DUB_LIVE_CELL004 | 705106558385 |
| DUB_LIVE_SHARED_CELL001 | 767397804526 |
| DUB_LIVE_SHARED_CELL002 | 654654367924 |

### ZAZ (eu-south-2)

| Cell | Account ID |
|------|-----------|
| ZAZ_PVC | 739275472447 |
| ZAZ_TWITCH | 796973516415 |
| ZAZ_FIRETV | 148761675882 |
| ZAZ_ALEXA | 495599749823 |
| ZAZ_AECS | 061220960583 |
| ZAZ_STORES | 677276121449 |
| ZAZ_LIVE_CELL001 | 144479903299 |
| ZAZ_LIVE_CELL002 | 657725064607 |
| ZAZ_LIVE_SHARED_CELL001 | 767397804526 |
| ZAZ_LIVE_SHARED_CELL002 | 654654367924 |

### NRT (ap-northeast-1)

| Cell | Account ID |
|------|-----------|
| NRT_TWITCH | 750018253103 |
| NRT_FIRETV | 299461394948 |
| NRT_LIVE_CELL001 | 144479903299 |
| NRT_LIVE_CELL002 | 657725064607 |
| NRT_LIVE_SHARED_CELL001 | 767397804526 |
| NRT_LIVE_SHARED_CELL002 | 654654367924 |

### FRA (eu-central-1)

| Cell | Account ID |
|------|-----------|
| FRA_STORES | 575108941796 |
| FRA_TWITCH | (check cells.ts) |

### SIN (ap-southeast-1)

| Cell | Account ID |
|------|-----------|
| SIN_LIVE_CELL001 | 144479903299 |
| SIN_LIVE_CELL002 | 657725064607 |

### SYD (ap-southeast-2)

| Cell | Account ID |
|------|-----------|
| SYD_LIVE_SHARED_CELL001 | 767397804526 |
| SYD_LIVE_SHARED_CELL002 | 654654367924 |

### Multi-Tenant (PublisherAdServer pipeline)

Auth: `ada credentials update --account={accountId} --provider=conduit --role=IibsAdminAccess-DO-NOT-DELETE --once`

| Cell | Account ID | Region |
|------|-----------|--------|
| MT_STANDARD_1_IAD | 623677486636 | us-east-1 |
| MT_STANDARD_1_PDX | 677450898219 | us-west-2 |
| MT_STANDARD_1_NRT | 150867077563 | ap-northeast-1 |
| MT_STANDARD_1_ZAZ | 503505393551 | eu-south-2 |
| MT_STANDARD_2_IAD | 446406251322 | us-east-1 |
| MT_STANDARD_2_PDX | 076360447415 | us-west-2 |
| MT_STANDARD_2_ZAZ | 094969483599 | eu-south-2 |
| MT_PVC_IAD | 412654396407 | us-east-1 |
| MT_PVC_PDX | 289400854957 | us-west-2 |
| MT_PVC_ZAZ | 024579064381 | eu-south-2 |
| MT_LIVE_CELL_1_ZAZ | 874777258994 | eu-south-2 |
| MT_LIVE_CELL_2_ZAZ | 490523971456 | eu-south-2 |

#### Legacy Multi-Tenant (on MarioService-cellular pipeline)

| Cell | Account ID | Region |
|------|-----------|--------|
| AMF/AMJS/Kindle/FireTablet ZAZ | 093113290656 | eu-south-2 |
| Kindle Eink IAD | 016055377375 | us-east-1 |
| IMDb DUB | 590183710214 | eu-west-1 |
| IMDb IAD | 891377402772 | us-east-1 |
| IMDb PDX | 975050124260 | us-west-2 |

### Live Logs (Centralized)

All Live Shared logs across all regions are routed to account **767397804526** in IAD (us-east-1).

## Notes on Live Cells

- Live cells (001-004) share the same account IDs across IAD/PDX/DUB/NRT/ZAZ/SIN
- Live Hydra cells only exist in IAD and PDX
- Live Shared cells exist in all regions
- EU Live endpoint (`api.eu.prod.live.pas.advertising.amazon.dev`) routes to DUB Live cells
- NA Live endpoint (`api.na.prod.live.pas.advertising.amazon.dev`) routes to IAD/PDX Live cells
