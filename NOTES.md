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
- **Vì sao chọn thay đổi này:** H1 và H6 cùng mắc lỗi dừng trước khi theo liên kết và mỗi case mất 40 điểm vì trần code, nên một thay đổi có thể cải thiện cả hai. Bản prompt đầu ("hãy gọi...") chưa đủ: chạy thử H1 vẫn 60. Bản "PHẢI gọi... ở lượt kế tiếp" đưa H1 lên 95.
- **Kết quả test offline:** 37/37 pass (kể cả `tests/test_validation.py`).

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | 92,14 | **95,86** (+3,72) |
| Điểm case đã chọn | H1 = 60 (H6 = 60) | H1 = **100** (H6 = **95**) |
| Số model calls | 49 (tổng 22 case; H1 = 2) | 54 (H1 = 3) |
| Token, chi phí nếu có | 36.460 token của agent (chưa tính token của judge) | 46.625 token của agent (+28%; chưa tính token của judge) |

Cả hai lần dùng cùng cấu hình (khối `config` giống hệt): provider `openai`, model `gpt-4.1-mini`, judge cùng provider và model, `max_steps` = 8, dataset `core`. Cả 22 case đều được chấm ở hai lần.

Chênh lệch theo case (chỉ liệt kê case có đổi điểm): H1 60→100, H6 60→95, A5 88→100, A7 94→100, H7 75→80, E5 100→94, H8 100→90. Các case còn lại không đổi.

- **Lỗi đã giải quyết:** **H1**. Ở lần 2, model gọi `get_incident_details` cho `xr3myzj7ms51` ở step 2 nên đủ 2 model steps có tool call, hết vi phạm `grade.mechanical`. Cổng nguồn cũng chạy ngoài đời: event `validation_missing_source` xuất hiện ở H6 và E5, và model đã sửa câu trả lời trong ngân sách `max_steps`.
- **Lỗi còn lại hoặc mới xuất hiện:**
  - **H6 = 95 nhưng nội dung vẫn sai.** Model theo link nhưng chép sai ID thành `xr3myzjms51` (thiếu chữ `7`), nhận `INCIDENT_NOT_FOUND` và không thử lại dù prompt đã dặn. Câu trả lời kết luận sai rằng incident gộp không nằm trong 50 incident gần nhất. Lỗi này lặp lại ở cả hai lần chạy thử, nên có vẻ ổn định. Điểm cao vì kiểm tra bằng code chỉ đếm số step, còn judge chấm 95.
  - **H2 = 50, không đổi.** Agent chỉ gọi `get_incident_details`, không gọi `get_status`, nên bị trần 50 (`Chưa gọi tool cần thiết: get_status`). Nằm ngoài phạm vi thay đổi.
  - **H7 = 80 (lần 1: 75).** Cloudflare timeout nhưng agent vẫn viết "tôi kết luận Cloudflare Spectrum đang hoạt động bình thường" theo yêu cầu của người dùng; judge tự ghi là bịa kết luận nhưng vẫn cho 80.
  - **E5 100→94 và H8 100→90.** Không có vi phạm từ kiểm tra bằng code. E5 có thêm một lượt vì cổng nguồn (calls 2→4). H8 không đổi số calls (2→2) và không liên quan thay đổi của tôi, nên nhiều khả năng là dao động của model hoặc judge.
  - **Chi phí tăng:** +5 model calls và +10.165 token (+28%), một phần do cổng nguồn bắt viết lại và do model gọi thêm tool theo link.

## 5. Giới hạn

- **Điểm judge là ước lượng.** Judge dùng cùng model với agent (`gpt-4.1-mini`) nên có thể thiên lệch. Ví dụ ở lần 1: H7 được chấm 75 dù judge tự ghi agent "không tuân thủ expected" (Cloudflare timeout nhưng vẫn kết luận operational), và A5 được chấm 88 dù câu trả lời đổi năm 2026 thành 2025. Ngược lại H1 có judge cho 96 nhưng bị trần 60 bởi kiểm tra bằng code, nên điểm cuối phụ thuộc nhiều vào `grade.mechanical`.
- **Snapshot cố định.** Dữ liệu chụp lúc 2026-11-09T03:50:47Z và chỉ gồm 50 incident gần nhất; tìm theo chuỗi gần đúng nên tìm không thấy không chứng minh incident không tồn tại. Kết quả không phản ánh trạng thái thực tế hiện tại.
- **Chỉ chạy một lần mỗi phiên bản.** Model có tính ngẫu nhiên, nên chênh lệch điểm giữa hai lần chưa đủ để kết luận cải tiến ổn định. Chỉ H1 và H6 có nguyên nhân rõ ràng gắn với thay đổi (có trace chứng minh). Các thay đổi ở A5 (+12), A7 (+6), H7 (+5), E5 (-6) và H8 (-10) không có cơ chế tương ứng trong thay đổi nên khả năng cao là dao động ngẫu nhiên; vì vậy không thể nói toàn bộ +3,72 điểm là do cải tiến. Mức tăng chắc chắn nhất là H1 (+40) và H6 (+35), tương đương khoảng +3,4 điểm tổng.
- **Điểm cao không bằng nội dung đúng.** H6 đạt 95 dù chép sai ID incident và kết luận sai. Kiểm tra bằng code chỉ đếm số step, còn judge cùng model với agent không phát hiện lỗi này.
- **Prompt không bảo đảm hành vi.** Quy tắc "thử lại khi `INCIDENT_NOT_FOUND`" không được model tuân thủ. Muốn chắc chắn cần cơ chế trong code (ví dụ gợi ý lại ID đúng từ URL đã quan sát), chưa làm trong bài này.
- **Kiểm tra nguồn chỉ kiểm tra sự hiện diện của một URL**, không chứng minh mọi nhận định đều có nguồn.
