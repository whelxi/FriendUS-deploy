import json
import re
from typing import List, Dict
from openai import OpenAI
from config import Config


class SeaLionDialogueSystem:
    def __init__(self):
        # Giữ nguyên cách khởi tạo bảo mật từ file new
        self.client = OpenAI(
            api_key=Config.SEALION_API_KEY,
            base_url=Config.SEALION_BASE_URL
        )
        self.model_name = "aisingapore/Gemma-SEA-LION-v4-27B-IT"

    def _call_model(self, prompt: str, system_prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,  # Giảm nhiệt độ để Output ổn định hơn (đặc biệt là JSON)
                max_tokens=2048
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Lỗi API SeaLion: {e}"

    def _clean_json_output(self, raw_string: str):
        """Hàm phụ trợ để làm sạch chuỗi JSON do AI sinh ra (xử lý Markdown)"""
        try:
            # Xóa các ký tự markdown như ```json hoặc ```
            clean_str = re.sub(r"```json|```", "", raw_string).strip()
            return clean_str
        except:
            return raw_string

    # --- STAGE 1: COREFERENCE & NORMALIZATION (Theo ai_summary.py) ---
    def stage_1_cleansing(self, chat_history: List[Dict]) -> str:
        # Chuyển đổi List[Dict] thành chuỗi hội thoại thô
        chat_str = "\n".join([f"{msg['speaker']}: {msg['text']}" for msg in chat_history])

        sys_prompt = """Nhiệm vụ: Giải quyết Coreference và Chuẩn hóa văn bản.
1. Thay thế tất cả đại từ (nó, họ, m, t, hắn...) bằng danh từ/tên riêng tương ứng trong ngữ cảnh.
2. Chuyển teencode/viết tắt thành tiếng Việt chuẩn.
ĐẦU RA: Chỉ trả về nội dung chat đã làm sạch, định dạng 'Tên: Nội dung'."""

        return self._call_model(chat_str, sys_prompt)

    # --- STAGE 2: DIALOGUE ACT TAGGING (Theo ai_summary.py) ---
    def stage_2_tagging(self, clean_chat: str) -> str:
        sys_prompt = """Đóng vai trò là công cụ Chat Corpora Annotator (CCA). 
Gán nhãn 'Dialogue Act' cho từng câu thoại để xây dựng cấu trúc tĩnh (Static Structure):
- REQUEST: Đưa ra đề xuất/câu hỏi.
- INFORM: Cung cấp sự thật/thông tin.
- ADVISE: Đưa ra lời khuyên/ý kiến.
- RESPOND: Phản hồi đồng ý (ACCEPT) hoặc từ chối (REJECT).
- RESOLVE: Chốt hạ vấn đề.

ĐẦU RA JSON duy nhất: [{"s": "Tên người", "a": "Nhãn hành động", "t": "Nội dung"}]"""

        result = self._call_model(clean_chat, sys_prompt)
        return self._clean_json_output(result)

    # --- STAGE 3: DYNAMIC SEGMENTATION (Theo ai_summary.py) ---
    def stage_3_segmentation(self, tagged_json: str) -> str:
        sys_prompt = """Dựa trên các nhãn Dialogue Act, hãy thực hiện Dynamic Topic Segmentation.
Gom nhóm các câu thoại liên quan thành các 'Sự việc' (Events).
Với mỗi sự việc, xác định:
1. Topic: Tên vụ việc.
2. Initiator: Người khơi mào.
3. Interaction Flow: Luồng thảo luận (Ai phản đối ai, ai cung cấp thêm tin).
4. Status: Kết quả cuối cùng (Đã chốt/Chưa chốt).

ĐẦU RA JSON: {"events": [{"topic": "...", "flow": "...", "status": "..."}]}"""

        result = self._call_model(tagged_json, sys_prompt)
        return self._clean_json_output(result)

    # --- STAGE 4: ABSTRACTIVE SUMMARY GENERATION (Theo ai_summary.py) ---
    def stage_4_summarization(self, segments_json: str) -> str:
        sys_prompt = """Bạn là một thành viên trong nhóm, tóm tắt lại nội dung buổi trò chuyện hôm nay cho những người 'lặn' lâu không đọc tin nhắn.
Văn phong: Thân thiện, hài hước, sử dụng ngôn ngữ của giới trẻ (nhưng vẫn dễ hiểu). Có thể dùng emoji phù hợp.

CẤU TRÚC BÁO CÁO:
🔥 CÓ GÌ HOT: (Tóm tắt nhanh những drama hoặc sự kiện nổi bật nhất)
💬 CHI TIẾT CÁC KÈO: 
   - [Tên kèo/vụ]: Kể lại ngắn gọn ai đã nói gì, chốt hạ ra sao. 
✅ VIỆC CẦN LÀM: (Liệt kê danh sách ai cần làm gì, ví dụ: 'Thằng Nam nhớ mang tiền', 'Tối nay 7h tập trung'...)"""

        return self._call_model(segments_json, sys_prompt)

    # --- MAIN PROCESS (PAPER PIPELINE) ---
    def process(self, raw_chat: List[Dict]):
        # Pipeline thực thi tuần tự 4 bước theo paper
        s1_clean = self.stage_1_cleansing(raw_chat)
        s2_tagged = self.stage_2_tagging(s1_clean)
        s3_segments = self.stage_3_segmentation(s2_tagged)
        s4_final = self.stage_4_summarization(s3_segments)
        return s4_final

    # --- SIMPLE PROCESS (Giữ lại từ file new) ---
    def simple_process(self, raw_chat: List[Dict]) -> str:
        chat_str = "\n".join([f"{msg['speaker']}: {msg['text']}" for msg in raw_chat])
        sys_prompt = """
Bạn là trợ lý ảo tổng hợp tin nhắn nhóm.
Nhiệm vụ: Đọc đoạn hội thoại và tóm tắt lại 3 ý chính quan trọng nhất một cách ngắn gọn, súc tích.
Không cần phân tích sâu, chỉ cần nắm bắt thông tin bề mặt nhanh chóng."""

        return self._call_model(f"Hội thoại:\n{chat_str}", sys_prompt)