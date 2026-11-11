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
| Điểm tổng |  |  |
| Điểm case đã chọn |  |  |
| Số model calls |  |  |
| Token, chi phí nếu có |  |  |

- Lỗi đã giải quyết:
- Lỗi còn lại hoặc mới xuất hiện:

## 5. Giới hạn

Nêu giới hạn của điểm judge, của snapshot và của việc chỉ chạy một lần mỗi phiên bản.
