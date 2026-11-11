# Bằng chứng các lần chạy thử

Các file này là kết quả chạy thử trong lúc cải tiến, **không phải** file nộp chính (`eval_before.json`, `eval_after.json`, `eval_bonus.json`). Mỗi file là một lần chạy một case duy nhất, nên điểm chỉ là một mẫu và không chứng minh độ ổn định. Cấu hình: `gpt-4.1-mini` cho agent và judge, `max_steps` = 8 (bài chính) hoặc 16 (bonus).

| File | Case | Điểm | Ý nghĩa |
|---|---|---:|---|
| `h1_prompt_v1.json` | H1 | 60 | Quy tắc prompt bản đầu ("hãy gọi... incident được nhắc tới") và cổng kiểm tra nguồn. Model vẫn dừng sau 1 lượt tool, bị trần 60 (`tool_steps` = 1). Bằng chứng rằng bản prompt đầu chưa đủ. |
| `h1_prompt_v2.json` | H1 | 95 | Quy tắc "PHẢI gọi... ở lượt kế tiếp". Model mở `xr3myzj7ms51` ở step 2, hết vi phạm. |
| `h6_prompt_v1.json` | H6 | 98 | Model theo link nhưng chép sai ID thành `xr3myzjms51` (thiếu chữ `7`), nhận `INCIDENT_NOT_FOUND`, kết luận sai. Judge vẫn cho 98. |
| `h6_prompt_v2.json` | H6 | 95 | Lỗi chép sai ID lặp lại y hệt dù prompt đã dặn thử lại. Căn cứ để thêm cơ chế `did_you_mean` trong code. |
| `bonus_baseline_before_changes.json` | B1–B10 | 83,0 (trung bình 9 case) | Bonus với `agent.py` chưa sửa gì cho bonus. B5 chưa chấm (provider timeout), B3 = B6 = B10 = 50. |

Các file này được tạo bằng mã ở những commit trước, nên không tái hiện chính xác với mã hiện tại.
