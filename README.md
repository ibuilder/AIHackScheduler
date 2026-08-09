# BBSchedule

**Construction scheduling with a CPM engine you can check, and a schedule-quality score that tells you whether to trust it.**

[![CI](https://github.com/ibuilder/AIHackScheduler/actions/workflows/ci.yml/badge.svg)](https://github.com/ibuilder/AIHackScheduler/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-327%20passing-brightgreen)](tests/)

Most schedule tools assume the schedule they are given is sound. Most are not. BBSchedule
computes the critical path properly, then grades the schedule against the
[DCMA 14-Point Assessment](https://www.planacademy.com/dcma-14-point-schedule-assessment/)
and refuses to optimise one that fails.

---

## Try it in one minute

```bash
git clone https://github.com/ibuilder/AIHackScheduler.git
cd AIHackScheduler
pip install -r requirements.txt
export SESSION_SECRET=dev-secret          # Windows: set SESSION_SECRET=dev-secret
flask --app app db upgrade
flask --app app seed-demo
flask --app app run
```

No PostgreSQL, no Redis, no Azure account. Development falls back to SQLite and every
cloud integration is optional. Open <http://localhost:5000> and sign in as
`demo` / `demo1234`.

`seed-demo` loads a 25-activity commercial fit-out. It is deliberately imperfect — a
dangling activity, a lead, excess lags, unresourced work — so the schedule assessment has
real defects to report:

```
Grade F | score 50.0 | data date 2026-11-23 | baseline present
  PASS   1. Logic                        1 of 25 activities are dangling
  FAIL   2. Leads                        1 relationship uses a lead; leads hide true logic
  FAIL   3. Lags                         3 of 27 relationships carry a lag
  FAIL   4. Relationship Types           24 of 27 relationships are FS
  PASS   5. Hard Constraints             1 activity is pinned by a date constraint
  FAIL   6. High Float                   7 activities carry more than 44 days of float
  PASS   7. Negative Float               0 activities cannot meet their required dates
  PASS   8. High Duration                1 activity runs longer than a reporting quarter
  PASS   9. Invalid Dates                0 activities record work completed after the data date
  FAIL  10. Resources                    5 of 24 working activities carry no cost or resource
  FAIL  11. Missed Tasks                 2 of 4 completed activities slipped past baseline
  PASS  12. Critical Path Test           A 600-day delay moved the finish by 600 days
  PASS  13. Critical Path Length Index   CPLI of 1.000 on a 271-day critical path
  FAIL  14. Baseline Execution Index     4 of 7 activities due by the data date are complete
```

All fourteen run, because the demo carries a baseline and recorded actuals. On a project
with neither, checks 9, 11 and 14 report as **skipped** rather than passing — a score is
only as honest as what it admits it could not measure.

---

## What it does

### Scheduling engine — [`core/`](core/)

Pure Python, no Flask or SQLAlchemy imports, fully unit tested.

- **Critical Path Method** — topologically ordered forward and backward passes; all four
  relationship types (FS, SS, FF, SF) with positive or negative lag; **total float and
  free float computed separately**; cycle detection that names the loop; a driving-path
  walk that returns a connected chain rather than a bag of zero-float activities.
- **Working calendars** — configurable working weekdays and holidays. Finish dates are the
  last day worked, which is how planners read them.
- **DCMA 14-point assessment** — all fourteen checks, including the ones needing a
  baseline and recorded actuals.
- **Progress measurement** — Baseline Execution Index, finish variance against baseline,
  and forecast slippage. Its "behind" set is deliberately broader than DCMA check 11:
  that check counts only completed-but-late activities, so work that was due and never
  started is invisible to it — which is the more urgent problem.
- **Monte Carlo risk** — three-point duration estimates sampled through the network
  thousands of times, giving P10/P50/P80/P90 completion dates, the measured probability
  of meeting the deterministic date, and a criticality index per activity. Seeded, so the
  same schedule gives the same answer every run.

```python
from core import Activity, Relationship, RelationType, calculate_cpm, assess_schedule

activities = [
    Activity("A", "Excavate", 5),
    Activity("B", "Pour footings", 8),
    Activity("C", "Cure", 7),
]
links = [
    Relationship("A", "B"),
    Relationship("B", "C", RelationType.FS, lag=2),
]

result = calculate_cpm(activities, links)
print(result.project_duration)          # 22
print(result.critical_path)             # ['A', 'B', 'C']
print(result.activities["B"].total_float)   # 0

report = assess_schedule(activities, links)
print(report.grade, report.is_optimisable)
```

### Three planning methodologies, one data model

A `Task` carries CPM fields, `station_start`/`station_end` for linear (time–distance)
scheduling, and `pull_plan_week` for Last Planner–style pull planning. A contractor running
a linear infrastructure job alongside a vertical build does not need two products that
cannot talk to each other.

### AI grounded in computed facts

Schedule analysis, optimisation, and completion forecasting run CPM and the quality
assessment **first**, then pass the results into the prompt as given. The model interprets;
it does not calculate. The system prompt forbids claiming a saving on an activity that is
not on the critical path, and the optimiser refuses to run at all against a schedule whose
logic fails the blocking checks.

Optimising an unsound network produces confident nonsense. This is the difference between
AI that helps and AI that launders guesswork.

---

## File exchange

Real schedules live in Primavera P6 and Microsoft Project. Nothing serious
enters a scheduling tool through a web form.

| Format | Read | Write | |
|---|---|---|---|
| **Primavera XER** (`.xer`) | yes | yes | Pure Python, no dependency |
| **MS Project XML** (`.xml`, MSPDI) | yes | yes | Pure Python, no dependency |
| **MS Project** (`.mpp`) | yes* | **no** | *needs `pip install -e ".[mpp]"` and a JVM |

**`.mpp` cannot be written — by anyone.** The binary format is proprietary and
only partly understood;
[MPXJ's own maintainer says so](https://www.mpxj.org/faq/). Microsoft's
supported interchange for writing is MSPDI XML, which Project opens directly
and can then save as `.mpp`. Export MSPDI and you have your round trip.

```bash
flask --app app import-schedule plan.xer --company 1 --user 1
flask --app app export-schedule 1 --format mspdi --out plan.xml
flask --app app schedule-formats     # what this deployment can actually do
```

The readers get the four things wrong importers get wrong. P6 writes
relationship types as `PR_SS`, not `SS` — store the raw string and every
start-to-start tie silently becomes finish-to-start. Durations are hours
against a calendar that is not always eight hours a day. Milestones are
zero-duration and clamping them to one day moves every downstream date. Costs
live on `TASKRSRC` and notes on `TASKMEMO`, not on `TASK`. Each has a named
test.

Round trips are tested by exporting, re-importing, and asserting the *computed
schedule* has not moved — same duration, same finish, same driving path.

Anything a reader could not map is returned as a warning rather than dropped.

---

## API

All endpoints are company-scoped; a request for another tenant's project is
indistinguishable from a request for one that does not exist.

| Endpoint | Returns |
|---|---|
| `GET /api/schedule/projects/<id>/cpm` | Every activity with early/late dates, total float, free float, criticality |
| `GET /api/schedule/projects/<id>/health` | DCMA 14-point assessment, grade, and per-check offenders |
| `GET /api/schedule/projects/<id>/critical-path` | The driving path only, for chart overlays |
| `GET /api/schedule/projects/<id>/progress` | Baseline Execution Index, variance, worst slippage |
| `GET /api/schedule/projects/<id>/risk` | Monte Carlo percentiles and criticality index |
| `POST /api/schedule/projects/<id>/baseline` | Freeze the current plan as the baseline |
| `GET /api/financial/aged-receivables` | Outstanding balances bucketed by days overdue |
| `POST /api/schedule/import` | Upload a `.xer`, `.xml` or `.mpp` as a new project |
| `GET /api/schedule/projects/<id>/export/<format>` | Download as `xer` or `mspdi` |
| `GET /api/schedule/formats` | What this deployment can read and write |

```bash
curl -b cookies.txt http://localhost:5000/api/schedule/projects/1/health | jq '.grade, .score'
```

---

## Architecture

```
core/                    Pure scheduling algorithms — no Flask, no database
  cpm.py                   Forward/backward passes, float, cycle detection
  calendar.py              Working-day ↔ calendar-date mapping
  schedule_health.py       DCMA 14-point assessment
  progress.py              Baseline Execution Index and variance
  risk.py                  Monte Carlo simulation over the network
  exchange.py              Format-neutral schedule model
  xer.py                   Primavera XER reader and writer
  mspdi.py                 MS Project XML reader and writer
services/
  schedule_analysis.py     Bridge between the ORM and core/
  schedule_risk.py         Simulation against a stored project
  schedule_optimizer.py    Optimisation, gated on schedule quality
  billing.py               Payment recording and invoice balances
  schedule_io.py           File formats bridged to the ORM
  azure_ai.py              LLM interpretation, grounded in computed CPM
  optional.py              Lazy loading for every optional integration
blueprints/                Flask routes, one per feature area
models.py                  SQLAlchemy models, multi-tenant by company
tests/                     284 tests, hand-checked scheduling networks
seed_demo.py               A realistic, deliberately imperfect demo project
```

The layering is the point: `core/` knows nothing about the web application, so its
correctness can be established in isolation and its results reused anywhere.

---

## Configuration

Only two variables are needed to run:

| Variable | Required | Default |
|---|---|---|
| `SESSION_SECRET` | yes | — (production refuses to start without it) |
| `DATABASE_URL` | no | `sqlite:///bbschedule-dev.db` in development |
| `FLASK_ENV` | no | `development` |

Everything else is optional and the feature degrades cleanly when absent. See
[`.env.example`](.env.example).

```bash
pip install -e ".[postgres]"       # PostgreSQL
pip install -e ".[async]"          # Celery + Redis background tasks
pip install -e ".[integrations]"   # Azure AI, Power BI, Stripe, Excel import
pip install -e ".[mpp]"            # reading binary .mpp (needs a JVM)
pip install -e ".[dev]"            # pytest, ruff
```

---

## Development

```bash
pip install -e ".[dev]"
pytest                    # 284 tests
ruff check .              # lint
ruff format .             # format
```

CI runs tests on Python 3.11, 3.12 and 3.13, lints, builds the wheel and the Docker image,
checks migrations match the models, and boots and seeds the application on every push.

### Keeping CI honest

Every dependency carries an upper bound, and the test and lint tooling is pinned. Without
that, a release on someone else's schedule fails a build nobody touched — which had already
started happening: `ruff` reformatted Markdown in a new minor and broke lint, and
`flask-limiter` had drifted from 3.x to 4.x unnoticed, working by luck rather than by
contract.

Bounds alone would just freeze the project, so Dependabot proposes raising them weekly.
Upgrades then arrive as pull requests that run the full suite, rather than landing silently
in the next build.

Its first run made the point better than the argument does. Seven proposals: the GitHub
Actions were three majors behind, the base image was three Python releases behind, and
`redis`, `openai`, `stripe` and `mpxj` had all published majors the bounds excluded. Two of
those proposals found real defects rather than needing them — see *A bump that found a bug*
below.

A green build has to mean something, so two things exist to stop it going hollow:

- **The optional extras are installed and imported.** None of them appear in
  `requirements.txt`, so for a while a proposal widening the `openai` bound passed all eight
  jobs without one line of the affected code being imported. The `extras` job installs
  `.[postgres,async,integrations,mpp]`, imports every optional package and boots the
  application with them present.
- **The image ships a Python the tests run.** `tests/test_deployment.py` fails if the
  Dockerfile's base image is not in the CI matrix, so production is never the first place an
  incompatibility appears.

### A bump that found a bug

The base image bump failed, and the failure was worth more than the upgrade. The Dockerfile
named its Python version three times — twice on `FROM` lines and once, thirty lines below, in
`COPY --from=builder /usr/local/lib/python3.11/site-packages`. Nothing recognises a `COPY`
path as a version declaration, so *any* Python bump broke the build. Dependencies now install
into a virtualenv at `/opt/venv` and the version appears only where it is declared.

The `mpp` extra exposed something worse. `read_mpp` and `_from_mpxj` were written against the
MPXJ API and committed without ever being executed — MPXJ is a Java library reached through
JPype, and no machine here had a JVM, so `_from_mpxj` even carried a `pragma: no cover`
admitting it. The first run raised `AttributeError`: `mpxj.initialize()` does not exist.

Underneath that was a quieter one. The relationship type was looked up on
`str(relation.getType())` with a `.get(..., FS)` default. MPXJ overrides `toString()` to a
display form, so the lookup missed every time and the default absorbed it: **every
relationship in every `.mpp` import silently became Finish-Start**, whatever the file said.

What caught it is that MPXJ's `UniversalProjectReader` reads MSPDI XML as well as binary
`.mpp`. `tests/test_mpp.py` puts one file through both MPXJ and this project's own
pure-Python reader and compares activities, durations and links — so no `.mpp` is needed, and
a disagreement means one of the two readers is wrong. It reported three Finish-Start links
where the file's type codes were 1, 3 and 0: FS, SS and FF. The mapping now reads
`java.lang.Enum.name()`, and an unrecognised type is recorded in `schedule.warnings` rather
than assumed.

### And one only a real file could find

That cross-check has a blind spot: it can only compare the two readers on MSPDI, because
MSPDI is the only format both understand. `.mpp` is the one format in this project that no
test can generate — nothing writes it but Microsoft Project — so `tests/data/example.mpp` is
vendored (MIT, from the author of MPXJ; provenance in [tests/data/README.md](tests/data/README.md)).

The first run of it read three 3-day tasks as **0.38 days each**. `Duration.getDuration()`
returns a bare number in whatever unit the file used — days, here — and the code took it as
hours and divided by hours-per-day, so every duration came out eight times too short.
Relationship lag had the same bug. Neither could show up in the MSPDI comparison, because
MSPDI genuinely does store hours.

It parsed cleanly, warned about nothing, and failed nothing. Durations now go through MPXJ's
`convertUnits`, and the test asserts what the file says rather than that a number came back:

```
name='example.mpp'  activities=3  relationships=2  warnings=0
     1    3.00d  Task 1
     2    3.00d  Task 2
     3    3.00d  Task 3
project_duration=9 working days, critical_path=['1', '2', '3']
```

The last line is the one that matters: a real Microsoft Project file, read from binary and
scheduled through the CPM engine.

---

## Deployment

```bash
docker compose -f deployment/docker-compose.yml up
```

Brings up the application, PostgreSQL, Redis and the Celery worker and beat scheduler. The
build context is the repository root, so run it from there. Set `DB_PASSWORD` and
`SESSION_SECRET` first; add `SEED_DEMO=1` to load the demo project on first start.

The container entrypoint runs `flask db upgrade` before starting, retrying until PostgreSQL
is accepting queries. Workers run with `SKIP_DB_INIT=1` so they cannot race the web process.

### Migrations

```bash
flask --app app db upgrade      # bring a database to the current schema
flask --app app db migrate -m   # after changing a model
flask --app app db check        # is anything unmigrated?
```

`0001_baseline` is the schema exactly as it stood at the original commit. `0002_rebuild_schema`
carries everything this rebuild added: baseline and actual dates, the data date, schedule
baselines, equipment usage and maintenance, the indexes, and moving `project_number` from a
global unique constraint to one scoped per company.

**If your database predates this work**, stamp it against the baseline first, then upgrade:

```bash
flask --app app db stamp 0001_baseline
flask --app app db upgrade
```

Do not use `init-db` for a database you intend to keep. `create_all` only adds *missing*
tables — it never alters an existing one — so it would leave old columns and constraints
silently in place. It stays for scratch databases and test fixtures, and stamps itself at
head so a later upgrade does not double-apply.

CI fails if the models change without a migration.

`deployment/azure-deploy.yml` describes the same stack as Azure Container Apps.

---

## Status and roadmap

This is working software with a solid core and an unfinished perimeter. Being specific
about which is which:

**Solid** — CPM engine, all fourteen DCMA checks, working calendars, baseline and
progress measurement, Monte Carlo risk, multi-tenant isolation, the schedule analysis API,
payment recording and invoice balances, equipment utilisation from logged hours.

**Working, thin** — project and task management, Gantt/linear/pull-planning views, auth
and roles, transaction ledger.

**Still a facade** — `reports/executive_dashboard.py` generates its revenue trends and
geographic breakdown rather than measuring them. Those payloads now carry a `simulated`
flag so the UI can label them, but they should be built or removed.

**Not attempted** — card processing. Payments are recorded, not taken: no key management,
no webhook reconciliation, no PCI scope. The README previously advertised "Stripe
integration in progress" against no implementation of any kind.

**Every page renders** — the nine admin, Azure, project-template and reporting pages that
rendered templates nobody had written are built, and the two analytics endpoints whose
helpers did not exist are implemented. `tests/test_all_routes.py` walks the URL map and
requests all 90 GET routes signed in; 83 return 200, none return a server error. It walks
the map rather than a list, so a route added tomorrow is covered the day it appears.

**Resource optimisation and portfolio insight** — `/api/ai/resource-optimization/<id>`
reports utilisation per resource, names what is over-allocated and by how many units,
prices the excess at each resource's own unit cost, and ranks the moves.
`/api/ai/company-insights` reports completion rate, spend against approved budget,
throughput trend across six periods, and DCMA health per project. Both are deterministic:
the same data gives the same answer, which is the property a schedule review needs.
Azure OpenAI is not required for either.

The near-term priorities, in order:

1. **Schedule quality in the UI** — grade badges, drill-down to offending activities, and
   a trend across baseline revisions. The data is all computed; nothing surfaces it yet.
2. **Resource-levelled scheduling** — the optimiser still emits generic advice where it
   could run a real serial-schedule-generation pass over existing assignments.
3. **Schedule comparison between baselines** — the snapshots are stored; diffing them is
   where delay analysis starts, and delay analysis is where the money is.

[`PLAN.md`](PLAN.md) has the full assessment: what was wrong, what the market looks like in
2026, and why schedule quality is the position worth taking.

---

## Contributing

Issues and pull requests are welcome. Please keep `core/` free of Flask and SQLAlchemy
imports, and add a hand-checkable test for any change to the scheduling maths — a
scheduling engine is only trustworthy if its answers can be verified by hand.

By contributing you agree that your contribution is licensed under the MIT licence.

## License

[MIT](LICENSE). Use it, fork it, ship it — the only condition is that the copyright notice
travels with it.

The repository previously described itself as proprietary software developed for Balfour
Beatty US while carrying no `LICENSE` file at all, which granted nobody any rights and
asserted an affiliation the code does not evidence. Both are resolved: the licence is MIT
and the branding is the project's own.

---

*Built on the observation that most construction schedules cannot support the decisions
made from them, and that this is measurable.*
