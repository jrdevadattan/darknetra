# Account-based intelligence

Run these from the current chat directory, as separate CLI commands. Quote each selector as one argument. Retrieve only the case-relevant selector; do not walk related infrastructure automatically.

| Command after `node .agents/skills/darknetra-osint/scripts/osint.mjs` | Supported operation |
| --- | --- |
| `integrations` | Read local credential configuration; no provider request. |
| `flashpoint 'example.com' 5` | Search Flashpoint Ignite technical indicators by domain, public IP, URL or file hash; at most 10 returned records. This is not a search of every Flashpoint collection. |
| `recorded-future 'example.com'` | Retrieve one domain's entity and risk assessment. Public IP selectors are also supported. |
| `chainalysis '<supplied-wallet-address>'` | Retrieve direct sanctions identifications for one supplied wallet address. |

Use Research Analyst for relevant indicator context and Financial Analyst for a relevant sanctions lookup. The lead reviews their results. Do not run paid services indiscriminately. The external transport is HTTPS GET only, fixed provider hosts and paths, validated public DNS, no redirects, no retries, a 20-second request timeout and a one-megabyte response limit.

## Configuration and access

The operator copies `frontend/providers.example.json` to `frontend/.codex-chat/providers.json` and fills the `flashpoint`, `recorded-future`, and `chainalysis` values with the appropriate API credentials. The Docker volume already exposes this file and changes are read on the next command. Native installations can set `DARKNETRA_PROVIDER_FILE` to another absolute path. Never put keys in a prompt, command argument, committed file or browser storage. The helper alone loads them. Do not inspect the file in a chat tool call.

Standalone helpers also accept `FLASHPOINT_API_TOKEN`, `RECORDED_FUTURE_API_TOKEN` and `CHAINALYSIS_API_KEY` environment variables; each takes precedence over its file value. The file is preferred for the embedded CLI, whose shell environment can filter credential variables. These names are never sent to the browser with their values.

`credentials_required` means the operator must configure an account. `configured_unverified` means a nonempty credential is present, not that it is valid or licensed. Only a successful lookup verifies access to that operation. Settings → Intelligence tools and the `integrations` command show this distinction.

Stop on `AUTH_REQUIRED`, `ACCESS_DENIED` or `RATE_LIMITED`. Ask the operator to fix credentials/entitlement or wait; do not retry alternative credentials or hosts. `NOT_FOUND`, malformed responses and network failures are unsuccessful checks, not evidence of no matches.

## Interpretation and citations

Results include a provider, request URL, retrieval time, bounded text and scope. The UI saves this provider response as a source record in the current run. Cite that request URL or a provider record URL actually returned. Links appearing in a provider response are references; their target pages have not been fetched. Risk scores and identifications are provider assessments. Do not turn them into confirmed findings, personal identities or ownership links.

An empty successful Flashpoint response applies only to the selected indicator search. An empty Chainalysis `identifications` array is not a clean-wallet determination and does not assess indirect exposure. No transfer registration, alerts, wallet tracing, account enumeration, writes or enforcement actions are implemented.

**Chainalysis Reactor and KYT remain separate customer products.** Their catalogue entries require the operator's specific licence, API credentials and account documentation. The sanctions adapter does not connect these products or claim to trace funds. Do not guess their endpoints or claim their capabilities were used.

## Contract references

Reviewed 2026-09-08. Test fixtures validate the adapter contract; authenticated live operation still needs the operator's credentials.

- [Flashpoint's integrations](https://flashpoint.io/integrations/) and [Swimlane's maintained Flashpoint connector reference](https://docs.swimlane.com/connectors/flashpoint): Ignite `GET /technical-intelligence/v2/indicators`, `ioc_value`, `size`, Bearer authentication, `items` response. Customer documentation is available through the Flashpoint account.
- [Recorded Future domain lookup](https://docs.recordedfuture.com/reference/domain-lookup), [IP lookup](https://docs.recordedfuture.com/reference/ip-lookup) and [API entitlements](https://docs.recordedfuture.com/reference/api-entitlements): `GET /v2/domain/{id}` with `idn:` prefix or `/v2/ip/{id}` with `ip:` prefix; fields `entity,risk,intelCard`; `X-RFToken` authentication.
- [Chainalysis public sanctions service](https://public.chainalysis.com/) and [API authentication measurements](https://apis.io/security/chainalysis/chainalysis-authentication/): `GET /api/v1/address/{address}` with `X-API-Key`. The public documentation returned an access restriction during this implementation; customer developer documentation requires sign-in. Confirm account-specific access before claiming live validation. [Chainalysis's sanctions overview](https://www.chainalysis.com/blog/ofac-sanctions/) describes the narrower screening scope.
