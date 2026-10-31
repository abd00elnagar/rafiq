import unittest
from pathlib import Path
from python_backend import agent
from livekit.agents import AgentServer


class TestAgentBackend(unittest.TestCase):

    def test_server_instance(self):
        """Verify AgentServer is instantiated correctly."""
        self.assertIsInstance(agent.server, AgentServer)

    def test_voice_agent_handler_registered(self):
        """Verify voice_agent handler is a callable coroutine function."""
        import inspect
        self.assertTrue(callable(agent.voice_agent))
        self.assertTrue(inspect.iscoroutinefunction(agent.voice_agent))

    def test_base_dir(self):
        """Verify BASE_DIR points to python_backend directory."""
        self.assertTrue(agent.BASE_DIR.is_dir())
        self.assertEqual(agent.BASE_DIR.name, "python_backend")


if __name__ == "__main__":
    unittest.main()
