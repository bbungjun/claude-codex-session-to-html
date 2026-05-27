import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DefaultOutputPathTests(unittest.TestCase):
    def test_installer_prompts_for_history_index_output_directory(self):
        install_script = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("GetFolderPath('Desktop')", install_script)
        self.assertIn('DEFAULT_OUTPUT_BASE="$DEFAULT_DESKTOP/session_history"', install_script)
        self.assertIn("Session history/index output directory", install_script)
        self.assertNotIn(
            'DEFAULT_OUTPUT_BASE="/mnt/c/Users/$WIN_USER/Desktop/session_history"',
            install_script,
        )
        self.assertNotIn("/mnt/c/Users/$WIN_USER", install_script)
        self.assertIn('CLAUDE_OUT="$OUTPUT_BASE"', install_script)
        self.assertIn('CODEX_OUT="$OUTPUT_BASE"', install_script)

    def test_converter_templates_do_not_assume_windows_user_profile_path(self):
        claude_converter = (ROOT / "hooks" / "session_to_html.py").read_text(
            encoding="utf-8"
        )
        codex_converter = (ROOT / "hooks" / "codex_to_html.py").read_text(
            encoding="utf-8"
        )

        expected_claude = 'OUTPUT_DIR      = Path.home() / "session_history"'
        expected_codex = 'OUTPUT_DIR       = Path.home() / "session_history"'

        self.assertIn(expected_claude, claude_converter)
        self.assertIn(expected_codex, codex_converter)
        self.assertNotIn("/mnt/c/Users/__USERNAME__", claude_converter)
        self.assertNotIn("/mnt/c/Users/__USERNAME__", codex_converter)

    def test_watcher_tracks_codex_jsonl_modifications(self):
        watcher = (ROOT / "hooks" / "session_watcher.sh").read_text(encoding="utf-8")

        self.assertIn("-e close_write,create,modify,moved_to", watcher)


if __name__ == "__main__":
    unittest.main()
