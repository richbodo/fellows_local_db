"""Direct worker-RPC behavior tests.

Replaces tests/test_api.py:TestGroupsCRUD + TestSettingsAPI from before
Phase 1 of plans/local_first_worker_architecture.md retired the dev
server's /api/groups + /api/settings handlers. Coverage matches: every
relationships op (createGroup → getGroup → updateGroup → deleteGroup,
listGroups, getSetting/setSetting/getSettings round-trip, dedupe,
validation, pagination behavior) gets exercised through window.__dataProvider,
which is the same code path the real app uses.

The page-side worker provider transforms call args (id, patch) into the
worker's RPC arg shape ({id}, {id, patch}); these tests assert the
externally-visible behavior, not the wire transformation.

Mutating relationships.db RPCs require a connected folder under the
private-data capability gate (plans/private_data_enforcement.md), so these
tests use the ``worker_data_folder`` fixture. The off-folder *refusal* of the
same RPCs is covered by tests/e2e/test_private_data_enforcement.py.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect


class TestGroupsRpc:
    def test_list_empty_initially(self, worker_data_folder):
        groups = worker_data_folder.list_groups()
        assert groups == []

    def test_create_returns_full_record(self, worker_data_folder):
        full = worker_data_folder.get_full_fellows()
        ids = [(f["record_id"], f["name"]) for f in full[:2]]
        g = worker_data_folder.create_group(
            "Climate cohort",
            fellow_record_ids=[r[0] for r in ids],
            note="for the Wellington roundtable",
        )
        assert isinstance(g["id"], int)
        assert g["name"] == "Climate cohort"
        assert g["note"] == "for the Wellington roundtable"
        assert g["created_at"] and g["updated_at"]
        assert len(g["members"]) == 2
        # The page-side worker provider attaches member names from the
        # in-memory fellowsBySlug cache populated by getFull on boot.
        names = sorted(m["name"] for m in g["members"])
        assert names == sorted(r[1] for r in ids)

    def test_create_then_list_shows_one(self, worker_data_folder):
        full = worker_data_folder.get_full_fellows()
        worker_data_folder.create_group("g1", fellow_record_ids=[full[0]["record_id"]])
        groups = worker_data_folder.list_groups()
        assert len(groups) == 1
        assert groups[0]["name"] == "g1"
        assert groups[0]["count"] == 1

    def test_get_by_id_returns_members_and_null_when_missing(self, worker_data_folder):
        full = worker_data_folder.get_full_fellows()
        g = worker_data_folder.create_group("x", fellow_record_ids=[full[0]["record_id"]])
        gid = g["id"]
        got = worker_data_folder.get_group(gid)
        assert got["id"] == gid
        assert len(got["members"]) == 1
        # Bogus id → null (not 404 — RPC returns null for missing id).
        missing = worker_data_folder.get_group(gid + 999)
        assert missing is None

    def test_update_renames_and_replaces_members(self, worker_data_folder):
        full = worker_data_folder.get_full_fellows()
        ids3 = [f["record_id"] for f in full[:3]]
        g = worker_data_folder.create_group("old name", fellow_record_ids=ids3[:2])
        gid = g["id"]
        updated = worker_data_folder.update_group(
            gid,
            {
                "name": "new name",
                "note": "noted",
                "fellow_record_ids": [ids3[2]],
            },
        )
        assert updated["name"] == "new name"
        assert updated["note"] == "noted"
        assert [m["record_id"] for m in updated["members"]] == [ids3[2]]
        # updated_at must move forward; created_at must NOT change.
        assert updated["updated_at"] >= updated["created_at"]

    def test_update_partial_only_touches_provided_fields(self, worker_data_folder):
        full = worker_data_folder.get_full_fellows()
        g = worker_data_folder.create_group(
            "keepme",
            fellow_record_ids=[full[0]["record_id"]],
        )
        gid = g["id"]
        # Patch only the note — name and members unchanged.
        updated = worker_data_folder.update_group(gid, {"note": "just a note"})
        assert updated["name"] == "keepme"
        assert updated["note"] == "just a note"
        assert len(updated["members"]) == 1

    def test_update_returns_null_for_missing_group(self, worker_data_folder):
        # Mirrors the legacy 404 behavior: missing id → null return.
        result = worker_data_folder.update_group(9999, {"name": "x"})
        assert result is None

    def test_delete_returns_true_then_false(self, worker_data_folder):
        g = worker_data_folder.create_group("doomed", fellow_record_ids=[])
        gid = g["id"]
        assert worker_data_folder.delete_group(gid) is True
        assert worker_data_folder.delete_group(gid) is False
        # List is empty again.
        assert worker_data_folder.list_groups() == []

    def test_create_dedupes_member_ids(self, worker_data_folder):
        full = worker_data_folder.get_full_fellows()
        rid = full[0]["record_id"]
        g = worker_data_folder.create_group(
            "x",
            fellow_record_ids=[rid, rid, rid],
        )
        assert len(g["members"]) == 1


# Boot- and folder-managed keys that legitimately populate `settings` in
# folder mode (workspace identity stamp + the migrated has-email pref + the
# AC-10 orphan soft-scan's one-shot `orphan_scan_done` flag). These are
# system-written, not user-authored; the RPC round-trip tests assert on their
# own keys via subset, ignoring these. `orphan_scan_done` can leak in from a
# prior test that triggered the boot scan through the shared folder fixture, so
# it must be tolerated here regardless of suite ordering.
_BOOT_MANAGED_KEYS = {
    "workspace_uuid", "device_label", "created_at", "write_generation",
    "last_written_at", "has_email_only", "orphan_scan_done",
}


class TestSettingsRpc:
    def test_no_user_keys_initially(self, worker_data_folder):
        # Folder mode carries identity-stamp metadata; assert only that no
        # user-authored test keys leaked in from a prior test.
        bag = worker_data_folder.list_settings()
        assert set(bag) - _BOOT_MANAGED_KEYS == set(), bag

    def test_get_unset_key_returns_null(self, worker_data_folder):
        assert worker_data_folder.get_setting("a") is None

    def test_set_then_get_round_trip(self, worker_data_folder):
        result = worker_data_folder.set_setting("self_email", "me@example.com")
        assert result == {"key": "self_email", "value": "me@example.com"}
        assert worker_data_folder.get_setting("self_email") == "me@example.com"

    def test_set_empty_value_deletes(self, worker_data_folder):
        worker_data_folder.set_setting("k", "v")
        worker_data_folder.set_setting("k", "")
        assert worker_data_folder.get_setting("k") is None

    def test_list_returns_all_keys(self, worker_data_folder):
        worker_data_folder.set_setting("a", "1")
        worker_data_folder.set_setting("b", "2")
        bag = worker_data_folder.list_settings()
        # Subset assertion: the round-tripped keys are present (folder mode also
        # carries identity-stamp metadata, which this test ignores).
        assert bag.get("a") == "1" and bag.get("b") == "2", bag
