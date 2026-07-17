# Third-Party Notices

Phase 1 through Phase 3 dependencies are resolved with `uv.lock` and `pnpm-lock.yaml`; those lockfiles are the authoritative complete version and integrity inventory, including transitive packages. The directly introduced dependencies reviewed for this phase are listed below. No dependency is vendored into this repository.

| Name | Locked version | License | Source | Usage |
|---|---:|---|---|---|
| aiosqlite | 0.22.1 | MIT | https://pypi.org/project/aiosqlite/ | Async SQLite |
| azure-identity | 1.25.3 | MIT | https://pypi.org/project/azure-identity/ | Entra ID credential provider |
| fastapi | 0.139.0 | MIT | https://pypi.org/project/fastapi/ | HTTP API |
| langgraph | 1.2.9 | MIT | https://pypi.org/project/langgraph/ | Graph orchestration |
| langgraph-checkpoint-sqlite | 3.1.0 | MIT | https://pypi.org/project/langgraph-checkpoint-sqlite/ | Local checkpoints |
| openai | 2.45.0 | Apache-2.0 | https://pypi.org/project/openai/ | Azure OpenAI adapter |
| pydantic-settings | 2.14.2 | MIT | https://pypi.org/project/pydantic-settings/ | Environment configuration |
| PyMySQL | 1.2.0 | MIT | https://pypi.org/project/PyMySQL/ | TLS-verified read-only MySQL connector |
| python-multipart | 0.0.32 | Apache-2.0 | https://pypi.org/project/python-multipart/ | Future upload request boundary |
| SQLAlchemy | 2.0.51 | MIT | https://pypi.org/project/SQLAlchemy/ | Metadata persistence |
| uvicorn | 0.51.0 | BSD-3-Clause | https://pypi.org/project/uvicorn/ | ASGI server |
| httpx | 0.28.1 | BSD-3-Clause | https://pypi.org/project/httpx/ | Backend API tests |
| mypy | 1.20.2 | MIT | https://pypi.org/project/mypy/ | Python type checking |
| pytest | 8.4.2 | MIT | https://pypi.org/project/pytest/ | Backend tests |
| pytest-asyncio | 1.4.0 | Apache-2.0 | https://pypi.org/project/pytest-asyncio/ | Async backend tests |
| Ruff | 0.15.21 | MIT | https://pypi.org/project/ruff/ | Python lint/format |
| React | 19.2.7 | MIT | https://www.npmjs.com/package/react | Web UI |
| React DOM | 19.2.7 | MIT | https://www.npmjs.com/package/react-dom | Web rendering |
| Vite | 7.3.6 | MIT | https://www.npmjs.com/package/vite | Web dev/build |
| TypeScript | 5.9.3 | Apache-2.0 | https://www.npmjs.com/package/typescript | Frontend type checking |
| @vitejs/plugin-react | 5.2.0 | MIT | https://www.npmjs.com/package/@vitejs/plugin-react | React/Vite integration |
| Vitest | 3.2.7 | MIT | https://www.npmjs.com/package/vitest | Frontend unit tests |
| @playwright/test | 1.61.1 | Apache-2.0 | https://www.npmjs.com/package/@playwright/test | Browser smoke test |
| @testing-library/react | 16.3.2 | MIT | https://www.npmjs.com/package/@testing-library/react | UI tests |
| @testing-library/jest-dom | 6.9.1 | MIT | https://www.npmjs.com/package/@testing-library/jest-dom | DOM assertions |
| jsdom | 26.1.0 | MIT | https://www.npmjs.com/package/jsdom | Unit-test DOM |
| @types/react | 19.2.17 | MIT | https://www.npmjs.com/package/@types/react | React types |
| @types/react-dom | 19.2.3 | MIT | https://www.npmjs.com/package/@types/react-dom | React DOM types |
| SQLGlot | 28.10.1 | MIT | https://pypi.org/project/sqlglot/ | SQL AST parsing and dialect normalization |
| DuckDB | 1.5.4 | MIT | https://pypi.org/project/duckdb/ | Bounded in-memory cross-source joins |
| pandas | 3.0.3 | BSD-3-Clause | https://pypi.org/project/pandas/ | Controlled dataframe analysis |
| pandas-stubs | 3.0.3.260530 | BSD-3-Clause | https://pypi.org/project/pandas-stubs/ | Pandas type checking |
| Plotly.js dist min | 3.0.0 | MIT | https://www.npmjs.com/package/plotly.js-dist-min | Validated chart rendering |
| @types/plotly.js | 3.0.0 | MIT | https://www.npmjs.com/package/@types/plotly.js | Plotly TypeScript types |

| pypdf | 6.14.2 | BSD-3-Clause | https://pypi.org/project/pypdf/ | Static PDF text parsing |
| python-docx | 1.2.0 | MIT | https://pypi.org/project/python-docx/ | Static DOCX parsing |
| openpyxl | 3.1.5 | MIT | https://pypi.org/project/openpyxl/ | Read-only XLSX parsing |
| PyYAML | 6.0.3 | MIT | https://pypi.org/project/PyYAML/ | Skill metadata serialization |
| reportlab | 4.5.1 | BSD-3-Clause | https://pypi.org/project/reportlab/ | Test-only PDF fixtures |
| types-openpyxl | 3.1.5.20260518 | Apache-2.0 | https://pypi.org/project/types-openpyxl/ | Parser type checking |
| types-PyYAML | 6.0.12.20260518 | Apache-2.0 | https://pypi.org/project/types-PyYAML/ | YAML type checking |

No GPL, AGPL, SSPL, or source-available direct dependency was introduced. Before release or dependency updates, generate and review a full transitive SBOM/license report from both lockfiles under the company-approved software-composition process.
