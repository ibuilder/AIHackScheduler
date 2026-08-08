# BBSchedule

**Construction scheduling with a CPM engine you can check, and a schedule-quality score that tells you whether to trust it.**

[![CI](https://github.com/ibuilder/AIHackScheduler/actions/workflows/ci.yml/badge.svg)](https://github.com/ibuilder/AIHackScheduler/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-183%20passing-brightgreen)](tests/)

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
flask --app app init-db
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
services/
  schedule_analysis.py     Bridge between the ORM and core/
  schedule_risk.py         Simulation against a stored project
  schedule_optimizer.py    Optimisation, gated on schedule quality
  billing.py               Payment recording and invoice balances
  azure_ai.py              LLM interpretation, grounded in computed CPM
  optional.py              Lazy loading for every optional integration
blueprints/                Flask routes, one per feature area
models.py                  SQLAlchemy models, multi-tenant by company
tests/                     183 tests, hand-checked scheduling networks
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
pip install -e ".[dev]"            # pytest, ruff
```

---

## Development

```bash
pip install -e ".[dev]"
pytest                    # 183 tests
ruff check .              # lint
ruff format .             # format
```

CI runs tests on Python 3.11, 3.12 and 3.13, lints, and boots and seeds the application on
every push.

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

**Known gaps, tested as gaps** — seven admin, Azure and project-template pages render
templates that were never written, so those routes return 500. `tests/test_templates.py`
holds the list and fails if it grows.

The near-term priorities, in order:

1. **Schedule quality in the UI** — grade badges, drill-down to offending activities, and
   a trend across baseline revisions. The data is all computed; nothing surfaces it yet.
2. **P6 `.xer` and MS Project import** — nothing serious enters a scheduling tool through
   a web form.
3. **Resource-levelled scheduling** — the optimiser still emits generic advice where it
   could run a real serial-schedule-generation pass over existing assignments.
4. **Schedule comparison between baselines** — the snapshots are stored; diffing them is
   where delay analysis starts.

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
