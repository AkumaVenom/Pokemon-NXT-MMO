# Autonomous Trainer Performance Hardening — Test Report

Release: **0.6.4-alpha · Autonomous Trainer Performance Hardening**  
Validation date: **2026-09-16**  
Database schema: **3 (unchanged)**

## Scope

This report validates the source-level fix for the long-uptime autonomous-trainer stalls reported with the normal 2,000-bot world. The implementation keeps the existing gameplay population, schedules, wild battles, captures, progression, travel, ranked simulation, AI Activity, rivalry data and shared-world presentation. The optimization targets redundant MySQL reads, transaction/commit amplification and repeated activity-retention work.

## Performance architecture regressions

`Tests/test_autonomous_performance.py` contains five explicit guards:

1. normal snapshot refresh performs **zero** full-population database reads while explicit `force=True` reconciliation remains available;
2. off-screen field simulation commits a due batch once and is forbidden from reloading the complete population;
3. competitive simulation uses one recent-opponent cohort read plus one batched commit, while legacy due/actor/candidate full-JSON reads are forbidden on the live scheduler path;
4. multiple visible field outcomes in one world tick share one transaction; and
5. the 45-day `ai_activity` retention delete is throttled to at most once per hour rather than running for every bot activity write.

The production code also restores only the touched bot rows from durable storage if a batched field write fails. That exception-only recovery path does not reintroduce population-wide reads.

## Automated validation completed

### Python syntax / static autonomous check

Commands:

```text
python -m compileall -q Server Build Tools Tests
python Tests/check_autonomous_trainers.py
```

Result: **PASS**. The static autonomous-trainer regression check printed `autonomous trainer overworld regression checks passed`.

### Autonomous + persistence/startup focused suite

Command:

```text
python -m unittest Tests.test_autonomous_performance Tests.test_autonomous_world_life Tests.test_autonomous_evolution Tests.test_sqlite_lifecycle Tests.test_world_lease Tests.test_async_tasks Tests.test_server_startup -v
```

Result: **43 tests passed, 0 failed** in **20.966 s**.

This covers the new performance contracts plus existing autonomous world life, travel, captures, persistence, party identity, level evolution, SQLite transaction lifetime, lease fencing, asynchronous transaction behavior and world startup/recovery behavior.

### Admin/release/build-source suite

Command:

```text
python -m unittest Tests.test_admin_console Tests.test_build_tools -v
```

Result: **86 tests passed, 0 failed** in **5.422 s**.

This includes release-version alignment, Windows launcher line-ending checks, schema-upgrade/lease protections and source-selection/build-manifest behavior.

### Browser/client Node regression suite

Command:

```text
node --test Tests/check_registration.mjs Tests/check_renderer_replication.mjs Tests/check_adventure_ui.mjs Tests/check_learnsets.mjs Tests/check_battle_fx.mjs Tests/check_varieties.mjs
```

Result: **103 tests passed, 0 failed**.

### Native launcher Go tests

Commands:

```text
cd Client/launcher && go test ./...
cd Server/launcher && go test ./...
```

Result: **PASS** for both launcher modules.

### Content republish

Command:

```text
python Tools/repack_content.py --root .
```

Result: **PASS**. Published pack `49cc4bbf1a14c45c0bea0be6` containing **959 maps, 877 catalog entries, 14,807 PNG assets and 2,366 verified audio clips**. Runtime/client release metadata now reports **0.6.4-alpha**.

## Full Python discovery note

A complete `python -m unittest discover -s Tests -p 'test_*.py' -v` run was also attempted. The execution environment stopped the command at its **240-second tool timeout** while the suite was still progressing; **67 tests had completed successfully and no failure had been reported among those completed tests**. Because that run did not reach the suite summary, it is not claimed as a full-suite pass. The code paths changed by this release are covered by the completed focused suites above.

## MySQL / Windows soak boundary

No source-only automated test can honestly reproduce the exact Windows Task Manager disk graph, InnoDB cache history, storage device behavior and 30+ minute production workload shown in the reported environment. The source regression suite therefore verifies the causal architecture directly: routine autonomous work no longer performs repeated 2,000-row JSON reloads, competitive fan-out full-state queries, per-bot field commits or per-action retention deletes.

Before declaring the deployment hardware-accepted, run the documented soak test with the normal **2,000 trainer** configuration and existing database. Verify bot movement remains continuous beyond the old failure window, `mysqld` no longer exhibits the previous autonomous I/O spike pattern, AI Activity still advances, off-screen captures/levels continue, ranked results persist, and a world restart retains bot progress.

## Acceptance status

**Source regression status: PASS.**  
**Deployment-specific Windows/MySQL long-uptime soak: required after install, because it depends on the target host and existing database.**
