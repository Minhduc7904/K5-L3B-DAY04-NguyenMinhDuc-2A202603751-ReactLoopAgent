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


class DidYouMeanTests(unittest.TestCase):
    def test_typo_in_followed_incident_id_gets_suggestion(self):
        # h02n9572mx9y có update trỏ tới incidents/xr3myzj7ms51; model chép thiếu chữ '7'.
        fake = FakeProvider([
            tool_call('a', 'get_incident_details', '{"provider":"github","incident_id":"h02n9572mx9y"}'),
            tool_call('b', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzjms51"}'),
            tool_call('c', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzj7ms51"}'),
            final('Xong https://stspg.io/7pwv28hvkmz8 https://stspg.io/pjgptg3cfc6n')])
        result = run_agent('x', fake, StatusTools(), max_steps=6)
        miss = json.loads(fake.histories[2][-1]['content'])
        self.assertEqual(miss['error'], 'INCIDENT_NOT_FOUND')
        self.assertEqual(miss['did_you_mean'], 'xr3myzj7ms51')
        self.assertTrue(json.loads(fake.histories[3][-1]['content'])['ok'])
        self.assertEqual(result['status'], 'completed')

    def test_no_suggestion_when_nothing_close(self):
        fake = FakeProvider([
            tool_call('a', 'get_incident_details', '{"provider":"github","incident_id":"h02n9572mx9y"}'),
            tool_call('b', 'get_incident_details', '{"provider":"github","incident_id":"zzzzzzzzzzzz"}'),
            final('Không có. https://stspg.io/7pwv28hvkmz8')])
        run_agent('x', fake, StatusTools(), max_steps=6)
        self.assertNotIn('did_you_mean', json.loads(fake.histories[2][-1]['content']))

    def test_no_suggestion_before_anything_observed(self):
        fake = FakeProvider([
            tool_call('a', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzjms51"}'),
            final('Không tìm thấy.')])
        run_agent('x', fake, StatusTools())
        self.assertNotIn('did_you_mean', json.loads(fake.histories[1][-1]['content']))


if __name__ == '__main__':
    unittest.main()
