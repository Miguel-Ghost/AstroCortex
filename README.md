# AstroCortex

NASA Space Apps Challenge 2026 (Lima) — challenge "Planet X and SPHEREx".

A public web tool that shows how a small region of the sky changes in SPHEREx images over time
(an aligned flipbook per field), classifies the sources in the field and offers a guided tour.

| Folder | Content |
|---|---|
| `Backend/` | FastAPI API, SPHEREx image pipeline, classification engine interface, demo data and tests |
| `Frontend/` | React + Vite viewer (sky view, flipbook, classification panel, guide agent), deployed on Vercel by `.github/workflows/deploy-frontend.yml` after Frontend CI passes |
| `render.yaml` | Render Blueprint for the backend (web service + Postgres) |

See `Backend/README.md` to run, test and deploy the backend and `Frontend/README.md` for the viewer.
