# Project AK

Monorepo of the Project AK accessory store.

| Folder | Contents |
|---|---|
| [`BACKEND/`](BACKEND/) | FastAPI API: code, tests, migrations, Docker, planning docs ([BACKEND/README.md](BACKEND/README.md)) |
| [`FRONTEND/`](FRONTEND/) | Storefront and admin frontend |

- CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the backend jobs inside `BACKEND/`.
- The frontend contract is [BACKEND/docs/api/openapi.json](BACKEND/docs/api/openapi.json). Frontend notes are in [BACKEND/docs/api/FRONTEND.md](BACKEND/docs/api/FRONTEND.md).
