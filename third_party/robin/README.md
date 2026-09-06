# Robin attribution

Source: https://github.com/apurvsinghgautam/robin

Pinned commit: `575d105e2f0fd61a450d5b4368535d0e83060354` (2026-08-24).

`backend/darknetra/integrations/robin.py` adapts the anchor traversal/title filtering
from `search.py:fetch_search_results` and first-seen, trailing-slash deduplication
from `search.py:get_search_results`. Copyright (c) 2025 Apurv Singh Gautam; MIT
license reproduced in LICENSE.

Adaptations: separate deterministic parsing from transport; use existing
selectolax instead of BeautifulSoup; add typed results, bounded bytes/anchors/
titles/results, URL validation, and decoding of the known Ahmia redirect wrapper.
Hostname validation checks v3 shape, not the onion checksum or availability.

Provider response recognition follows the public Ahmia template
(`ahmia/ahmia-site`, `ahmia/templates/tor_results.html`): `#ahmiaResultsPage`,
`ol.searchResults li.result h4 a`, and explicit `#noResults`. A challenge, unknown
layout, empty result container, or wholly unparseable result set returns
`UNAVAILABLE`; only the provider's explicit no-results state produces a clean
empty result. Source inspected at
https://github.com/ahmia/ahmia-site/blob/master/ahmia/templates/tor_results.html.

The DARKNETRA `robin_search` adapter fetches a single public index with SafeHttp,
persists it through the capture gate, then runs this parser. Every hit cites that
index capture. It does not fetch the listed target pages or use Robin's LLM,
query expansion, UI, concurrent search transports, or Tor process.

Upstream code is reused under this license; no affiliation or endorsement is implied.
