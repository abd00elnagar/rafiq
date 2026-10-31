import unittest
from pathlib import Path


class TestRequirements(unittest.TestCase):

    def setUp(self):
        self.root_dir = Path(__file__).resolve().parent.parent

    def _check_requirements_file(self, filename: str):
        filepath = self.root_dir / filename
        self.assertTrue(filepath.is_file(), f"{filename} should exist")

        lines = filepath.read_text(encoding="utf-8").splitlines()
        packages = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Each dependency line should start with a valid package name
            # and must NOT look like pip list tabular output
            parts = line.split()
            self.assertEqual(
                len(parts), 1,
                f"Line '{line}' in {filename} contains whitespace separating name and version, expected pip requirement format."
            )
            packages.append(parts[0])

        # Core required packages must be present
        required = ["livekit", "livekit-agents", "livekit-api", "sounddevice", "soundfile", "numpy", "python-dotenv"]
        for req in required:
            self.assertTrue(
                any(p.startswith(req) for p in packages),
                f"{req} must be present in {filename}"
            )

    def test_requirements_file(self):
        self._check_requirements_file("requirements.txt")

    def test_requirments_file(self):
        self._check_requirements_file("requirments.txt")


if __name__ == "__main__":
    unittest.main()
