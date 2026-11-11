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

**Nguyên nhân có thể:** lỗi nằm ở **prompt**, không phải ở vòng lặp. Vòng lặp xử lý đúng mọi tool call và chỉ dừng khi model không gọi thêm. Tool result đã chứa tham chiếu tới incident `xr3myzj7ms51`, nhưng `SYSTEM_PROMPT` ban đầu không yêu cầu model theo dõi incident được nhắc tới, nên model coi link như thông tin để trích dẫn và kết thúc sớm.

## 3. Thay đổi đã thực hiện

### 3.1 Cải tiến chính: luôn theo liên kết sang incident được nhắc tới (H1, H6)

H1 và H6 cùng mắc lỗi dừng trước khi theo liên kết và mỗi case mất 40 điểm vì trần code, nên một thay đổi sửa được cả hai. Tiến trình, mỗi dòng là bằng chứng trong `evidence/`:

| Bước | Thay đổi | Kết quả |
|---|---|---|
| Prompt v1 | "hãy gọi... incident được nhắc tới" | H1 = 60: model vẫn dừng sau 1 lượt tool |
| Prompt v2 | "PHẢI gọi... ở lượt kế tiếp, chép ID chính xác" | H1 = 95, H6 = 98 (chạy riêng) |
| Chạy cả bộ (mã có prompt v2) | | H1 = 98, H6 = 100 |
| Vòng 2 (thêm đoạn prompt khác) | cùng quy tắc, prompt dài hơn | **H1 = 60 trở lại** ở một lần chạy: prompt đơn thuần không ổn định |
| Cổng `validation_unfollowed_link` (code) | Nếu update của incident đã đọc trỏ tới `.../incidents/<id>` mà chưa gọi `get_incident_details` cho id đó, nhắc đúng một lần khi model định kết thúc | Mã cuối: H1 = 96 (chạy cả bộ), lặp 3 lần: 100, 100, 96; H6 = 97 |

Giới hạn trung thực: ở các lần chạy mã cuối, model tự theo liên kết nên cổng này **không được kích hoạt ở bài chính** (chỉ kích hoạt ở bonus B2). Vì vậy tôi không thể nói cổng là nguyên nhân làm H1 tăng; cổng được thêm vì bằng chứng vòng 2 cho thấy prompt một mình có thể sai, và nó được kiểm chứng bằng unit test (`UnfollowedLinkGateTests`).

### 3.2 Vòng lặp (CP2, CP3) và cổng nguồn (Bài 4)

- Vòng lặp tự viết: giữ nguyên assistant message, xử lý mọi tool call và trả đúng `tool_call_id`; `max_steps`; JSON arguments lỗi trả `INVALID_ARGUMENTS`; lỗi tool trả về như observation; `finish == 'length'` và lỗi provider trả `error`.
- Cổng nguồn (Bài 4): lưu `url` của mỗi `get_incident_details` thành công; nếu câu trả lời cuối không chứa URL nào thì ghi `validation_missing_source` và yêu cầu viết lại kèm URL; hết `max_steps` thì trả `max_steps`, không báo `completed`.

### 3.3 Các thay đổi phụ sau khi tự đánh giá và chấm thử độc lập

Mỗi mục kèm lý do. Đây không phải cải tiến chính; chúng giảm rủi ro hoặc sửa lỗi tôi tìm thấy.

1. **Sửa crash (commit `1f601f0`).** Khóa ngân sách retry dùng `provider` thô từ model; list/dict gây `TypeError: unhashable`. Chỉ nhận chuỗi.
2. **Chuẩn hóa response và kết quả tool (`ff35be0`).** Response/message/calls/id/name sai hình dạng thì trả `error` với event `malformed_response`, không crash; kết quả tool không phải object hoặc không serialize được thì thành observation lỗi; các field `incidents`, `updates`, `url`, `error` sai kiểu không gây `TypeError`. Script fuzz 4000 lượt: bản trước các sửa này crash 1354 lần, bản mới 0 lần (đối chiếu `bce4486`).
3. **Câu trả lời rỗng và `retry_after` (`f458e89`).** `stop` mà không có nội dung: nhắc một lần rồi `error` thay vì báo `completed`. `retry_after` là nan, âm hoặc không hợp lệ không đi vào `time.sleep`; inf hoặc lớn hơn 5 giây thì dừng thử lại.
4. **`did_you_mean` và `hint` cho `INCIDENT_NOT_FOUND`.** Ghi nhớ các ID đã thấy; ID gần giống (difflib, ngưỡng 0,8) thì gợi ý (nhắm lỗi chép sai `xr3myzjms51` ở H6); ID chưa từng xuất hiện trong câu hỏi hay tool result thì thêm `hint` "đừng tự đặt ID, lấy từ get_status" (nhắm A7).
5. **Cổng "provider lỗi chưa giải quyết" (`validation_unresolved_failure`).** Provider có tool lỗi mà chưa gọi lại thành công thì nhắc một lần không kết luận trạng thái của họ (nhắm H7, E6, A3).
6. **Quy tắc prompt tổng quát.** Prompt gốc cộng ba nguyên tắc kiểm chứng: đối chiếu khẳng định về trạng thái hiện tại bằng `get_status` (kể cả khi người dùng đã đưa sẵn ID); không kết luận về provider mà tool lỗi; không tự đặt ID incident; cộng quy tắc "component không khớp thì thử từ khóa ngắn hơn". Lúc đầu tôi viết hai quy tắc bám đúng câu hỏi H2 và H7; vì dễ thành "học theo bài", tôi viết lại thành nguyên tắc chung trước khi chạy vòng cuối và chạy bộ held-out để kiểm tra (mục 4.3). Sau vòng 1 tôi **chỉnh prompt đúng một lần** (hai mệnh đề về `get_status` và về component không khớp) vì E2 = 80 và held-out X1 = 50.
7. **Trace ghi đúng thứ model thấy** (`attempts`, `retries_remaining`, `did_you_mean`...).
8. **Cổng công bố cho bonus** (mục 6).

### 3.4 Cơ chế nào đã được eval thật kích hoạt

| Cơ chế | Kích hoạt ở lần chạy mã cuối | Chỉ có unit test |
|---|---|---|
| `validation_unresolved_failure` | E6, A3, H7 (bài chính), X3 (held-out) | |
| `validation_missing_source` | A7 | |
| `validation_unfollowed_link` | B2 (bonus) | bài chính |
| `validation_missing_disclosure` | B2 (bonus); B4 ở vòng 1 | |
| `validation_pending_retry` | B10 (bonus) | |
| `did_you_mean`, `hint` ID tự đặt, `validation_empty_answer`, `malformed_response`, `retry_budget_exhausted`, `disclosure_fallback` | | có (không xuất hiện trong eval) |

Số test offline hiện tại: **86 test bài chính và 3 test bonus, đều pass** (thêm `tests/test_retry.py`, `tests/test_hardening.py`).

## 4. So sánh các lần chạy

### 4.1 Trước và sau

Cùng cấu hình (khối `config` giống hệt, đã đối chiếu bằng code): `openai`, `gpt-4.1-mini` cho agent và judge, `max_steps` = 8, dataset `core`, cả 22 case đều được chấm.

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | 92,14 | **99,23** (+7,09) |
| Case chọn | H1 = 60 (H6 = 60) | H1 = **96** (H6 = **97**) |
| Model calls | 49 | 55 |
| Tool calls | 40 | 40 |
| Token của agent | 36.460 | 60.821 (+67%) |
| Token của judge | 36.076 | 36.521 |

Case đổi điểm: H1 60→96, H2 50→100, H6 60→97, H7 75→100, A5 88→100, A7 94→98, E2 100→98, A6 100→96, H3 100→98. Các case còn lại không đổi.

Chi phí tăng chủ yếu do thêm lượt tool theo liên kết (H1, H6), `get_status` đối chiếu (H2, H7) và các lượt nhắc của cổng.

### 4.2 Điểm tổng dao động giữa các lần chạy

Mã khác nhau, cùng bộ 22 case: 92,14 (trước), 95,86, 98,82, 98,32 (vòng 1), 96,86 (vòng 2, H1 = 60), **99,23** (mã cuối). Chênh 2–3 điểm giữa các lần chạy là bình thường, nên chênh nhỏ giữa hai lần không phải bằng chứng cải tiến. Bằng chứng cải tiến duy nhất là các case có trace thay đổi nguyên nhân (H1, H2, H6, H7).

Đo dao động của từng case trên mã cuối (lần chạy cả bộ + 3 lần chạy riêng, `evidence/repeat_*.json`):

| Case | Các lần chạy | Trung bình | Ghi chú |
|---|---|---:|---|
| H1 | 96, 100, 100, 96 | 98,0 | cả 4 lần đều theo liên kết |
| A7 | 98, 96, 96, 100 | 97,5 | cả 4 lần gọi đúng `c60k3g4vsoc1`, không bịa ID |
| E2 | 98, 100, 98, 100 | 99,0 | cả 4 lần mở `wp49bp8bqo6c` |
| E3 | 100, 100, 100, 100 | 100 | |
| E5 | 100, 100, 90, 95 | 96,3 | lần 90: judge cho rằng khẳng định "hoạt động bình thường vì components rỗng" quá mức |
| B3 (bonus) | 100, 100, 100, 100 | 100 | cả 4 câu trả lời nêu 429 và timestamp |
| B10 (bonus) | 95, 97, 98, 94 | 96,0 | cả 4 nêu timestamp từng provider và 429 |

Sửa phân tích trước đó: tôi từng xếp **A7 94→90** vào "dao động". Trace lần chạy đó cho thấy model **bịa ID `"phoenix"`** rồi nói "ID bạn cung cấp", tức là lỗi thật. Ở mã cuối, cả bốn lần A7 đều gọi đúng `c60k3g4vsoc1`, hint "đừng tự đặt ID" không cần kích hoạt; không chứng minh được hint có tác dụng, chỉ có thể nói lỗi không còn xuất hiện trong 4 mẫu.

### 4.3 Bộ held-out (`heldout/`)

6 câu cùng loại tình huống với eval chính nhưng diễn đạt khác và dùng ID khác (xác nhận sai tiền đề, timeout dưới áp lực, hỏi không kèm ID, theo liên kết `qpfv5p86dmrl`→`djlmxz2zd0j7`, tóm tắt một incident).

| Lần | Điểm | Ghi chú |
|---|---|---|
| Vòng 1 | 91,67 | X1 = 50: model không gọi `get_status` khi người dùng khẳng định "đang sập" |
| Vòng 2 (sau chỉnh prompt) | 99,67 | |
| Mã cuối | **100** | |

Giới hạn: tôi đã dùng kết quả X1 để chỉnh prompt một lần, nên X1 không còn là kiểm tra độc lập; 100 điểm ở bộ này lạc quan. Bộ chỉ có 6 câu và cũng do judge cùng model chấm.

## 5. Giới hạn

- **Điểm judge là ước lượng.** Judge dùng cùng model với agent nên có thể thiên lệch. Ví dụ lần 1: H7 được chấm 75 dù judge tự ghi agent "không tuân thủ expected"; A5 được chấm 88 dù câu trả lời đổi năm 2026 thành 2025. H1 có judge cho 96 nhưng bị trần 60 bởi kiểm tra bằng code, nên điểm cuối phụ thuộc nhiều vào `grade.mechanical`.
- **Judge chấm bonus sai ở lần chạy trước.** Chấm độc lập phát hiện B3 được 100 dù câu trả lời không nhắc 429 hay thử lại và không có timestamp; B10 thiếu timestamp từng provider. Tôi sửa bằng cổng công bố (mục 6) và **kiểm tra bằng mắt** câu trả lời mới (B3 và B10 trong 4 lần chạy đều có 429 và timestamp), không dựa vào điểm judge.
- **Snapshot cố định.** Dữ liệu chụp lúc 2026-11-09T03:50:47Z và chỉ gồm 50 incident gần nhất; tìm theo chuỗi gần đúng nên không tìm thấy không chứng minh incident không tồn tại.
- **Mẫu nhỏ.** Mỗi case tối đa 4 lần chạy; model có tính ngẫu nhiên. Lỗi hiếm (ví dụ chép sai ID) có thể không xuất hiện trong mẫu.
- **Điểm cao không bằng nội dung đúng.** Ở lần chạy thử, H6 đạt 98 và 95 dù chép sai ID và kết luận sai; kiểm tra bằng code chỉ đếm số step, còn judge cùng model không phát hiện.
- **Các quy tắc prompt và cổng chỉ nhắc một lần**, model vẫn có thể viết lại sai. Kiểm tra nguồn chỉ kiểm tra sự hiện diện của một URL, không chứng minh mọi nhận định có nguồn. Cổng theo liên kết chỉ bắt URL dạng `.../incidents/<id>`.
- **Cổng nhắc là "cố gắng tốt nhất".** Nếu provider lỗi sau lời nhắc bổ sung (công bố, theo liên kết), `run_agent` giữ câu trả lời trước và ghi `disclosure_fallback`; cần vì `bonus/test_agent.py` dùng provider giả không có thêm câu trả lời.
- **Lịch sử commit.** Các commit CP1–CP6 được tạo lại theo checkpoint sau khi đã làm xong, nên thời gian commit không phản ánh thời điểm thực tế hoàn thành từng checkpoint.

## 6. Bonus: 5 nhà cung cấp, retry, phân trang, context

**Kết quả** (`eval_bonus.json`, 10/10 case được chấm): **99,3/100**, `bonus_points_0_15` = **14,89**. Cùng cấu hình: `gpt-4.1-mini` cho agent và judge, `max_steps` = 16, dataset `bonus`. 32 model calls, 65.834 token của agent và 29.096 token của judge. Chỉ B10 (95) và B2 (98) dưới 100. Các lần chạy bonus trước: 99,4 (mã chưa có cổng công bố), 98,2 (vòng 1).

**Baseline trước khi sửa** (`agent.py` bài chính chưa sửa gì): 9/10 case được chấm, trung bình 83,0. B5 chưa chấm (provider `TimeoutError`, không phải lỗi agent); B3 = B10 = 50 (gặp 429 mà không thử lại; code chấm trần 50 vì cần ít nhất 2 lần gọi `get_vercel_status`); B6 = 50 (không gọi `get_incident_details`).

**Thay đổi trong `agent.py`:**
- **Retry 429 có ngân sách.** Model vẫn thấy observation 429 (`bonus/test_agent.py` yêu cầu). Code thêm `attempts`, `retries_remaining`, chờ theo `Retry-After` (tối đa 5 giây), đếm 429 theo (tool, provider) trong cả run; sau 3 lần thì không gọi tool nữa mà trả `retry_exhausted: true` (event `retry_budget_exhausted`).
- **Cổng nhắc thử lại** (`validation_pending_retry`) khi model định kết thúc mà còn lượt thử lại.
- **Cổng công bố** (`validation_missing_disclosure`, chỉ bonus): ghi `captured_at` của từng provider đã đọc; nếu câu trả lời cuối thiếu ngày của `captured_at` hoặc không nhắc 429/thử lại dù từng gặp thì nhắc một lần. Mục đích: sửa lỗi B3/B10 do chấm độc lập phát hiện.
- **`BONUS_RULES`.** Nối vào prompt chỉ khi bộ tools có `system_prompt` riêng nên bài chính không bị ảnh hưởng: gọi `get_incident_details` khi cần chi tiết; đọc tiếp theo `next_offset`; gọi lại ngay khi `retries_remaining > 0`; thiếu tool cho provider thì nói thiếu dữ liệu; nêu `captured_at` từng provider và việc đã gặp 429.

**Hành vi quan sát được trong trace:** B3 gọi Vercel hai lần (429 rồi thành công) và nêu 429, timestamp; B4 gọi Vercel đúng 3 lần rồi dừng, báo không biết trạng thái Vercel, và được cổng công bố nhắc bổ sung `captured_at` (vòng 1); B10 thử lại sau 429 (có lần cổng `validation_pending_retry` nhắc); B2 đọc nhiều trang timeline, cổng theo liên kết và công bố đều kích hoạt.

**Giới hạn còn lại:**
- Ngân sách 3 lần (`retry_budget_exhausted`) không được kích hoạt trong eval vì model tự dừng đúng; chỉ có unit test.
- 429 trong eval là giả lập (`retry_after_seconds` = 0); logic chờ theo `Retry-After` thật chỉ được kiểm tra bằng unit test với `time.sleep` giả.
- Cổng nguồn chỉ kiểm tra URL của `get_incident_details`; status tool chỉ trả trang chủ.
- B2 bị cổng nhắc hai lần (theo liên kết và công bố) nên tốn thêm model calls.
