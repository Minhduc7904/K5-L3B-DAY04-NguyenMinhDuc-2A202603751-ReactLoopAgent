# Bằng chứng các lần chạy thử

Các file này là kết quả chạy trong lúc cải tiến, **không phải** file nộp chính (`eval_before.json`, `eval_after.json`, `eval_bonus.json` ở thư mục gốc). Cấu hình mọi lần chạy: `gpt-4.1-mini` cho agent và judge, `max_steps` = 8 (bài chính, held-out) hoặc 16 (bonus). Mỗi file chạy với mã ở thời điểm tương ứng nên không tái hiện chính xác với mã hiện tại.

## Lần chạy mã cuối (commit `bda9a12`)

| File | Nội dung |
|---|---|
| `heldout_results.json` | Bộ held-out `heldout/cases.json` (6 câu): trung bình 100 |
| `repeat_<case>_<n>.json` | Chạy lặp 3 lần mỗi case nhạy để đo dao động: H1, A7, E2, E3, E5 (bài chính), B3, B10 (bonus) |

## Các vòng trước khi chỉnh mã (giữ lại để không giấu kết quả xấu)

| File | Mã | Kết quả | Ý nghĩa |
|---|---|---|---|
| `round1/eval_after_round1.json` | commit `b7b7f44` | 98,32 | E2 = 80: tìm `component` "Cache - Purge" không khớp rồi kết luận không có incident; H7 = 90 |
| `round1/eval_bonus_round1.json` | commit `b7b7f44` | 98,2 (14,73/15) | B3 và B10 đã nêu 429 và timestamp; B4 bị cổng công bố nhắc một lần |
| `round1/heldout_round1.json` | commit `b7b7f44` | 91,67 | X1 = 50: model không gọi `get_status` khi người dùng khẳng định "đang sập" |
| `round2/eval_after_round2.json` | `b7b7f44` + chỉnh prompt | 96,86 | E2 sửa được (100) nhưng H1 tụt 60 vì model không theo liên kết ở lần chạy đó; H7 = 85 |
| `round2/heldout_round2.json` | `b7b7f44` + chỉnh prompt | 99,67 | X1 sửa được |
| `round2/repeat_*.json` | `b7b7f44` + chỉnh prompt | | Lặp A7, E2, E3, E5, B3, B10 trước khi có cổng theo liên kết |

Vòng 2 cho thấy chỉ dùng prompt thì H1 vẫn không ổn định, nên commit `bda9a12` thêm cổng `validation_unfollowed_link` trong code.

## Các lần chạy thử cũ (prompt phiên bản đầu)

| File | Case | Điểm | Ý nghĩa |
|---|---|---:|---|
| `h1_prompt_v1.json` | H1 | 60 | Quy tắc "hãy gọi... incident được nhắc tới": model vẫn dừng sau 1 lượt tool, bị trần 60 |
| `h1_prompt_v2.json` | H1 | 95 | Quy tắc "PHẢI gọi... ở lượt kế tiếp": model mở `xr3myzj7ms51` ở step 2 |
| `h6_prompt_v1.json` | H6 | 98 | Model chép sai ID thành `xr3myzjms51`, nhận `INCIDENT_NOT_FOUND`, kết luận sai; judge vẫn cho 98 |
| `h6_prompt_v2.json` | H6 | 95 | Lỗi chép sai ID lặp lại; căn cứ để thêm `did_you_mean` |
| `bonus_baseline_before_changes.json` | B1–B10 | 83,0 (9 case) | Bonus với `agent.py` chưa sửa gì cho bonus; B5 chưa chấm (provider timeout), B3 = B6 = B10 = 50 |
