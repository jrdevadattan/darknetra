# Reused components

| Component | Pin | Integration |
|---|---|---|
| [Robin](https://github.com/apurvsinghgautam/robin) | `575d105e2f0fd61a450d5b4368535d0e83060354` | Attributed deterministic index parsing; MIT license in robin/LICENSE. No upstream LLM or direct Tor pipeline. |
| [Agent Reach](https://github.com/Panniantong/Agent-Reach) | `da5044d26fc6adddb6554d5679c94ac22e76e428`, 1.5.0 | Pinned package; public URL validation and web-channel challenge detection used by agent_reach_read. MIT package license. Upstream direct networking is replaced by capture. |
| [feedparser](https://github.com/kurtmckee/feedparser) | 6.0.14 | Parses captured RSS/Atom streams; BSD-2-Clause package license. |
| [Trafilatura](https://github.com/adbar/trafilatura) | 2.2.0 | Extracts main text from captured HTML without its crawler/downloader; Apache-2.0 package license. |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | 2.1.1 in uv.lock | Real stdio protocol server; MIT package license. |

Python package distributions carry their own licenses. Robin's extracted source
retains its notice here; this directory is included in the Docker image. Exact
dependency artifacts and hashes are recorded in backend/uv.lock.

Evaluated but not bundled: SearXNG (AGPL, optional operator-provided public JSON
endpoint), DDGS (its automatic network backends do not preserve our capture path),
Brave Search API and SerpApi (credentials and billing required). No claim that an
unconfigured provider or every Agent Reach channel is operational.
