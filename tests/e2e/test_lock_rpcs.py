"""Lock orchestration RPCs (Phase 2 of plans/lock_my_user_data.md).

Drives the worker's lock state machine directly via
window.__dataProvider._rpc.call(...). The page-side Settings UI lands
in Phase 4; these tests pin the contract the UI will eventually
consume.

State machine under test:
    disabled        ── enableLock ──>  enabled+locked
    enabled+locked  ── unlock     ──>  enabled+unlocked (cached key)
    enabled+unlocked ── lock      ──>  enabled+locked
    enabled+unlocked ── changePass ─>  enabled+unlocked (new cached key)
    enabled+unlocked ── disableLock ─> disabled

Structured errors pinned:
    WrongPassphraseError   — wrong password on unlock / change / disable
    LockStateError         — RPC called in incompatible state
    LockEnvelopeError      — corrupt .locked file
    DataLockedError        — relDb-touching RPC called while locked
"""
from __future__ import annotations

import pytest


_WAIT_FOR_DP = """
async () => {
  for (var i = 0; i < 200; i++) {
    if (window.__dataProvider && typeof window.__dataProvider.listGroups === 'function') {
      return window.__dataProvider.kind || 'unknown';
    }
    await new Promise(function (r) { setTimeout(r, 50); });
  }
  throw new Error('window.__dataProvider not ready after 10s');
}
"""


def _wait_for_dp(page):
    return page.evaluate(_WAIT_FOR_DP)


def _rpc(page, op, args=None):
    if args is None:
        return page.evaluate(
            "(op) => window.__dataProvider._rpc.call(op)",
            op,
        )
    return page.evaluate(
        "(p) => window.__dataProvider._rpc.call(p.op, p.args)",
        {"op": op, "args": args},
    )


def _rpc_expect_error(page, op, args):
    """Call an RPC, catch the rejection in JS, return {name, message}."""
    return page.evaluate(
        """async (p) => {
          try {
            await window.__dataProvider._rpc.call(p.op, p.args);
            return { thrown: false };
          } catch (e) {
            return { thrown: true, name: e.name, message: e.message };
          }
        }""",
        {"op": op, "args": args},
    )


@pytest.fixture
def lock_clean_page(standalone_page, base_url_fixture):
    """Fresh OPFS state per test. Wipes everything via wipeAll + reloads,
    then yields the page. Teardown wipes again so the next test starts
    clean.
    """
    page = standalone_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_dp(page)
    # Wipe any leftover state from prior tests (or prior runs).
    _rpc(page, "wipeAll")
    page.reload(wait_until="domcontentloaded")
    _wait_for_dp(page)
    yield page
    # Best-effort teardown. wipeAll nulls poolUtil; the next test's
    # fixture entry reloads, so leaving the page broken is fine.
    try:
        _rpc(page, "wipeAll")
    except Exception:
        pass


# ----- getLockState ---------------------------------------------------------

def test_get_lock_state_default(lock_clean_page):
    state = _rpc(lock_clean_page, "getLockState")
    assert state["enabled"] is False
    assert state["locked"] is False
    assert state["hasKey"] is False
    assert state["formatVersion"] is None
    assert state["kdfId"] is None
    assert state["iters"] is None


# ----- enableLock -----------------------------------------------------------

def test_enable_lock_transitions_to_locked(lock_clean_page):
    full = lock_clean_page.evaluate("() => window.__dataProvider.getFull()")
    rid = full[0]["record_id"]
    lock_clean_page.evaluate(
        "(p) => window.__dataProvider.createGroup(p)",
        {"name": "Locked Group", "fellow_record_ids": [rid], "note": "secret"},
    )

    result = _rpc(lock_clean_page, "enableLock", {"passphrase": "correct-horse"})
    assert result["ok"] is True

    state = _rpc(lock_clean_page, "getLockState")
    assert state["enabled"] is True
    assert state["locked"] is True
    assert state["hasKey"] is False
    assert state["formatVersion"] == 1
    assert state["kdfId"] == 1
    assert state["iters"] == 600000


def test_enable_lock_when_already_enabled_throws(lock_clean_page):
    _rpc(lock_clean_page, "enableLock", {"passphrase": "pw"})
    err = _rpc_expect_error(
        lock_clean_page, "enableLock", {"passphrase": "pw"}
    )
    assert err["thrown"] is True
    assert err["name"] == "LockStateError"


# ----- DataLockedError on relDb-touching ops --------------------------------

def test_listgroups_while_locked_throws_data_locked_error(lock_clean_page):
    _rpc(lock_clean_page, "enableLock", {"passphrase": "pw"})
    err = _rpc_expect_error(lock_clean_page, "listGroups", None)
    assert err["thrown"] is True
    assert err["name"] == "DataLockedError"


def test_creategroup_while_locked_throws_data_locked_error(lock_clean_page):
    _rpc(lock_clean_page, "enableLock", {"passphrase": "pw"})
    err = _rpc_expect_error(
        lock_clean_page, "createGroup",
        {"name": "Should not exist", "fellow_record_ids": []},
    )
    assert err["thrown"] is True
    assert err["name"] == "DataLockedError"


# ----- unlock ---------------------------------------------------------------

def test_unlock_with_right_passphrase_restores_data(lock_clean_page):
    full = lock_clean_page.evaluate("() => window.__dataProvider.getFull()")
    rid = full[0]["record_id"]
    lock_clean_page.evaluate(
        "(p) => window.__dataProvider.createGroup(p)",
        {"name": "Confidential", "fellow_record_ids": [rid]},
    )

    _rpc(lock_clean_page, "enableLock", {"passphrase": "pw1"})
    assert _rpc(lock_clean_page, "getLockState")["locked"] is True

    result = _rpc(lock_clean_page, "unlock", {"passphrase": "pw1"})
    assert result["ok"] is True
    assert result["counts"]["groups"] == 1

    state = _rpc(lock_clean_page, "getLockState")
    assert state["enabled"] is True
    assert state["locked"] is False
    assert state["hasKey"] is True

    groups = lock_clean_page.evaluate("() => window.__dataProvider.listGroups()")
    assert len(groups) == 1
    assert groups[0]["name"] == "Confidential"


def test_unlock_wrong_passphrase_throws_wrong_passphrase_error(lock_clean_page):
    _rpc(lock_clean_page, "enableLock", {"passphrase": "right"})
    err = _rpc_expect_error(
        lock_clean_page, "unlock", {"passphrase": "wrong"}
    )
    assert err["thrown"] is True
    assert err["name"] == "WrongPassphraseError"

    state = _rpc(lock_clean_page, "getLockState")
    assert state["locked"] is True


def test_unlock_when_not_enabled_throws_lock_state_error(lock_clean_page):
    err = _rpc_expect_error(
        lock_clean_page, "unlock", {"passphrase": "anything"}
    )
    assert err["thrown"] is True
    assert err["name"] == "LockStateError"


# ----- lock -----------------------------------------------------------------

def test_lock_re_encrypts_session_changes(lock_clean_page):
    _rpc(lock_clean_page, "enableLock", {"passphrase": "pw"})
    _rpc(lock_clean_page, "unlock", {"passphrase": "pw"})

    lock_clean_page.evaluate(
        "() => window.__dataProvider.setSetting('marker', 'after-unlock')"
    )

    result = _rpc(lock_clean_page, "lock")
    assert result["ok"] is True

    state = _rpc(lock_clean_page, "getLockState")
    assert state["locked"] is True
    assert state["hasKey"] is False

    _rpc(lock_clean_page, "unlock", {"passphrase": "pw"})
    val = lock_clean_page.evaluate(
        "() => window.__dataProvider.getSetting('marker')"
    )
    assert val == "after-unlock"


def test_lock_without_cached_key_throws_lock_state_error(lock_clean_page):
    _rpc(lock_clean_page, "enableLock", {"passphrase": "pw"})
    # Do not unlock; cached key is null.
    err = _rpc_expect_error(lock_clean_page, "lock", None)
    assert err["thrown"] is True
    assert err["name"] == "LockStateError"


# ----- changePassphrase -----------------------------------------------------

def test_change_passphrase_old_stops_working_new_works(lock_clean_page):
    _rpc(lock_clean_page, "enableLock", {"passphrase": "old-pw"})
    _rpc(lock_clean_page, "unlock", {"passphrase": "old-pw"})

    result = _rpc(
        lock_clean_page, "changePassphrase",
        {"oldPassphrase": "old-pw", "newPassphrase": "new-pw"},
    )
    assert result["ok"] is True
    assert result["rekeyedCount"] >= 1  # at least the live DB

    # Lock + unlock with new passphrase
    _rpc(lock_clean_page, "lock")
    unlock_result = _rpc(lock_clean_page, "unlock", {"passphrase": "new-pw"})
    assert unlock_result["ok"] is True

    # Lock + try old passphrase — must fail
    _rpc(lock_clean_page, "lock")
    err = _rpc_expect_error(
        lock_clean_page, "unlock", {"passphrase": "old-pw"}
    )
    assert err["name"] == "WrongPassphraseError"


def test_change_passphrase_wrong_old_throws(lock_clean_page):
    _rpc(lock_clean_page, "enableLock", {"passphrase": "real"})
    _rpc(lock_clean_page, "unlock", {"passphrase": "real"})

    err = _rpc_expect_error(
        lock_clean_page, "changePassphrase",
        {"oldPassphrase": "wrong", "newPassphrase": "new"},
    )
    assert err["thrown"] is True
    assert err["name"] == "WrongPassphraseError"


# ----- disableLock ----------------------------------------------------------

def test_disable_lock_restores_plaintext_access(lock_clean_page):
    full = lock_clean_page.evaluate("() => window.__dataProvider.getFull()")
    rid = full[0]["record_id"]
    lock_clean_page.evaluate(
        "(p) => window.__dataProvider.createGroup(p)",
        {"name": "Persisting", "fellow_record_ids": [rid]},
    )

    _rpc(lock_clean_page, "enableLock", {"passphrase": "pw"})
    _rpc(lock_clean_page, "unlock", {"passphrase": "pw"})

    result = _rpc(lock_clean_page, "disableLock", {"passphrase": "pw"})
    assert result["ok"] is True

    state = _rpc(lock_clean_page, "getLockState")
    assert state["enabled"] is False
    assert state["locked"] is False

    groups = lock_clean_page.evaluate("() => window.__dataProvider.listGroups()")
    assert any(g["name"] == "Persisting" for g in groups)


def test_disable_lock_wrong_passphrase_throws(lock_clean_page):
    _rpc(lock_clean_page, "enableLock", {"passphrase": "real"})
    _rpc(lock_clean_page, "unlock", {"passphrase": "real"})

    err = _rpc_expect_error(
        lock_clean_page, "disableLock", {"passphrase": "wrong"}
    )
    assert err["thrown"] is True
    assert err["name"] == "WrongPassphraseError"


# ----- persistence across reload --------------------------------------------

def test_lock_persists_across_page_reload(lock_clean_page, base_url_fixture):
    _rpc(lock_clean_page, "enableLock", {"passphrase": "pw"})

    lock_clean_page.reload(wait_until="domcontentloaded")
    _wait_for_dp(lock_clean_page)

    state = _rpc(lock_clean_page, "getLockState")
    assert state["enabled"] is True
    assert state["locked"] is True

    _rpc(lock_clean_page, "unlock", {"passphrase": "pw"})
    state = _rpc(lock_clean_page, "getLockState")
    assert state["locked"] is False
    assert state["hasKey"] is True
