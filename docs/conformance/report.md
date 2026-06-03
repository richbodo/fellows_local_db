# Conformance Report

_Generated 2026-06-03T23:53:10Z for `e0d9e7b`. Source of truth: `docs/Architecture.md`._

> Deterministic serialization of `scripts/conformance_lib.py` — the same logic the pytest gate runs, **not** the LLM evaluate flow. `live` means a real, non-deferred assertion exists; pass/fail is enforced by the suite (`just test`). See `plans/conformance_report_and_gate.md`.

## Headline

- **Deferrals: 1 / cap 3** ✅
- **Conformant rows:** 29 of 32
- **Findings:** 0 ✅

## Deferrals (strict-xfail)

| Test | Tracking | Issue state |
|---|---|---|
| `tests/e2e/test_private_data_enforcement.py::test_off_folder_settings_are_empty` | #248 | OPEN |

## Findings

_None. Every `conformant` row cites live, non-deferred evidence; every deferral is anchored and under cap._

## Attestation rows

| Row | Status | Evidence (cited test → static state) |
|---|---|---|
| AC-1 (two-store ownership split) | conformant | `tests/test_relationships.py::test_attach_fellows_readonly_allows_select` → live; `tests/test_database.py` → live |
| AC-4 (versioned cross-boundary handshake) | conformant | `tests/e2e/test_version_handshake.py::test_version_skew_refuses_mutations_but_allows_reads` → live; `tests/e2e/test_worker_rpc.py` → live |
| AC-6 (always-reachable diagnostic escape) | conformant | `tests/e2e/test_email_gate.py` → live; `tests/e2e/test_reset_everything.py` → live; `tests/e2e/test_clear_app_cache.py` → live |
| AC-7 (self-service field-debug substrate) | conformant | `tests/e2e/test_diagnostics_panel.py` → live; `test_boot_watchdog.py` → live; `test_boot_error_panel.py` → live; `test_bug_report.py` → live; `test_boot_beacon.py` → live |
| AC-9 (auto-backup of private data) | conformant | `tests/e2e/test_user_folder_storage.py::test_snapshot_lands_in_folder_when_folder_mode_active` → live; `tests/e2e/test_settings.py` → live |
| AC-10 (opt-in non-destructive re-imports) | conformant | `tests/e2e/test_directory_data_update_flow.py::test_apply_with_group_impact_shows_dialog_and_can_cancel` → live; `test_orphan_soft_scan.py` → live; `test_versioned_fellows_db.py` → live |
| AC-11 (concurrent-access detection) | conformant | `tests/e2e/test_user_folder_storage.py::TestPhase2WriteLock` → live; `test_worker_spawn_failure.py` → live |
| AC-15 (build label tied to source revision) | conformant | `tests/test_build_pwa.py` → live; `tests/e2e/test_update_check.py` → live; `test_bug_report.py` → live; `test_boot_beacon.py` → live |
| AC-16 (user-driven transport selection) | partial-conformance (conformant to the `mailto-only` axis pick; richer transports planned) | `tests/e2e/test_groups_export.py` → live; `tests/test_comms.py` → live |
| AC-17 (mirrored data is sourced) | conformant | `tests/test_database.py` → live; `build/diff_fellows_db.py` → live |
| AC-18 (transports cannot read message contents) | conformant | `tests/test_comms.py` → live; `tests/test_private_data_ops.py` → live |
| AC-19 (user-visible payload before send) | conformant | `tests/e2e/test_groups_export.py` → live; `tests/e2e/test_groups_compose.py` → live |
| AC-PRM-A (LLM calls over user data are transports) | partial-conformance (cloud opt-in via per-install consent; per-call prompt visibility is the cloud client's UI, not the workspace's) | `tests/e2e/test_pna_exception_mode.py` → live; `test_mcpb_settings.py` → live |
| AC-PRM-D (re-ingestion is user-initiated) | conformant | `tests/e2e/test_directory_data_update_flow.py` → live; `test_versioned_fellows_db.py::test_install_only_does_not_refetch_on_sha_mismatch` → live |
| AC-MCP-A (cloud AI clients require consent for Private DB) | partial-conformance (per-session/per-install opt-in via `EX-CLOUD-LLM`; not per-call server-side gating) | `tests/e2e/test_pna_exception_mode.py` → live; `tests/test_private_data_ops.py` → live |
| AC-MCP-B (MCP Communications stages; workspace launches) | conformant | `tests/test_comms.py::test_stage_email_basic_to` → live |
| AC-2 (no SaaS surface) | conformant | `tests/test_deploy_auth_round_trip.py::test_directory_api_is_403_without_session` → live; `test_deploy_sqlite_api.py` → live; `test_deploy_mcpb_routes.py` → live |
| AC-3 (single OPFS owner) | conformant | `tests/e2e/test_worker_rpc.py` → live; `test_worker_cold_start.py` → live; `test_local_first_boot.py` → live |
| AC-5 (stale session never locks users out of cache) | conformant | `tests/e2e/test_offline_only_mode.py::test_401_with_cached_data_shows_directory_from_cache` → live; `test_search_offline_fallback.py` → live; `test_local_first_boot.py` → live |
| AC-8 (anti-enumeration + abuse-bounded analytics) | conformant | `tests/test_magic_link_auth.py` → live; `test_deploy_auth_round_trip.py` → live; `test_deploy_client_errors.py` → live; `test_client_error_sanitizer.py` → live |
| AC-12 (capability detection inside worker) | conformant | `tests/e2e/test_unsupported_browser.py::test_no_sah_falls_back_to_api_idb_provider` → live; `test_worker_cold_start.py` → live |
| AC-13 (COOP/COEP required) | conformant | `tests/test_api.py::TestSecurityHeaders` → live |
| AC-14 (SW never owns SQLite) | conformant | `tests/e2e/test_sw_post_caching.py` → live; `test_image_cache_no_bust.py` → live |
| EX-CLOUD-LLM | conformant for EX-H1–H6 and EX-H8; EX-H7 (consent-to-human) surfaced best-effort via MCP `instructions` | `tests/e2e/test_pna_exception_mode.py` → live; `tests/e2e/test_mcpb_settings.py` → live; `tests/test_private_data_ops.py::test_instructions_carry_cloud_llm_propagation_notice` → live; `tests/test_shared_data_ops.py::test_instructions_carry_cloud_llm_propagation_notice` → live |
| CST-PWA-PRIVATE-SNAPSHOT | **conformant** (as a *handling*): the capability reduction is complete — UI/route reduction **plus** data-layer refusal of off-folder durable writes (worker-side load-bearing + page-side defense-in-depth, PR #244 `d2706a9`; [`../plans/private_data_enforcement.md`](../plans/private_data_enforcement.md)). The negative invariant is now a hard guard, not a strict-xfail. Frontier stays **Open**: this is honest handling, not a durable cross-platform store. | `tests/e2e/test_browse_only_durability.py::test_gate_defaults_to_browse_only_without_folder` → live; `tests/e2e/test_private_data_enforcement.py::test_browse_only_refuses_create_group` → live; `tests/e2e/test_private_data_enforcement.py::test_no_durable_private_write_when_browse_only` → live; `tests/e2e/test_private_data_enforcement.py::test_folder_attached_allows_create_group` → live |
| CST-PWA-SANDBOX-SEALED | conformant | `tests/e2e/test_sandbox_sealed_mcp.py::test_no_folder_resident_private_store_off_folder` → live; `tests/e2e/test_sandbox_sealed_mcp.py::test_mcp_setup_warns_no_folder_off_folder` → live; `tests/e2e/test_sandbox_sealed_mcp.py::test_mcp_folder_warning_hidden_when_folder_attached` → live |
| CST-PWA-STORAGE-EVICTABLE | **conformant**: the two prefs (`has_email_only` / `self_email`) are localStorage-only off-folder — the boot reconciles no longer write `settings` to OPFS in browse-only mode (PR #244 `d2706a9`; [`../plans/private_data_enforcement.md`](../plans/private_data_enforcement.md)). The "Avoided" claim now holds. | `tests/e2e/test_private_data_enforcement.py::test_prefs_stay_localstorage_only_off_folder` → live |
| CST-PWA-NO-SYNC | conformant: canonical-copy disambiguation shipped; sync explicitly out of scope | `tests/e2e/test_user_folder_storage.py` → live; `tests/e2e/test_folder_probe.py` → live |
| CST-PWA-DURABLE-SQL-ARCH | conformant by architecture | _declared review kind_ |
| CST-PWA-SINGLE-OWNER | conformant | `tests/e2e/test_user_folder_storage.py::TestPhase2WriteLock` → live |
| CST-PWA-NO-BACKGROUND | conformant: opportunistic-only, honestly framed | `tests/e2e/test_user_folder_storage.py` → live |
| CST-PWA-SERVER-FLOOR | conformant by bounding | _declared review kind_ |

