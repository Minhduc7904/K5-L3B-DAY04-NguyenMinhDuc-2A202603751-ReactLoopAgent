"""Fuzz offline: provider và tool trả dữ liệu sai hình dạng ngẫu nhiên (seed cố định); mong đợi 0 crash.

Dùng:  python tests/fuzz_agent.py                       # kiểm tra agent.py hiện tại
       python tests/fuzz_agent.py <thư mục có agent.py khác>   # ví dụ so với bản cũ:
         git show bce4486:agent.py > old/agent.py && python tests/fuzz_agent.py old
Không gọi mạng, không cần API key. Không bị unittest discover thu thập (tên không bắt đầu bằng test).
"""
import json
import random
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = ([sys.argv[1]] if len(sys.argv) > 1 else []) + [str(ROOT), str(ROOT / 'evals'), str(ROOT / 'tests')]
import agent  # noqa: E402
from bonus.tools import BonusTools  # noqa: E402
from status_tools import StatusTools  # noqa: E402

RUNS = 4000
rnd = random.Random(7)
ATOMS = [None, 0, 1, -1, 3.5, float('nan'), float('inf'), '', 'x', 'github', ['github'], {'a': 1}, [], {}, True, 10 ** 400,
         'get_status', 'get_incident_details', 'get_vercel_status', '{"provider":"github"}', '{bad', '[]', '"s"']


def atom():
    return rnd.choice(ATOMS)


def value(depth=0):
    r = rnd.random()
    if depth > 2 or r < 0.5:
        return atom()
    if r < 0.75:
        return [value(depth + 1) for _ in range(rnd.randint(0, 3))]
    keys = ['ok', 'error', 'provider', 'incidents', 'updates', 'url', 'id', 'body', 'captured_at',
            'source', 'retry_after_seconds', 'message']
    return {rnd.choice(keys): value(depth + 1) for _ in range(rnd.randint(0, 5))}


def call():
    if rnd.random() < 0.6:
        return {'id': rnd.choice(['a', 'b', 'c']),
                'name': rnd.choice(['get_status', 'get_incident_details', 'get_vercel_status']),
                'arguments': rnd.choice(['{}', '{"provider":"github"}',
                                         '{"provider":"github","incident_id":"x"}', '{bad', atom()])}
    return {k: atom() for k in ('id', 'name', 'arguments') if rnd.random() < 0.8}


def response():
    if rnd.random() < 0.1:
        return atom()
    msg = {'role': 'assistant', 'content': rnd.choice(['Xong', '', None, ['p'], 'https://x 2026-11-10 429'])}
    out = {'message': msg if rnd.random() < 0.9 else atom(),
           'finish': rnd.choice(['stop', 'tool_calls', 'length', None, 'x']),
           'usage': rnd.choice([{}, None, 'u', {'total_tokens': 1}])}
    if rnd.random() < 0.6:
        out['calls'] = [call() for _ in range(rnd.randint(0, 3))] if rnd.random() < 0.9 else atom()
    return out


class RandomProvider:
    def complete(self, messages, schemas):
        if rnd.random() < 0.05:
            raise RuntimeError('boom')
        return response()


class RandomTools:
    def execute(self, name, args):
        r = rnd.random()
        if r < 0.1:
            raise ValueError('tool boom')
        if r < 0.5:
            return value()
        if r < 0.6:
            return {'ok': False, 'error': 'RATE_LIMITED', 'retry_after_seconds': atom()}
        return rnd.choice([StatusTools(), BonusTools()]).execute(name, args if isinstance(args, dict) else {})


def main():
    crashes, statuses = 0, {}
    with mock.patch('agent.time.sleep'):
        for _ in range(RUNS):
            tools = RandomTools()
            if rnd.random() < 0.5:
                tools.system_prompt, tools.schemas = 'bonus', []
            try:
                res = agent.run_agent('Câu hỏi', RandomProvider(), tools, max_steps=rnd.randint(1, 8))
                json.dumps(res)  # kết quả phải serialize được
                assert res['status'] in ('completed', 'error', 'max_steps')
                statuses[res['status']] = statuses.get(res['status'], 0) + 1
            except Exception:
                crashes += 1
                if crashes <= 3:
                    import traceback
                    traceback.print_exc()
    print(f'runs={RUNS} crashes={crashes} statuses={statuses}')
    return 1 if crashes else 0


if __name__ == '__main__':
    sys.exit(main())
