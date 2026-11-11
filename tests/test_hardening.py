"""Tests offline cho các lỗi/rủi ro phát hiện khi chấm độc lập."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evals'))
from agent import run_agent
from bonus.tools import BonusTools
from scenarios import ScenarioTools
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


class UnresolvedFailureGateTests(unittest.TestCase):
    def test_reminds_once_when_provider_failed_and_model_concludes(self):
        fake = FakeProvider([
            tool_call('a', 'get_status', '{"provider":"cloudflare","component":"Spectrum"}'),
            final('Cloudflare Spectrum đang operational.'),
            final('Chưa biết trạng thái Cloudflare vì timeout.')])
        result = run_agent('x', fake, ScenarioTools('cloudflare_timeout'))
        events = [t for t in result['trace'] if t['event'] == 'validation_unresolved_failure']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['providers'], ['cloudflare'])
        self.assertEqual(result['status'], 'completed')
        self.assertIn('Chưa biết', result['answer'])
        self.assertIn('cloudflare', fake.histories[2][-1]['content'])

    def test_reminder_is_not_repeated(self):
        fake = FakeProvider([
            tool_call('a', 'get_status', '{"provider":"cloudflare"}'),
            final('Operational.'), final('Vẫn operational.')])
        result = run_agent('x', fake, ScenarioTools('cloudflare_timeout'))
        self.assertEqual(len([t for t in result['trace'] if t['event'] == 'validation_unresolved_failure']), 1)
        self.assertEqual(result['answer'], 'Vẫn operational.')

    def test_no_reminder_after_later_success(self):
        class FlakyTools(StatusTools):
            first = True

            def execute(self, name, args):
                if self.first:
                    self.first = False
                    return {'ok': False, 'error': 'TimeoutError', 'message': 'timeout'}
                return super().execute(name, args)
        fake = FakeProvider([tool_call('a', 'get_status', '{"provider":"github"}'),
                             tool_call('b', 'get_status', '{"provider":"github"}'), final('Xong.')])
        result = run_agent('x', fake, FlakyTools())
        self.assertFalse(any(t['event'] == 'validation_unresolved_failure' for t in result['trace']))

    def test_not_found_does_not_trigger(self):
        fake = FakeProvider([
            tool_call('a', 'get_incident_details', '{"provider":"github","incident_id":"missing"}'),
            final('Không tìm thấy incident.')])
        result = run_agent('x', fake, StatusTools())
        self.assertFalse(any(t['event'] == 'validation_unresolved_failure' for t in result['trace']))

    def test_no_reminder_on_last_step(self):
        fake = FakeProvider([tool_call('a', 'get_status', '{"provider":"cloudflare"}'), final('Operational.')])
        result = run_agent('x', fake, ScenarioTools('cloudflare_timeout'), max_steps=2)
        self.assertFalse(any(t['event'] == 'validation_unresolved_failure' for t in result['trace']))
        self.assertEqual(result['status'], 'completed')


class TraceShowsWhatModelSawTests(unittest.TestCase):
    def test_trace_result_includes_retry_metadata(self):
        fake = FakeProvider([tool_call('a', 'get_vercel_status', '{}'), final('Tạm thời chưa biết.')])
        result = run_agent('x', fake, BonusTools('snapshot', 'rate_limit_always'), max_steps=2)
        tool_event = next(t for t in result['trace'] if t['event'] == 'tool')
        seen = json.loads(fake.histories[1][-1]['content'])
        self.assertEqual(tool_event['result'], seen)
        self.assertEqual(tool_event['result']['retries_remaining'], 2)

    def test_trace_result_includes_did_you_mean(self):
        fake = FakeProvider([
            tool_call('a', 'get_incident_details', '{"provider":"github","incident_id":"h02n9572mx9y"}'),
            tool_call('b', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzjms51"}'),
            final('Xong https://stspg.io/7pwv28hvkmz8')])
        result = run_agent('x', fake, StatusTools(), max_steps=5)
        miss = [t for t in result['trace'] if t['event'] == 'tool'][1]
        self.assertEqual(miss['result']['did_you_mean'], 'xr3myzj7ms51')
        for event in result['trace']:
            if event['event'] == 'tool':
                self.assertTrue({'step', 'name', 'arguments', 'result'} <= set(event))


if __name__ == '__main__':
    unittest.main()
