# Replit notes

This file held the original Replit agent's description of the project. It has been
replaced by two documents that are kept current:

- **[README.md](README.md)** — what the platform does, how to run it, and the API.
- **[PLAN.md](PLAN.md)** — the assessment of the original build, what was wrong and why,
  the 2026 competitive picture, and the roadmap.

## Running on Replit

`.replit` is configured to serve the application with Gunicorn on port 5000. The schema is
no longer created as an import side effect, so a fresh workspace needs two commands first:

```bash
flask --app app init-db
flask --app app seed-demo
```

`seed-demo` loads a 25-activity demo project and a `demo` / `demo1234` login.

If `DATABASE_URL` is set — as it is when the Replit PostgreSQL module is enabled — the
application uses it. Otherwise development falls back to a local SQLite file, so the
project also runs unchanged outside Replit.

Set `SESSION_SECRET` in the Replit Secrets pane. Production refuses to start without it.
