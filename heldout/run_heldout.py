"""Chạy bộ câu hỏi held-out: cùng loại tình huống với eval chính nhưng diễn đạt và ID khác.

Mục đích: kiểm tra các quy tắc/cơ chế của agent có tổng quát hay chỉ khớp 22 câu eval.
Tái dùng run_case (evals/run_evals.py) và summarize (evals/grading.py); không sửa hai file đó.
Dùng: python heldout/run_heldout.py --output evidence/heldout_results.json
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evals'))
from grading import summarize  # noqa: E402
from run_evals import run_case  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description='Chạy bộ held-out và chấm 0–100 bằng judge của eval chính')
    choices = ['openai', 'gemini', 'anthropic', 'openrouter']
    parser.add_argument('--provider', choices=choices, default=os.getenv('PROVIDER', 'openai'))
    parser.add_argument('--model', default=os.getenv('MODEL'))
    parser.add_argument('--judge-provider', choices=choices, default=os.getenv('JUDGE_PROVIDER'))
    parser.add_argument('--judge-model', default=os.getenv('JUDGE_MODEL'))
    parser.add_argument('--case', help='Ví dụ X1; bỏ trống để chạy toàn bộ')
    parser.add_argument('--max-steps', type=int, default=8)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--output', default='evidence/heldout_results.json')
    args = parser.parse_args()
    args.judge_provider = args.judge_provider or args.provider
    args.judge_model = args.judge_model or args.model
    args.bonus = False
    if not args.model or not args.judge_model:
        parser.error('Thiếu --model hoặc MODEL')
    if args.max_steps < 1 or not 1 <= args.workers <= 8:
        parser.error('--max-steps phải >= 1 và --workers phải từ 1 đến 8')

    cases = json.loads((Path(__file__).parent / 'cases.json').read_text(encoding='utf-8'))
    selected = [c for c in cases if not args.case or c['id'] == args.case.upper()]
    if not selected:
        parser.error('Không tìm thấy case')

    def run_and_print(case):
        print(f"Đang chạy {case['id']}", flush=True)
        item = run_case(case, args)
        print(f"{case['id']}: {item['grade'].get('score')} ({item['grade']['status']})", flush=True)
        return item

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run_and_print, selected))
    report = {'summary': summarize(results),
              'config': {'provider': args.provider, 'model': args.model, 'judge_provider': args.judge_provider,
                         'judge_model': args.judge_model, 'max_steps': args.max_steps, 'dataset': 'heldout'},
              'cases': results}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = report['summary']
    print(f"Điểm held-out: {summary['score_0_100']}/100; đã chấm {summary['scored_cases']}/{summary['total_cases']} case. File: {out}")
    low = [r['id'] for r in results if (r['grade'].get('score') or 0) < 90]
    if low:
        print('Case dưới 90:', ', '.join(low))
    return 0 if summary['score_0_100'] is not None else 1


if __name__ == '__main__':
    sys.exit(main())
