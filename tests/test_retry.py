"""Tests offline cho ngân sách thử lại khi gặp 429 (bộ tools bonus)."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import run_agent
from bonus.tools import BonusTools
from status_tools import StatusTools
from test_lab import FakeProvider, tool_call, final


def vercel_calls(result):
    return [t for t in result['trace'] if t['event'] == 'tool' and t['name'] == 'get_vercel_status']


def last_observation(fake, index):
    return json.loads(fake.histories[index][-1]['content'])


class RateLimitRetryTests(unittest.TestCase):
    @patch('agent.time.sleep')
    def test_model_sees_429_with_retries_remaining_then_recovers(self, sleep):
        fake = FakeProvider([tool_call('a', 'get_vercel_status', '{}'),
                             tool_call('b', 'get_vercel_status', '{}'),
                             final('Vercel ổn định.')])
        result = run_agent('x', fake, BonusTools('snapshot', 'rate_limit_once'))
        first = last_observation(fake, 1)
        self.assertEqual(first['error'], 'RATE_LIMITED')
        self.assertEqual(first['retries_remaining'], 2)
        self.assertEqual(last_observation(fake, 2)['provider'], 'vercel')
        self.assertEqual(len(vercel_calls(result)), 2)
        self.assertEqual(result['status'], 'completed')

    @patch('agent.time.sleep')
    def test_gate_pushes_back_when_model_stops_with_retries_left(self, sleep):
        fake = FakeProvider([tool_call('a', 'get_vercel_status', '{}'),
                             final('Bạn có muốn tôi thử lại không?'),
                             tool_call('b', 'get_vercel_status', '{}'),
                             final('Vercel ổn định.')])
        result = run_agent('x', fake, BonusTools('snapshot', 'rate_limit_once'))
        self.assertTrue(any(t['event'] == 'validation_pending_retry' for t in result['trace']))
        self.assertEqual(len(vercel_calls(result)), 2)
        self.assertEqual(result['answer'], 'Vercel ổn định.')

    @patch('agent.time.sleep')
    def test_budget_is_three_calls_and_later_calls_are_blocked(self, sleep):
        script = [tool_call(c, 'get_vercel_status', '{}') for c in 'abcd'] + [final('Chưa biết trạng thái Vercel.')]
        fake = FakeProvider(script)
        result = run_agent('x', fake, BonusTools('snapshot', 'rate_limit_always'))
        self.assertEqual(len(vercel_calls(result)), 3)  # lần gọi thứ tư bị chặn, không chạm tool
        self.assertTrue(any(t['event'] == 'retry_budget_exhausted' for t in result['trace']))
        third = last_observation(fake, 3)
        self.assertTrue(third['retry_exhausted'])
        self.assertEqual(third['retries_remaining'], 0)
        self.assertTrue(last_observation(fake, 4)['retry_exhausted'])
        self.assertEqual(result['status'], 'completed')

    @patch('agent.time.sleep')
    def test_long_retry_after_stops_without_waiting(self, sleep):
        class SlowTools(BonusTools):
            def execute(self, name, args):
                return {'ok': False, 'error': 'RATE_LIMITED', 'http_status': 429,
                        'retry_after': '120', 'retriable': True, 'message': '429'}
        fake = FakeProvider([tool_call('a', 'get_github_status', '{}'), final('Không kiểm tra được.')])
        result = run_agent('x', fake, SlowTools('snapshot'))
        self.assertTrue(last_observation(fake, 1)['retry_exhausted'])
        sleep.assert_not_called()
        self.assertEqual(result['status'], 'completed')

    @patch('agent.time.sleep')
    def test_main_tools_unaffected(self, sleep):
        fake = FakeProvider([tool_call('a', 'get_status', '{"provider":"github"}'), final('Xong')])
        result = run_agent('x', fake, StatusTools())
        self.assertEqual(result['status'], 'completed')
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
