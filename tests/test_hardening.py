"""Tests offline cho các lỗi/rủi ro phát hiện khi chấm độc lập."""
import json
import math
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evals'))
import agent
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


class StubTools:
    """Tool giả trả đúng giá trị cấu hình, để thử các kết quả sai hình dạng."""
    def __init__(self, value):
        self.value = value

    def execute(self, name, args):
        return self.value


def events(result, name):
    return [t for t in result['trace'] if t['event'] == name]


class MalformedResponseTests(unittest.TestCase):
    def run_with(self, response):
        return run_agent('x', FakeProvider([response]), StatusTools())

    def test_response_with_wrong_shape_is_error_not_crash(self):
        message = {'role': 'assistant', 'content': None}
        cases = {
            'none': None,
            'list': [],
            'no_message': {'calls': [], 'finish': 'stop'},
            'message_none': {'message': None, 'calls': [], 'finish': 'stop'},
            'message_list': {'message': [], 'calls': [], 'finish': 'stop'},
            'calls_not_list': {'message': message, 'calls': 'x', 'finish': 'tool_calls'},
            'call_not_dict': {'message': message, 'calls': ['x'], 'finish': 'tool_calls'},
            'call_no_id': {'message': message, 'calls': [{'name': 'get_status', 'arguments': '{}'}], 'finish': 'tool_calls'},
            'call_no_name': {'message': message, 'calls': [{'id': 'a', 'arguments': '{}'}], 'finish': 'tool_calls'},
            'name_is_list': {'message': message, 'calls': [{'id': 'a', 'name': ['x'], 'arguments': '{}'}], 'finish': 'tool_calls'},
            'id_is_dict': {'message': message, 'calls': [{'id': {}, 'name': 'get_status', 'arguments': '{}'}], 'finish': 'tool_calls'},
        }
        for label, response in cases.items():
            with self.subTest(case=label):
                result = self.run_with(response)
                self.assertEqual(result['status'], 'error')
                self.assertEqual(len(events(result, 'malformed_response')), 1)

    def test_arguments_given_as_object_are_accepted(self):
        message = {'role': 'assistant', 'content': None}
        response = {'message': message, 'finish': 'tool_calls', 'usage': 'bad',
                    'calls': [{'id': 'a', 'name': 'get_status', 'arguments': {'provider': 'github'}}]}
        fake = FakeProvider([response, final('Xong.')])
        result = run_agent('x', fake, StatusTools())
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(json.loads(fake.histories[1][-1]['content'])['provider'] == 'github')
        self.assertEqual(result['usage'][0], {})

    def test_arguments_none_or_number_become_invalid_arguments_observation(self):
        for raw in (None, 5):
            with self.subTest(arguments=raw):
                response = tool_call('a', 'get_status', '{}')
                response['calls'][0]['arguments'] = raw
                fake = FakeProvider([response, final('Xong.')])
                result = run_agent('x', fake, StatusTools())
                self.assertEqual(result['status'], 'completed')


class DefensiveToolPathTests(unittest.TestCase):
    def run_stub(self, value, name='get_status', arguments='{"provider":"github"}'):
        fake = FakeProvider([tool_call('a', name, arguments), final('Xong.'), final('Xong.')])  # dư 1: cổng lỗi có thể nhắc
        result = run_agent('x', fake, StubTools(value))
        self.assertEqual(result['status'], 'completed')
        observation = json.loads(fake.histories[1][-1]['content'])  # model nhận JSON hợp lệ
        return result, observation

    def test_fields_with_wrong_types_do_not_crash(self):
        values = [
            {'ok': True, 'incidents': 5, 'updates': 7, 'url': 12, 'id': ['x']},
            {'ok': True, 'incidents': [1, None, 'x'], 'updates': [3, None], 'url': ['u']},
            {'ok': False, 'error': ['RATE_LIMITED']},
            {'ok': False, 'error': {'a': 1}},
            {'provider': ['github'], 'incidents': [{'id': ['z']}]},
        ]
        for value in values:
            with self.subTest(value=value):
                self.run_stub(value)
                self.run_stub(value, 'get_incident_details', '{"provider":"github","incident_id":"x"}')

    def test_non_dict_tool_result_becomes_observation(self):
        for value in (None, [], 'text', 3):
            with self.subTest(value=value):
                _, observation = self.run_stub(value)
                self.assertEqual(observation['error'], 'INVALID_TOOL_RESULT')

    def test_unserializable_tool_result_becomes_observation(self):
        cyclic = {}
        cyclic['self'] = cyclic
        for value in (cyclic, {(1, 2): 'tuple key'}):
            with self.subTest(value=repr(value)[:30]):
                result, observation = self.run_stub(value)
                self.assertEqual(observation['error'], 'UNSERIALIZABLE_RESULT')
                json.dumps(result['trace'])  # trace cũng phải serialize được

    def test_non_json_values_are_stringified_in_trace(self):
        result, observation = self.run_stub({'ok': True, 'items': {1, 2}, 'cls': object})
        json.dumps(result['trace'])
        self.assertTrue(observation['ok'])

    def test_bad_url_is_not_used_as_source(self):
        result, _ = self.run_stub({'ok': True, 'url': 123}, 'get_incident_details',
                                  '{"provider":"github","incident_id":"x"}')
        self.assertFalse(events(result, 'validation_missing_source'))


class InventedIdTests(unittest.TestCase):
    def lookup(self, question, calls):
        responses = [tool_call(str(i), 'get_incident_details', json.dumps(args)) for i, args in enumerate(calls)]
        fake = FakeProvider(responses + [final('Xong.')])
        run_agent(question, fake, StatusTools(), max_steps=len(calls) + 2)
        return [json.loads(h[-1]['content']) for h in fake.histories[1:len(calls) + 1]]

    def test_id_never_seen_gets_hint(self):
        miss, = self.lookup('Có incident nào không?', [{'provider': 'github', 'incident_id': 'phoenix'}])
        self.assertEqual(miss['error'], 'INCIDENT_NOT_FOUND')
        self.assertIn('hint', miss)
        self.assertIn('get_status', miss['message'])

    def test_id_from_question_gets_no_hint(self):
        miss, = self.lookup('Cho tôi xem incident zz9999 của GitHub', [{'provider': 'github', 'incident_id': 'zz9999'}])
        self.assertEqual(miss['error'], 'INCIDENT_NOT_FOUND')
        self.assertNotIn('hint', miss)

    def test_id_seen_in_tool_result_gets_no_hint(self):
        _, miss = self.lookup('x', [{'provider': 'github', 'incident_id': 'h02n9572mx9y'},
                                    {'provider': 'cloudflare', 'incident_id': 'h02n9572mx9y'}])
        self.assertEqual(miss['error'], 'INCIDENT_NOT_FOUND')
        self.assertNotIn('hint', miss)

    def test_typo_still_gets_did_you_mean_not_hint(self):
        _, miss = self.lookup('x', [{'provider': 'github', 'incident_id': 'h02n9572mx9y'},
                                    {'provider': 'github', 'incident_id': 'xr3myzjms51'}])
        self.assertIn('did_you_mean', miss)
        self.assertNotIn('hint', miss)

    def test_non_string_id_does_not_crash(self):
        miss, = self.lookup('x', [{'provider': 'github', 'incident_id': ['a']}])
        self.assertFalse(miss['ok'])


class EmptyAnswerTests(unittest.TestCase):
    def test_empty_answer_is_nudged_once_then_completes(self):
        for empty in ('', '   \n', None):
            with self.subTest(empty=empty):
                fake = FakeProvider([final(empty), final('Có đáp án.')])
                result = run_agent('x', fake, StatusTools())
                self.assertEqual(result['status'], 'completed')
                self.assertEqual(result['answer'], 'Có đáp án.')
                self.assertEqual(len(events(result, 'validation_empty_answer')), 1)
                self.assertEqual(fake.histories[1][-1]['role'], 'user')

    def test_repeated_empty_answer_is_error(self):
        result = run_agent('x', FakeProvider([final(''), final(' ')]), StatusTools())
        self.assertEqual(result['status'], 'error')
        self.assertIn('rỗng', result['error'])

    def test_empty_answer_on_last_step_is_error(self):
        result = run_agent('x', FakeProvider([final('')]), StatusTools(), max_steps=1)
        self.assertEqual(result['status'], 'error')

    def test_non_string_content_counts_as_empty(self):
        response = final('x')
        response['message']['content'] = ['phần', 'tử']
        result = run_agent('x', FakeProvider([response, final('Ổn.')]), StatusTools())
        self.assertEqual(result['answer'], 'Ổn.')


class RetryDelayTests(unittest.TestCase):
    def sleeps_for(self, retry_after):
        value = {'ok': False, 'error': 'RATE_LIMITED', 'retry_after_seconds': retry_after}
        fake = FakeProvider([tool_call(str(i), 'get_status', '{"provider":"github"}') for i in range(4)]
                            + [final('Chưa biết trạng thái.')] * 2)
        slept = []
        with mock.patch('agent.time.sleep', side_effect=slept.append):
            result = run_agent('x', fake, StubTools(value), max_steps=8)
        return slept, result

    def test_invalid_retry_after_never_reaches_sleep(self):
        for value in (float('nan'), -3, '-1', 10 ** 400, 'abc', [], {}):
            with self.subTest(retry_after=value):
                slept, _ = self.sleeps_for(value)
                self.assertTrue(slept)
                for seconds in slept:
                    self.assertTrue(math.isfinite(seconds) and 0 <= seconds <= agent.MAX_RETRY_WAIT)

    def test_infinite_or_huge_retry_after_stops_without_sleeping(self):
        for value in (float('inf'), 1e9, '9999'):
            with self.subTest(retry_after=value):
                slept, result = self.sleeps_for(value)
                self.assertEqual(slept, [])
                self.assertEqual(result['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
