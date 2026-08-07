# BBSchedule — Improvement Plan

*Assessment date: 7 August 2026. Baseline: commit `aecb85f`, the single commit in the repository.*

---

## 1. What this project is trying to be

The repository presents itself as an enterprise construction scheduling platform for
Balfour Beatty US. Stripped of the marketing, the intent is specific and worth taking
seriously:

> Give a general contractor one place to hold a project's schedule across three
> planning methodologies — CPM/Gantt, linear (time–distance), and Last Planner–style
> pull planning — and then apply AI to optimise it.

That combination is genuinely underserved. Primavera P6 owns CPM. Touchplan and vPlanner
own pull planning. TILOS owns linear scheduling. Very few products hold all three against
one data model, and a contractor running a linear infrastructure job alongside a vertical
build currently pays for two tools that cannot talk to each other.

The three-methodology data model is the real asset here. `Task` already carries
`station_start`/`station_end` for linear scheduling and `pull_plan_week` for pull planning
alongside standard CPM fields. That is the defensible idea.

## 2. What was actually there

The application was generated in one pass on Replit and never iterated. Breadth is
extensive — 96 files, 16 blueprints, financial management, equipment management, Power BI,
Azure AI, Microsoft Fabric — but almost nothing had been exercised.

### The critical path calculation was wrong

`services/schedule_optimizer.py::_find_critical_path` ran its forward pass by iterating
`tasks` in list order rather than topological order. A task whose predecessor appeared
later in the list read `earliest_finish.get(predecessor.id, 0)` — a dictionary miss — and
silently used `0`. The critical path therefore depended on database row ordering.

The backward pass had the same defect and could leave `latest_start` at `float('inf')`,
after which `float_time <= 0` classified activities arbitrarily. Only Finish-to-Start
logic was handled; SS, FF, and SF relationships were read from the database and ignored.

Everything downstream — the Gantt critical-path highlight, every optimisation
recommendation, every AI prompt claiming to analyse the critical path — inherited this.

### The AI had nothing solid to stand on

`services/azure_ai.py` sent raw task rows to a model and asked it for "critical path
analysis". With no computed float in the prompt, the model had no way to produce one
except by inventing it. It then called `json.loads()` on a free-form completion, so even a
good answer usually surfaced as a decode error.

### Defects found and fixed

| Area | Defect | Consequence |
|---|---|---|
| `services/schedule_optimizer.py` | CPM forward/backward passes not topologically ordered | Critical path depended on row order |
| `services/schedule_optimizer.py` | SS/FF/SF relationships parsed then discarded | Overlapping work modelled as sequential |
| `blueprints/projects.py:79` | `role.name != 'ADMIN'` bypassed the company check | **Any admin could read any other company's project** |
| `security/rate_limiting.py` | Declared dummy routes at `/auth/login`, `/api/<path:path>` | Shadowed live routes; limited nothing |
| `security/rate_limiting.py` | `Limiter(app, key_func=…)` positional form | Removed in flask-limiter 3.x; always hit the fallback |
| `security/rate_limiting.py` | Blocked any query string containing `select`/`update`/`delete`/`script` | `?sort=updated_at` returned 400; no real protection |
| `database/optimizations.py` | `db.engine.execute()` | Removed in SQLAlchemy 2.0 — **every index silently failed** |
| `database/optimizations.py` | `CREATE INDEX CONCURRENTLY` / `VACUUM` inside a transaction | Cannot run there; racy across workers |
| `models.py` | No cascade on `TaskDependency` | Deleting a project nulled `task_id`, corrupting the table |
| `blueprints/scheduling.py:128` | `task.status = data['status']` wrote a raw string to an enum column | Every later load of that task raised |
| `app.py:118` | `app.secret_key = os.environ.get("SESSION_SECRET")` overwrote the config value with `None` | Sessions and flash messages broke silently |
| `app.py` | `db.create_all()` at import time | Raced across gunicorn workers; bypassed Flask-Migrate |
| `app.py` | Every error handler returned JSON | A mistyped URL showed raw JSON to a browser |
| `routes.py:83` | `app.logger` — `app` never imported | `NameError` inside the dashboard error handler |
| `tasks/background_tasks.py:271` | `date` never imported | `NameError` on every Excel import |
| `services/azure_ai.py:5` | `from openai import AzureOpenAI` at module scope | **Application would not boot without an optional package** |
| `config.py` (root) | Shadowed by the `config/` package | Never loaded; Azure and Foundry settings were dead |
| `models/equipment.py` | Directory without `__init__.py`, shadowed by `models.py` | Unreachable duplicate model |

None of this was discoverable, because there were no tests, no CI, and no way to run the
application without first provisioning PostgreSQL.

## 3. Where the market actually is

Research into the 2026 landscape sharpens what "AI construction scheduling" has to mean:

- **[ALICE Technologies](https://www.alicetechnologies.com/home)** generates and compares
  hundreds of millions of build sequences, working directly from P6 files. Generative
  scheduling, most valuable in preconstruction.
- **[nPlan](https://www.nplan.io/)** forecasts delay risk from a corpus of 750,000+
  historical schedules, for clients including Skanska and Laing O'Rourke. Most valuable
  during execution.
- **Procore** embeds AI across an already-broad platform; its scheduling depth
  [lags the specialists](https://aibuildingtools.com/blog/ai-construction-scheduling).
- Contractors using these tools
  [report 17–30% fewer schedule overruns](https://aibuildingtools.com/blog/ai-construction-scheduling).

Two conclusions follow.

**First, the moat is data and simulation, not prompting.** ALICE's advantage is a
recombination engine; nPlan's is a proprietary corpus. Neither can be reached by calling a
chat completions endpoint. A small project competing on "we also call GPT" has nothing.

**Second, there is an unoccupied position: schedule quality as the product.** Every one of
these tools assumes a trustworthy schedule as input. In practice most are not. The
industry already has a shared standard for measuring this — the
[DCMA 14-Point Assessment](https://www.planacademy.com/dcma-14-point-schedule-assessment/),
developed by the Defense Contract Management Agency and now used across infrastructure,
energy, and commercial construction to tell a genuine planning instrument from an
administrative artefact. SmartPM built a business on it.

Schedule quality is cheap to compute, needs no proprietary corpus, and is the honest
precondition for everything else. That is where this project can be credible today.

## 4. What has been built

### A verifiable scheduling engine — `core/`

A pure-Python package with no Flask or SQLAlchemy imports, so it is unit-testable and
reusable from a CLI or a worker.

- **`core/cpm.py`** — topologically ordered forward and backward passes; all four
  relationship types with positive or negative lag; total float and free float computed
  separately; cycle detection that names the offending loop; a `longest_path` walk that
  returns the connected driving path rather than a bag of zero-float activities.
- **`core/calendar.py`** — working-day to calendar-date mapping, with configurable working
  weekdays and holidays. Finish dates are the last day worked, which is how planners read
  them.
- **`core/schedule_health.py`** — the DCMA 14-point assessment. Checks 1–8, 12 and 13 are
  computed from the logic network. Checks 9, 11 and 14 need recorded baseline and actual
  finish dates, which the schema does not yet hold; they report as **skipped with a
  reason** and are excluded from the score, rather than passing vacuously.

`assess_schedule` also exposes `is_optimisable`, which gates the optimiser: a schedule
failing the logic, negative-float, or CPLI checks cannot be optimised against, because
every optimisation decision depends on float being meaningful.

### Grounded AI

`services/azure_ai.py` now computes CPM and schedule quality first and passes them into
the prompt as given facts. The model's job is interpretation and narrative, not arithmetic.
The system prompt forbids claiming a saving on an activity that is not on the critical
path, and `response_format={"type": "json_object"}` makes the reply parseable.

This is a deliberate architectural stance: **the deterministic engine is the product; the
model is a presentation layer over it.**

### It runs in one minute

Development now falls back to SQLite, optional integrations are lazily imported, and
`flask seed-demo` loads a 25-activity, 27-link commercial fit-out. The demo schedule
deliberately contains a dangling activity, a lead, excess lags, and unresourced work, so
the assessment has real defects to find — it grades **F (54.5%)** and names each one.

### Verification

73 tests. The CPM tests use networks whose answers can be checked by hand, which is the
only way to be confident about a scheduling engine. CI runs tests on Python 3.11/3.12/3.13,
lints with ruff, and boots and seeds the application on every push.

## 5. What comes next

### Near term — finish the schedule-quality story

1. **Record baseline and actual dates.** Add `baseline_start`, `baseline_finish`,
   `actual_start`, `actual_finish` to `Task`, plus a `ScheduleBaseline` table. This alone
   unlocks DCMA checks 9, 11 and 14 and makes Baseline Execution Index and schedule
   variance computable. *This is the single highest-value change remaining.*
2. **Schedule quality in the UI.** A grade badge on every project, a drill-down naming
   each failing activity, and a trend line across submissions. This is the feature people
   would pay for and it is nearly complete already.
3. **Import P6 and MS Project.** Nothing serious enters through a web form. `.xer` via
   [PyP6Xer](https://pypi.org/project/PyP6Xer/) or the broader
   [MPXJ](https://www.mpxj.org/) for `.mpp`, `.xml`, and `.pmxml`. Without an import path
   the platform cannot touch a real project.
4. **Adopt Flask-Migrate properly.** `flask db init` and a baseline migration; remove the
   remaining reliance on `create_all` outside tests.

### Medium term — earn the "AI" in the name

5. **Monte Carlo risk analysis.** Three-point duration estimates plus 10,000 iterations
   over the existing engine produces a P50/P80 completion date and a criticality index per
   activity. Deterministic, explainable, needs no external service, and is the credible
   version of "predictive analytics" — the current `azure_ai/predictive_analytics.py`
   returns hardcoded values.
6. **Resource-levelled scheduling (RCPSP).** The optimiser currently emits generic advice
   ("consider dynamic resource allocation"). A real serial-schedule-generation heuristic
   over the existing resource assignments would produce actual levelled dates.
7. **Schedule comparison.** Diff two revisions: what moved, what was added, what logic
   changed. Delay analysis is where the money is in construction, and it is pure
   computation over data already held.

### Ongoing — the parts that were never real

8. **Retire or finish the facade.** `blueprints/equipment_management.py` returns
   placeholder maintenance and utilisation data; `Equipment.utilization_rate` returns a
   hardcoded `75.5`; the financial module documents "Stripe integration in progress" with
   no implementation. Each should either be built or removed. Shipping a dashboard of
   invented numbers is worse than shipping nothing.
9. **Resolve the licensing contradiction.** The README claims "proprietary software
   developed for Balfour Beatty US. All rights reserved.", but the repository is public
   with no `LICENSE` file. Under GitHub's terms a public repo without a license grants no
   rights to anyone — so it is neither usefully open nor properly protected, and the
   Balfour Beatty attribution on a personally owned repository is a claim worth checking
   before it is published further. **This needs an owner decision**, so no license file has
   been added. Options: (a) add a real open-source license and drop the proprietary
   language, (b) keep it proprietary and make the repository private, or (c) keep it public
   with an explicit "all rights reserved, source-available for review" notice.
10. **Broaden test coverage.** The financial, equipment, and reporting blueprints have
    none. Tenant-isolation tests in particular should cover every blueprint, not just the
    two now tested.

## 6. Positioning

The honest one-line description of what this should be:

> **Open scheduling infrastructure for construction: a correct CPM engine, DCMA schedule
> quality scoring, and three planning methodologies against one data model — with AI layered
> on top of computed facts rather than in place of them.**

Not "enterprise platform". Not a Procore competitor. A trustworthy engine that other
things can be built on, differentiated by treating schedule quality as a first-class
product rather than an assumption.

---

## Sources

- [AI Construction Scheduling Software: 6 Tools Ranked (2026)](https://aibuildingtools.com/blog/ai-construction-scheduling)
- [ALICE Technologies](https://www.alicetechnologies.com/home)
- [What is the DCMA 14-point schedule assessment? — Plan Academy](https://www.planacademy.com/dcma-14-point-schedule-assessment/)
- [The DCMA 14 Checks: Schedule Quality Assessment — SmartPM](https://smartpm.com/blog/dcma-14-checks)
- [DCMA 14-Point Schedule Assessment — Ron Winter, PSP (PDF)](https://www.ronwinterconsulting.com/DCMA_14-Point_Assessment.pdf)
- [PyP6Xer — Primavera XER parser for Python](https://pypi.org/project/PyP6Xer/)
- [Best AI for Construction Scheduling & Primavera P6 in 2026](https://www.nomic.ai/compare/best-ai-for-construction-scheduling)
