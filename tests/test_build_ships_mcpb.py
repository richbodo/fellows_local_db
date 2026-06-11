"""Regression guard: the deploy/ship build path must produce the Claude
Desktop ``.mcpb`` bundles and ship them where the server serves them.

This locks the fix for the ship bug where ``just build`` ran only
``build/build_pwa.py`` (which ``rmtree``'s ``deploy/dist/``), the ``.mcpb``
bundles were never built into ``deploy/dist/mcpb/``, and the rsync
``--delete`` then removed any stale copies from prod — surfacing to fellows
as three "File wasn't available on site" download failures under
*Set up Claude Desktop integration*.

These are cheap, deterministic, Node-free checks (justfile / ansible /
source-text parsing) at the altitude that would have caught the bug — not a
full Node build of the bundles.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JUSTFILE = REPO_ROOT / "justfile"
DEPLOY_SERVER = REPO_ROOT / "deploy" / "server.py"
FELLOWS_APP_TASKS = (
    REPO_ROOT / "ansible" / "roles" / "fellows_app" / "tasks" / "main.yml"
)


def _recipe_body(name: str) -> str:
    """Return the indented body of a justfile recipe ``name:`` (no args)."""
    lines = JUSTFILE.read_text(encoding="utf-8").splitlines()
    i, n = 0, len(lines)
    while i < n and lines[i].rstrip() != f"{name}:":
        i += 1
    assert i < n, f"no `{name}:` recipe found in justfile"
    i += 1
    body: list[str] = []
    while i < n:
        line = lines[i]
        if line.strip() == "" or line[:1] in (" ", "\t"):
            body.append(line)
        else:
            break  # first column-0 non-blank line ends the recipe
        i += 1
    return "\n".join(body)


def _recipe_header_deps(name: str) -> str:
    """Return the dependency list after ``name:`` on the recipe header line."""
    pat = re.compile(rf"^{re.escape(name)}:\s*(.*)$", re.MULTILINE)
    m = pat.search(JUSTFILE.read_text(encoding="utf-8"))
    assert m, f"no `{name}:` recipe header found in justfile"
    return m.group(1).strip()


class TestBuildRecipeProducesBundles:
    def test_build_recipe_runs_build_mcpb(self):
        body = _recipe_body("build")
        assert "build/build_mcpb.py" in body, (
            "the `build` recipe must run build/build_mcpb.py so deploy/ship "
            "produce the .mcpb bundles (else the /mcpb/ routes 404)"
        )

    def test_build_recipe_runs_pwa_before_mcpb(self):
        # build_pwa.py rmtree's deploy/dist/; build-mcpb MUST run after it or
        # the bundles it produces are wiped before they ship.
        body = _recipe_body("build")
        assert "build/build_pwa.py" in body, "the `build` recipe must run build_pwa.py"
        assert body.index("build/build_pwa.py") < body.index("build/build_mcpb.py"), (
            "build_pwa.py (which wipes deploy/dist/) must run BEFORE build_mcpb.py"
        )


class TestDeployPathInvokesBuild:
    def test_deploy_depends_on_build(self):
        deps = _recipe_header_deps("deploy")
        assert re.search(r"\bbuild\b", deps), f"`deploy` must depend on `build`: {deps!r}"

    def test_ship_reaches_deploy(self):
        deps = _recipe_header_deps("ship")
        assert "deploy" in deps.split(), f"`ship` must run `deploy`: {deps!r}"


class TestProducerServerParity:
    def test_build_mcpb_outputs_where_server_serves(self):
        from build.build_mcpb import OUTPUT_DIR

        rel = OUTPUT_DIR.resolve().relative_to(REPO_ROOT.resolve())
        assert rel == Path("deploy/dist/mcpb"), (
            f"build_mcpb writes to {rel}, but deploy/server.py serves from "
            "deploy/dist/mcpb/ — producer and server must agree"
        )

    def test_server_whitelist_matches_available_bundles(self):
        from build.build_mcpb import available_bundles

        text = DEPLOY_SERVER.read_text(encoding="utf-8")
        m = re.search(r"MCPB_NAMES\s*=\s*frozenset\(\{([^}]*)\}\)", text)
        assert m, "could not find MCPB_NAMES in deploy/server.py"
        names = set(re.findall(r'"([^"]+)"', m.group(1)))
        assert names == set(available_bundles()), (
            "deploy/server.py MCPB_NAMES must match the bundles build_mcpb "
            f"produces; server={sorted(names)} producer={available_bundles()}"
        )


class TestDeployVerifiesBundles:
    """The deploy must fail loudly if the bundles didn't land — the /mcpb/
    routes are auth-gated (403 before the file-existence check), so an
    HTTPS smoke can't catch a missing bundle. The on-disk post-rsync check
    in the fellows_app role is the tripwire."""

    def test_ansible_verifies_mcpb_bundles_present(self):
        text = FELLOWS_APP_TASKS.read_text(encoding="utf-8")
        assert "deploy/dist/mcpb/{{ item }}.mcpb" in text, (
            "the fellows_app role must stat the deployed .mcpb bundles post-rsync"
        )
        for name in ("comms", "shared_data_ops", "private_data_ops"):
            assert name in text, f"bundle {name} not verified in the deploy role"
        assert "ansible.builtin.fail" in text, (
            "a missing .mcpb bundle must fail the deploy loudly"
        )
