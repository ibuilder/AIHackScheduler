#!/bin/sh
# Container entrypoint: bring the schema up to date, then start the process.
#
# Schema creation is no longer an import side effect — `db.create_all()` used to
# run whenever app.py was imported, which raced across gunicorn workers. That
# means a deployment has to create it deliberately, and nothing in the compose
# or Azure configuration did, so a fresh stack came up against an empty
# database and every request failed.
set -e

if [ "${SKIP_DB_INIT}" = "1" ]; then
    echo "entrypoint: SKIP_DB_INIT=1, leaving the schema alone"
else
    # `flask db upgrade`, not `init-db`. create_all only adds missing tables —
    # it never alters an existing one — so a database from an earlier release
    # would silently keep its old columns and constraints.
    #
    # Postgres accepts connections before it is ready to serve them, so retry
    # rather than assuming depends_on was enough.
    attempt=1
    until flask --app app db upgrade; do
        if [ "$attempt" -ge 15 ]; then
            echo "entrypoint: database did not become ready after $attempt attempts" >&2
            exit 1
        fi
        echo "entrypoint: database not ready (attempt $attempt), retrying in 2s"
        attempt=$((attempt + 1))
        sleep 2
    done
fi

if [ "${SEED_DEMO}" = "1" ]; then
    echo "entrypoint: SEED_DEMO=1, loading the demo project"
    flask --app app seed-demo
fi

exec "$@"
