# Phase 2: implementation plan

**Not built.** Previously authorised; no implementation or deployment is performed by this documentation edit.
Functional contract and acceptance: [roadmap P2-1–P2-6](roadmap.md#phase-2-requirements).

| Roadmap IDs | Proposed implementation |
|---|---|
| P2-1 | `public_tools/search.py`: direct Tavily HTTP; `reading.py`: harness extraction + trafilatura |
| P2-2 | `weather.py`: Open-Meteo, reading the canonical location through the adapter |
| P2-3 | `news.py`: BBC RSS plus topic search; bounded selection/article cache owned outside reloaded tool instances |
| P2-4 | Private HF Docker Space API; no dependency on a running Mac |
| P2-5 | `network.py`: validated public-IP resolution/pinning and bounded fetching; HF Secrets and private robot config |
| P2-6 | `setup.py`: private credential prompts, deploy/configure/verify; stock replacement after acceptance |

`public_tools/api.py` supplies validated routes. `robot_tools/public_info.py` is the stdlib adapter.
These paths are proposed; the modules do not exist. The conversation model answers from returned evidence,
without another agent loop. Review app context ownership/reload interfaces before selecting the cache owner.

Execution order: service + adapter → combined unit/contract checks → local real-provider checks →
credential setup/hosted deployment → roadmap acceptance. Distinguish keyed checks from offline coverage.
Scanning, alignment, presence refresh and home/media integrations remain in the backlog, outside Phase 2.
