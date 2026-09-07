# NIGHTSHIFT · every scenario in this project, as one command each.
#
#     just                  the list
#     just scenarios        what can be broken, and which signal notices
#     just scenario-surge   one whole incident, end to end
#
# Everything here is a thin wrapper over `python cli.py ...`. Nothing is hidden:
# a class can see that the shortcut is a shortcut and not a different system.

PY := "./.venv/bin/python"
COMPOSE := "docker compose -f platform/docker-compose.yml"

# A leading dash on a line means "carry on even if this exits non-zero".
# `cli.py signals` exits 1 when something has breached, which is correct for CI
# and would otherwise stop a recipe whose whole purpose is to break something.

# every recipe, in order
default:
    @just --list --unsorted


# ═══════════════════════════════════════════════════════════════════════════
# the estate
# ═══════════════════════════════════════════════════════════════════════════

# start postgres, mongo, kafka, minio, airflow and both services
up:
    {{COMPOSE}} up -d
    @echo ""
    @echo "  airflow           http://localhost:8080"
    @echo "  pgweb             http://localhost:8081"
    @echo "  mongo express     http://localhost:8082"
    @echo "  redpanda console  http://localhost:8083"
    @echo "  signal api        http://localhost:8091/signals"
    @echo "  agent service     http://localhost:8092/health"
    @echo "  signal board      just board"

# stop everything, keeping the data
down:
    {{COMPOSE}} stop

# what is running, and is it healthy
ps:
    @{{COMPOSE}} ps --format '{{{{.Service}}}}\t{{{{.Status}}}}'

# is everything actually answering, not just running
health: ps
    @echo ""
    @echo -n "  signal api  " && curl -s localhost:8091/health || echo "not answering"
    @echo -n "  agent       " && curl -s localhost:8092/health || echo "not answering"
    @echo ""

# fill the six source systems with a month of generated trading
seed:
    {{PY}} -m seed

# wipe the sources and generate them again, about three minutes
reseed:
    {{PY}} -m seed --force


# ═══════════════════════════════════════════════════════════════════════════
# the pipelines
# ═══════════════════════════════════════════════════════════════════════════

# back to empty: warehouse, incidents, artifacts, agent branches, and the break
reset:
    {{PY}} cli.py reset

# forget the incidents and artifacts, keep the warehouse. Between demos
reset-oncall:
    {{PY}} cli.py reset --oncall

# run all eight pipelines in dependency order
run:
    {{PY}} cli.py run all

# run one, e.g. just run-one p3_bronze_driver_app
run-one name:
    {{PY}} cli.py run {{name}}

# what is in the warehouse right now
status:
    {{PY}} cli.py status

# reset and rebuild. This is how you start a lesson
rebuild: reset run status


# ═══════════════════════════════════════════════════════════════════════════
# the signal service
# ═══════════════════════════════════════════════════════════════════════════

# the thirteen KPI definitions, and who owns each
kpis:
    {{PY}} cli.py kpis

# evaluate all thirteen right now
signals:
    -{{PY}} cli.py signals

# the seventeen things that must never be false
invariants:
    -{{PY}} cli.py invariants

# what has breached, grouped into incidents
incidents:
    {{PY}} cli.py incidents

# the board in a browser, on http://localhost:8099
board:
    {{PY}} cli.py dashboard

# the clock, in the foreground, evaluating every 60 seconds
watch:
    {{PY}} cli.py watch

# one cycle of the clock, so you can see it decide without waiting
tick:
    {{PY}} -m signal_service.scheduler --once

# the signal service API, in the foreground, on :8091
api:
    {{PY}} cli.py api


# ═══════════════════════════════════════════════════════════════════════════
# the agent system
# ═══════════════════════════════════════════════════════════════════════════

# the agent service, in the foreground, on :8092
agent:
    {{PY}} cli.py agent

# five agents against one signal, every step printed as it happens
investigate kpi="surge_coverage_pct":
    {{PY}} cli.py investigate {{kpi}}

# evaluate everything red, group it into incidents, and work the worst one
investigate-board:
    {{PY}} cli.py investigate board

# the same, without printing what each tool returned
investigate-quiet kpi="surge_coverage_pct":
    {{PY}} cli.py investigate {{kpi}} --quiet


# ═══════════════════════════════════════════════════════════════════════════
# breaking things on purpose · three breaks, three different incidents
# ═══════════════════════════════════════════════════════════════════════════

# what can be broken, which signal notices, and who owns it
scenarios:
    {{PY}} break_it.py --list

# put every break back and rebuild
fix:
    {{PY}} break_it.py --fix
    {{PY}} cli.py run all
    -{{PY}} cli.py signals

# 1 · a mobile release moves a field. pricing's signal
break-surge:
    {{PY}} break_it.py surge
    {{PY}} cli.py run p3_bronze_driver_app
    {{PY}} cli.py run p7_silver_rides
    {{PY}} cli.py run p8_gold_daily
    -{{PY}} cli.py signals

# 2 · a new zone opens and our dimension is stale. operations' signal
break-zones:
    {{PY}} break_it.py zones
    {{PY}} cli.py run p1_bronze_trips
    {{PY}} cli.py run p7_silver_rides
    {{PY}} cli.py run p8_gold_daily
    -{{PY}} cli.py signals

# 3 · the aggregate did not rebuild. data-platform's, and five signals at once
break-stale:
    {{PY}} break_it.py stale
    -{{PY}} cli.py signals


# ═══════════════════════════════════════════════════════════════════════════
# the scenarios · one command each, end to end, for a class
# ═══════════════════════════════════════════════════════════════════════════
#
# Each one resets, breaks something different, and runs the agents on it. They
# produce three genuinely different Confluence pages, because the evidence is
# genuinely different: a document store, a stale dimension, and a job that did
# not run. Nothing about the investigation is scripted.

# 1 · pricing · a field moved. Seven steps, ending in a pull request and a page
scenario-surge: rebuild reset-oncall
    {{PY}} cli.py scenario surge

# the same, stopping at the handover so you can talk before the agents run
scenario-surge-pause: rebuild reset-oncall
    {{PY}} cli.py scenario surge --no-agent

# 2 · operations · a stale dimension. The code is right, the DATA is late
scenario-zones: rebuild reset-oncall
    {{PY}} cli.py scenario zones

# 3 · data-platform · a job did not run. FIVE signals, grouped into ONE incident
scenario-stale: rebuild reset-oncall
    {{PY}} cli.py scenario stale

# all three, back to back. Three incidents, three different pages
scenario-all: scenario-surge scenario-zones scenario-stale
    @echo ""
    @echo "  three incidents, three pages. Put it back with:  just fix"

# nobody calls the agents: the clock finds it and rings the doorbell itself
scenario-unattended: rebuild reset-oncall break-surge
    @echo ""
    @echo "  ══ nobody calls the agents. The clock rings the doorbell ════"
    {{PY}} -m signal_service.scheduler --once
    @echo ""
    @echo "  the agent service is working it on a background thread..."
    @sleep 90
    {{PY}} cli.py incidents


# ═══════════════════════════════════════════════════════════════════════════
# checks
# ═══════════════════════════════════════════════════════════════════════════

# the whole test suite, including the ones that try to cross every boundary
test:
    {{PY}} -m pytest -q

# only the boundary tests, the ones worth showing a room
test-guards:
    {{PY}} -m pytest tests/test_guards.py -v --no-header
