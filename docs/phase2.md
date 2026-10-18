# Phase 2: implementation plan

**Built 2026-10-17:** all four tools. The Tavily key is stored; `read_article` was rebuilt the same day to
fetch pages directly (live-checked on Guardian and BBC pages). Requirements and acceptance: [roadmap P2-1–P2-6](roadmap.md#phase-2-requirements).
Supersedes the hosted-service design (private Space, service credential, adapter layer): none of it is needed.

| Roadmap IDs | Robot tool file | Provider |
|---|---|---|
| P2-1 | `robot_tools/web_search.py` | Tavily Search API |
| P2-2 | `robot_tools/read_article.py`, `robot_tools/approve_site.py` | The page itself (direct fetch), approved sites only; BeautifulSoup for text |
| P2-3 | `robot_tools/weather.py` | UK Met Office model (`ukmo_seamless`) via Open-Meteo; Open-Meteo geocoding (no key) |
| P2-4 | `robot_tools/news.py` | BBC RSS, Tavily topic search |
| P2-5 | All of the above | — |

Each file is self-contained: the app loads external tools by file path, so tools cannot import a shared
helper. Each carries a small stdlib HTTPS helper (fixed host, timeout, size cap, JSON, clear errors);
`read_article` carries its own network checks (P2-5).
The Tavily key is stored encrypted ([tools: API keys](tools.md#api-keys)). The news selection is stored in
`$REACHY_TOOLS_STATE_DIR/news_selection.json`, so numbering survives tool reloads. Tests mock HTTP.

Pollen's built-in search/weather are preinstalled remote tool Spaces (`pollen-robotics/reachy-mini-search-tool`,
`pollen-robotics/reachy-mini-weather-tool`); P2-6 removes them from the tool selection after acceptance.

Order: weather (no key) → web_search → read_article → news → unit tests throughout → key placed by
Simon → live provider checks → enable in development → acceptance → remove Pollen's built-in search/weather.
