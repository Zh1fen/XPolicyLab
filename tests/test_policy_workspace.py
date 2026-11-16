"""Exercise sparse checkout recovery and protection against hiding local work in disposable repos."""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PolicyWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="xpl-view-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / "scripts").mkdir()
        (self.repo / "configs").mkdir()
        shutil.copy(ROOT / "scripts/policy_workspace.py", self.repo / "scripts")
        shutil.copy(ROOT / "configs/policy_workspace.json", self.repo / "configs")
        self.defaults = json.loads((self.repo / "configs/policy_workspace.json").read_text())["active_policies"]
        for name in [*self.defaults, "Mem_0"]:
            base = self.repo / "policy" / name
            base.mkdir(parents=True)
            (base / "deploy.yml").write_text(f"policy_name: {name}\n")
            (base / "model.py").write_text("# original\n")
        (self.repo / ".gitignore").write_text("**/checkpoints/\n")
        (self.repo / "docs/nested").mkdir(parents=True)
        (self.repo / "docs/nested/guide.md").write_text("# Keep docs visible\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True)

    def run_view(self, *args):
        return subprocess.run(
            [sys.executable, str(self.repo / "scripts/policy_workspace.py"), *args],
            cwd=self.repo, capture_output=True, text=True,
        )

    def test_focus_expand_and_full_preserve_active_edits(self):
        model = self.repo / "policy/Pi_05/model.py"
        model.write_text("# local work\n")
        for args, optional_visible in [(('focus',), False), (('focus', 'Mem_0'), True), (('full',), True)]:
            result = self.run_view(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((self.repo / "policy/Mem_0/model.py").exists(), optional_visible)
            self.assertEqual(model.read_text(), "# local work\n")
            for name in self.defaults:
                self.assertTrue((self.repo / "policy" / name / "model.py").exists(), name)
            self.assertTrue((self.repo / "docs/nested/guide.md").exists())
            self.assertNotIn("D ", self.git("status", "--short"))

    def assert_focus_refused(self):
        result = self.run_view("focus")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to hide", result.stderr)
        self.assertTrue((self.repo / "policy/Mem_0/model.py").exists())

    def test_refuses_unstaged_optional_changes(self):
        (self.repo / "policy/Mem_0/model.py").write_text("# changed\n")
        self.assert_focus_refused()

    def test_refuses_staged_optional_changes(self):
        (self.repo / "policy/Mem_0/model.py").write_text("# changed\n")
        self.git("add", "policy/Mem_0/model.py")
        self.assert_focus_refused()

    def test_refuses_staged_deploy_deletion(self):
        self.git("rm", "policy/Mem_0/deploy.yml")
        self.assert_focus_refused()

    def test_refuses_unregistered_local_policy_files(self):
        folder = self.repo / "policy/NewPolicy"
        folder.mkdir()
        (folder / "draft.py").write_text("# work in progress\n")
        self.assert_focus_refused()
        self.assertTrue((folder / "draft.py").exists())

    def test_refuses_untracked_optional_files(self):
        (self.repo / "policy/Mem_0/local.txt").write_text("experiment")
        self.assert_focus_refused()

    def test_refuses_ignored_optional_assets(self):
        folder = self.repo / "policy/Mem_0/checkpoints"
        folder.mkdir()
        (folder / "weights.bin").write_bytes(b"keep")
        self.assert_focus_refused()
        self.assertEqual((folder / "weights.bin").read_bytes(), b"keep")

    def test_unknown_policy_does_not_change_view(self):
        result = self.run_view("focus", "wrong_name")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown policies", result.stderr)
        self.assertTrue((self.repo / "policy/Mem_0/model.py").exists())


if __name__ == "__main__":
    unittest.main()
