# Ghi chú phân tích · Day 04

Họ và tên: Nguyễn Minh Đức
MSSV: 2A202603751

## 1. Case được chọn

- ID case: **H1** (cùng nguyên nhân với **H6**)
- Câu hỏi: "Điều tra incident GitHub h02n9572mx9y. Theo liên kết do incident cung cấp để tìm nguyên nhân và ảnh hưởng, rồi đối chiếu với incident Cloudflare yaa0witbl2me..."
- Câu trả lời của agent: Liệt kê đúng tên, trạng thái (resolved), component và thời gian của hai incident, dẫn nguồn từng bên và không suy ra nguyên nhân chung. Tuy nhiên chỉ **in ra** link `https://www.githubstatus.com/incidents/xr3myzj7ms51` mà **không mở** incident này, nên không đọc được nguyên nhân và ảnh hưởng ở incident gộp.
- Điểm ở lần chạy 1: **H1 = 60/100** (LLM judge cho 96 điểm, nhưng kiểm tra bằng code áp trần 60). H6 cũng 60/100. Điểm tổng lần 1 là 92,14.

## 2. Bằng chứng trong trace

`grade.mechanical` của H1 báo vi phạm: "Cần tool calls ở ít nhất 2 model steps khác nhau." (`tool_calls: 2`, `tool_steps: 1`, `score_cap: 60`). H6 có cùng vi phạm.

Trace của H1 (rút gọn). Agent gọi hai tool ngay ở step 1, sau đó dừng ở step 2 mà không gọi tiếp:

```text
{'event': 'model', 'step': 1, 'finish': 'tool_calls', 'tool_calls': 2}
{'event': 'tool', 'step': 1, 'name': 'get_incident_details',
 'arguments': '{"provider": "github", "incident_id": "h02n9572mx9y"}'}
   -> updates[].body: "Please refer to the combined summary in this related incident:
                       https://www.githubstatus.com/incidents/xr3myzj7ms51"
{'event': 'tool', 'step': 1, 'name': 'get_incident_details',
 'arguments': '{"provider": "cloudflare", "incident_id": "yaa0witbl2me"}'}
{'event': 'model', 'step': 2, 'finish': 'stop', 'tool_calls': 0}
```

**Nguyên nhân có thể:** lỗi nằm ở **prompt**, không phải ở vòng lặp. Vòng lặp xử lý đúng mọi tool call và chỉ dừng khi model không gọi thêm. Tool result đã chứa tham chiếu tới incident `xr3myzj7ms51`, nhưng `SYSTEM_PROMPT` hiện không yêu cầu model theo dõi incident được nhắc tới, nên model coi link như thông tin để trích dẫn và kết thúc sớm.

## 3. Thay đổi đã thực hiện

Đã làm (CP2, CP3), `agent.py`:
- Vòng lặp tự viết: giữ nguyên assistant message, xử lý mọi tool call và trả đúng `tool_call_id`.
- `max_steps`, JSON arguments lỗi (trả `INVALID_ARGUMENTS`), lỗi tool trả về như observation, `finish == 'length'` và lỗi provider trả `error`.
- Kết quả test offline: 35/37 pass; 2 test còn lại là `EvidenceGateTests` của Bài 4.

Bài 4, `agent.py`:
- **Sửa gì, ở đâu:**
  1. Cổng kiểm tra nguồn trong `run_agent`: lưu `url` của mỗi `get_incident_details` thành công vào `sources`. Khi model định kết thúc (`finish == 'stop'`) mà câu trả lời không chứa URL nào trong `sources`, ghi event `validation_missing_source` vào trace và thêm một tin nhắn `user` yêu cầu viết lại kèm URL. Nếu đã hết `max_steps` thì trả `max_steps`, không báo `completed`. Không áp dụng khi chưa có incident nào đọc thành công.
  2. Bổ sung vào `SYSTEM_PROMPT`: nếu update nhắc tới incident khác (ID hoặc URL `.../incidents/<id>`) thì **phải** gọi `get_incident_details` cho incident đó ở lượt kế tiếp trước khi trả lời; chép ID chính xác từng ký tự; nếu gặp `INCIDENT_NOT_FOUND` thì kiểm tra ID và thử lại một lần.
- **Vì sao chọn thay đổi này:** H1 và H6 cùng mắc lỗi dừng trước khi theo liên kết và mỗi case mất 40 điểm vì trần code, nên một thay đổi có thể cải thiện cả hai. Bản prompt đầu ("hãy gọi...") chưa đủ: chạy thử H1 vẫn 60. Bản "PHẢI gọi... ở lượt kế tiếp" đưa H1 lên 95 (bằng chứng chạy thử trong `evidence/`).
- **Kết quả test offline sau Bài 4:** 37/37 pass (kể cả `tests/test_validation.py`).

Vòng sửa sau khi chấm thử độc lập (cùng `agent.py`):
  3. **Sửa lỗi crash.** Khóa ngân sách retry dùng `provider` thô từ model; nếu `provider` là list/dict thì `TypeError: unhashable type` làm `run_agent` crash. Nay chỉ nhận chuỗi, còn lại dùng `None`.
  4. **`did_you_mean` cho `INCIDENT_NOT_FOUND`.** Ở H6 (lần chạy thử), model chép sai ID `xr3myzj7ms51` thành `xr3myzjms51` và không thử lại dù prompt đã dặn. Nay code ghi nhớ các ID đã thấy trong tool result (danh sách `incidents`, `id`, URL, và `incidents/<id>` trong nội dung update); khi gặp `INCIDENT_NOT_FOUND` thì dùng `difflib` (ngưỡng 0,8) để gợi ý ID gần nhất cho model. Chỉ gợi ý, không tự thay ID.
  5. **Cổng "provider lỗi chưa giải quyết".** Theo dõi provider có tool trả `ok: False` (trừ `INVALID_ARGUMENTS`, `UNKNOWN_TOOL`, `INCIDENT_NOT_FOUND`, `RATE_LIMITED`) mà chưa có lần gọi thành công sau đó. Khi model định kết thúc, nhắc **một lần** (event `validation_unresolved_failure`) không kết luận trạng thái provider đó và nói rõ chưa biết. Nhắm vào H7.
  6. **Hai quy tắc prompt mới:** đối chiếu bằng `get_status` khi người dùng khẳng định đang outage (H2); không kết luận trạng thái provider khi tool lỗi/timeout dù người dùng yêu cầu (H7).
  7. **Trace phản ánh đúng thứ model thấy:** event `tool` ghi kết quả đã có `attempts`, `retries_remaining`, `did_you_mean`.
- **Kết quả test offline hiện tại:** 53 test của bài chính và 3 test bonus đều pass (thêm `tests/test_retry.py`, `tests/test_hardening.py`).

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | 92,14 | **98,82** (+6,68) |
| Điểm case đã chọn | H1 = 60 (H6 = 60) | H1 = **98** (H6 = **100**) |
| Số model calls | 49 (tổng 22 case; H1 = 2) | 54 (H1 = 3) |
| Token, chi phí nếu có | 36.460 token của agent (chưa tính token của judge) | 52.111 token của agent (+43%; chưa tính token của judge) |

Cả hai lần dùng cùng cấu hình (khối `config` giống hệt): provider `openai`, model `gpt-4.1-mini`, judge cùng provider và model, `max_steps` = 8, dataset `core`. Cả 22 case đều được chấm ở hai lần.

`eval_after.json` là lần chạy với mã cuối cùng. Một lần chạy trước đó (mã chưa có các thay đổi 3–7) cho 95,86; file đó nằm trong lịch sử git (commit `e3f4f94`).

Chênh lệch theo case (chỉ liệt kê case có đổi điểm): H1 60→98, H2 50→100, H6 60→100, H7 75→100, A5 88→93, A7 94→90, E3 100→97, E5 100→96. Các case còn lại không đổi.

- **Lỗi đã giải quyết (có bằng chứng trong trace):**
  - **H1 (60→98).** Model gọi `get_incident_details` cho `xr3myzj7ms51` ở step 2, đủ 2 model steps có tool call, hết vi phạm `grade.mechanical`.
  - **H2 (50→100).** Sau `get_incident_details` ở step 1, model gọi thêm `get_status` ở step 2 (quy tắc prompt mới), nên hết trần 50 và trả lời đúng: incident đã resolved, Actions operational.
  - **H7 (75→100).** Cloudflare timeout; trace có event `validation_unresolved_failure` ở step 2, sau đó câu trả lời nói "tôi chưa biết trạng thái thực tế" của Cloudflare Spectrum thay vì kết luận operational. Đây là bằng chứng trực tiếp cho cổng mới.
  - **H6 (60→100).** Model đọc `h02n9572mx9y` rồi `xr3myzj7ms51` (ID đúng, `ok: true`), nên đủ 2 steps và trả lời dựa trên incident gộp. **Lưu ý:** lần này model không chép sai ID, nên `did_you_mean` không được kích hoạt; cải thiện ở H6 đến từ prompt hoặc dao động của model, không phải từ `did_you_mean`.
  - Các cổng cũng chạy ngoài đời: `validation_missing_source` ở A6, `validation_unresolved_failure` ở E6 và A3 (mỗi case thêm một model call, điểm vẫn 100).
- **Lỗi còn lại hoặc mới xuất hiện:**
  - **E3 100→97, E5 100→96, A7 94→90.** Không có vi phạm từ kiểm tra bằng code, không có event kiểm tra nào được kích hoạt, và số model calls không đổi ở E3 và E5. Nhiều khả năng là dao động của model hoặc judge, nhưng không loại trừ được ảnh hưởng của hai quy tắc prompt mới; một lần chạy không đủ để phân biệt. A5 tăng 88→93 cũng không có cơ chế tương ứng.
  - **Chi phí tăng:** +5 model calls và +15.651 token (+43%), do model gọi thêm tool theo link, đối chiếu `get_status` (H2), và các cổng nhắc (A6, E6, A3, H7). Chưa tính token của judge.

## 5. Giới hạn

- **Điểm judge là ước lượng.** Judge dùng cùng model với agent (`gpt-4.1-mini`) nên có thể thiên lệch. Ví dụ ở lần 1: H7 được chấm 75 dù judge tự ghi agent "không tuân thủ expected" (Cloudflare timeout nhưng vẫn kết luận operational), và A5 được chấm 88 dù câu trả lời đổi năm 2026 thành 2025. Ngược lại H1 có judge cho 96 nhưng bị trần 60 bởi kiểm tra bằng code, nên điểm cuối phụ thuộc nhiều vào `grade.mechanical`.
- **Snapshot cố định.** Dữ liệu chụp lúc 2026-11-09T03:50:47Z và chỉ gồm 50 incident gần nhất; tìm theo chuỗi gần đúng nên tìm không thấy không chứng minh incident không tồn tại. Kết quả không phản ánh trạng thái thực tế hiện tại.
- **Chỉ chạy một lần mỗi phiên bản.** Model có tính ngẫu nhiên, nên chênh lệch điểm giữa hai lần chưa đủ để kết luận cải tiến ổn định. Bốn case được nhắm tới (H1 +38, H2 +50, H6 +40, H7 +25) cộng khoảng +6,95 điểm tổng và có trace chứng minh cơ chế (H6 chỉ một phần, xem mục 4). Phần còn lại (A5 +5, A7 -4, E3 -3, E5 -4) cộng khoảng -0,27 và không gắn với cơ chế rõ ràng, nên coi là dao động. Lần chạy trước của chính mã này (95,86) cho thấy điểm tổng có thể lệch vài điểm giữa các lần chạy.
- **Cơ chế chưa được eval thật kiểm chứng.** `did_you_mean` không được kích hoạt trong lần chạy cuối (model không chép sai ID), nên chỉ được kiểm chứng bằng unit test. Lỗi chép sai ID `xr3myzjms51` chỉ quan sát được ở hai lần chạy thử riêng H6 (`evidence/h6_prompt_v1.json`, `evidence/h6_prompt_v2.json`).
- **Điểm cao không bằng nội dung đúng.** Ở các lần chạy thử, H6 đạt 98 và 95 dù chép sai ID incident và kết luận sai; kiểm tra bằng code chỉ đếm số step, còn judge cùng model với agent không phát hiện lỗi này.
- **H2 và H7 chủ yếu dựa vào prompt và nhắc nhở.** Chúng đạt 100 trong một lần chạy, nhưng không có bảo đảm; cổng provider lỗi chỉ nhắc một lần và model vẫn có thể viết lại sai.
- **Kiểm tra nguồn chỉ kiểm tra sự hiện diện của một URL**, không chứng minh mọi nhận định đều có nguồn.
- **Lịch sử commit.** Các commit CP1–CP6 được tạo lại theo checkpoint sau khi đã làm xong, nên thời gian commit không phản ánh thời điểm thực tế hoàn thành từng checkpoint.

## 6. Bonus: 5 nhà cung cấp, retry, phân trang, context

**Kết quả** (`eval_bonus.json`, 10/10 case được chấm): **99,4/100**, `bonus_points_0_15` = **14,91**. Cùng cấu hình với bài chính: `gpt-4.1-mini` cho agent và judge, `max_steps` = 16, dataset `bonus`. Chỉ B10 dưới 100 (94). Agent dùng khoảng 58 nghìn token (29 model calls), chưa tính judge. Kết quả này từ lần chạy với mã `agent.py` cuối cùng.

**Baseline trước khi sửa** (`agent.py` của bài chính, chưa sửa gì): 9/10 case được chấm, trung bình 83,0.
- **B5 chưa chấm**: provider báo `TimeoutError: The read operation timed out` ở step 3, không phải lỗi agent; chạy lại case này là có điểm.
- **B3 = 50, B10 = 50**: gặp 429 nhưng model không thử lại (B3 còn hỏi ngược người dùng "Bạn có muốn tôi thử lại?"); code chấm trần 50 vì cần ít nhất 2 lần gọi `get_vercel_status`.
- **B6 = 50**: chỉ gọi hai tool `get_*_status`, không gọi `get_incident_details` nên bị trần 50.

**Thay đổi trong `agent.py`:**
- **Retry 429 có ngân sách.** Model vẫn thấy observation 429 (test có sẵn `bonus/test_agent.py` yêu cầu điều này). Code thêm `attempts` và `retries_remaining` vào kết quả, chờ theo `Retry-After` (tối đa 5 giây; lớn hơn thì dừng, không chờ), và đếm 429 theo (tool, provider) trong cả run. Sau 3 lần thì không gọi tool nữa mà trả `retry_exhausted: true` (event `retry_budget_exhausted` trong trace), nên không vượt giới hạn "tối đa 3 lần".
- **Cổng nhắc thử lại.** Nếu model định kết thúc khi còn lượt thử lại, ghi event `validation_pending_retry` và nhắc model gọi lại, cùng kiểu với cổng kiểm tra nguồn.
- **`BONUS_RULES`.** Quy tắc nối thêm vào prompt chỉ khi bộ tools có `system_prompt` riêng, nên bài chính không bị ảnh hưởng: phải gọi `get_incident_details` khi cần chi tiết; đọc tiếp theo `next_offset`; gọi lại ngay khi `retries_remaining > 0`; thiếu tool cho provider thì nói thiếu dữ liệu.
- **Tests offline:** `tests/test_retry.py` (5 test) cho phần retry; xem mục 3 cho tổng số test hiện tại.

**Hành vi quan sát được trong trace:** B3 gọi Vercel hai lần (429 rồi thành công); B4 gọi Vercel đúng 3 lần rồi dừng và báo không biết trạng thái; B10 gặp 429 ở Vercel, thử lại thành công; B5 sửa tham số sau `INVALID_ARGUMENTS`; B2 đọc nhiều trang timeline; B6 gọi `get_incident_details` cho cả hai dịch vụ và bỏ qua nhiễu.

**Giới hạn còn lại:**
- Trong lần chạy eval cuối, **cổng nhắc thử lại và ngân sách 3 lần không được kích hoạt** (trace không có event `validation_pending_retry` hay `retry_budget_exhausted`) vì model tự thử lại đúng. Hai cơ chế này chỉ được kiểm chứng bằng unit test, chưa bằng eval thật.
- **Một lần chạy mỗi case có dao động.** Chạy riêng B3, B6, B10 cho 96, 98, 95 trong khi chạy cả bộ cho 100, 100, 94 với cùng mã. B6 chỉ được sửa bằng prompt nên không có bảo đảm.
- 429 trong eval là giả lập (`retry_after_seconds` = 0); logic chờ theo `Retry-After` thật chỉ được kiểm tra bằng unit test với thời gian chờ giả.
- Cổng nguồn chỉ kiểm tra URL của `get_incident_details`; status tool chỉ trả trang chủ nên không được kiểm tra.
- `eval_bonus.json` và `eval_after.json` đều được chạy lại với mã `agent.py` cuối cùng. Lần chạy bonus lặp lại cho kết quả giống lần trước: 99,4/100 (B10 = 94, các case khác 100), 29 model calls, 57.865 token (lần trước 28 calls, 53.951 token). Các cổng mới (`validation_unresolved_failure`, `did_you_mean`) không được kích hoạt trong lần chạy bonus.
