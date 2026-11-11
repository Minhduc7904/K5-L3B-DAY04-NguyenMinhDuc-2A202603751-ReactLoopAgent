"""Tests offline cho các lỗi/rủi ro phát hiện khi chấm độc lập."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evals'))
from agent import run_agent
from status_tools import StatusTools
from test_lab import FakeProvider, tool_call, final


class UnhashableArgumentTests(unittest.TestCase):
    def test_provider_as_list_or_dict_does_not_crash(self):
        for raw in ('{"provider":["github"]}', '{"provider":{"a":1},"incident_id":"x"}', '{"provider":null}'):
            with self.subTest(arguments=raw):
                fake = FakeProvider([tool_call('a', 'get_status', raw), final('Không đủ dữ liệu.')])
                result = run_agent('x', fake, StatusTools())
                self.assertEqual(result['status'], 'completed')
                observation = json.loads(fake.histories[1][-1]['content'])
                self.assertEqual(fake.histories[1][-1]['tool_call_id'], 'a')
                self.assertFalse(observation.get('ok', True))


if __name__ == '__main__':
    unittest.main()
