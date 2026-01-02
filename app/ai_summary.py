import json
from typing import List, Dict
from openai import OpenAI
from config import Config

class SeaLionDialogueSystem:
    def __init__(self):
        # Lấy Key từ Config bảo mật
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
                temperature=0.1,
                max_tokens=2048
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Lỗi API SeaLion: {e}"

    # --- BƯỚC 1: CHUẨN HÓA (TEENCODE/SLANG) ---
    def normalize_text(self, chat_history: List[Dict]) -> List[Dict]:
        chat_str = "\n".join([f"{i}|{msg['speaker']}: {msg['text']}" for i, msg in enumerate(chat_history)])
        sys_prompt = """
Bạn là một chuyên gia ngôn ngữ học về tiếng lóng và văn hóa mạng Việt Nam. 
Nhiệm vụ: Chuyển đổi đoạn hội thoại sau sang tiếng Việt chuẩn mực.

CÁC RÀNG BUỘC NGHIÊM NGẶT:
1. KHÔNG ĐƯỢC BỎ SÓT bất kỳ từ teencode nào (vd: j, k, ko, đc, s, vcl, clgt, bít, m, t...).
2. GIỮ NGUYÊN cấu trúc ID|Speaker: Text.
3. Nếu gặp từ không hiểu, hãy giữ nguyên nhưng cố gắng đoán dựa trên ngữ cảnh xung quanh.
4. Đảm bảo số dòng đầu ra bằng chính xác số dòng đầu vào.

INPUT FORMAT: ID|Speaker: Text"""

        result = self._call_model(f"Dữ liệu:\n{chat_str}", sys_prompt)
        
        normalized_chat = []
        for line in result.split('\n'):
            if "|" in line and ":" in line:
                try:
                    parts = line.split("|")
                    idx = int(parts[0])
                    text = line.split(":", 1)[1].strip()
                    msg = chat_history[idx].copy()
                    msg['norm_text'] = text
                    normalized_chat.append(msg)
                except:
                    continue
        return normalized_chat if normalized_chat else chat_history

    # --- BƯỚC 2: GIẢI QUYẾT ĐỒNG THAM CHIẾU (COREFERENCE) ---
    def coreference_resolution(self, chat_history: List[Dict]) -> List[Dict]:
        chat_str = "\n".join(
            [f"{i}|{msg['speaker']}: {msg.get('norm_text', msg['text'])}" for i, msg in enumerate(chat_history)])
        sys_prompt = """
Bạn là chuyên gia phân tích ngữ cảnh hội thoại (Coreference Resolution).
Nhiệm vụ: Thay thế TẤT CẢ các đại từ nhân xưng mơ hồ bằng tên riêng của thực thể mà chúng ám chỉ.

DANH SÁCH KIỂM TRA (CHECKLIST):
- 'nó', 'hắn', 'ổng', 'bả', 'em nó' -> Thay bằng tên người cụ thể.
- 'đó', 'kia', 'ấy' (khi chỉ sự vật/sự việc đã nói ở trên) -> Thay bằng tên sự việc cụ thể.
- Ví dụ: "Bình: Nó không cho mượn" -> "Bình: Minh không cho mượn" (nếu ngữ cảnh trước đó là Minh).

YÊU CẦU: Phải rà soát từng câu một. Nếu câu nào không có đại từ, giữ nguyên. 
TRẢ VỀ ĐỊNH DẠNG: ID|Text đã thay thế."""

        result = self._call_model(f"Đoạn chat:\n{chat_str}", sys_prompt)
        
        for line in result.split('\n'):
            if "|" in line:
                try:
                    parts = line.split("|")
                    idx = int(parts[0])
                    resolved_text = parts[1].strip()
                    chat_history[idx]['coref_text'] = resolved_text
                except:
                    continue
        return chat_history

    # --- BƯỚC 3: PHÂN ĐOẠN CHỦ ĐỀ (TOPIC SEGMENTATION) ---
    def dynamic_topic_segmentation(self, chat_history: List[Dict]) -> str:
        chat_content = "\n".join(
            [f"{msg['speaker']}: {msg.get('coref_text', msg.get('norm_text'))}" for msg in chat_history])
        sys_prompt = """
Bạn là một người chuyên đi 'hóng hớt' và kể lại chuyện trong group chat cho bạn bè. 
Hãy đọc đoạn chat và chia nhỏ xem hội thoại này gồm những 'kèo' nào hoặc những 'vụ' nào đang hot.

YÊU CẦU JSON:
{
  "segments": [
    {
      "topic_name": "Tên vụ việc (ví dụ: Kèo đi nhậu, Drama thằng Nam...)",
      "whats_happening": "Chuyện gì đang xảy ra vậy? (Kể lại kiểu thân thiện)",
      "main_characters": ["Những ai tham gia vụ này"]
    }
  ]
}"""
        result = self._call_model(chat_content, sys_prompt)
        return result

    # --- BƯỚC 4: TỔNG HỢP ---
    def process(self, raw_chat: List[Dict]):
        # Pipeline xử lý
        chat_norm = self.normalize_text(raw_chat)
        chat_coref = self.coreference_resolution(chat_norm)
        topics_json = self.dynamic_topic_segmentation(chat_coref)

        sys_prompt = """
Bạn là một thành viên trong nhóm, tóm tắt lại nội dung buổi trò chuyện hôm nay cho những người 'lặn' lâu không đọc tin nhắn.
Văn phong: Thân thiện, hài hước, sử dụng ngôn ngữ của giới trẻ (nhưng vẫn dễ hiểu). Có thể dùng emoji phù hợp.

CẤU TRÚC BÁO CÁO:
🔥 CÓ GÌ HOT: (Tóm tắt nhanh những drama hoặc sự kiện nổi bật nhất)
💬 CHI TIẾT CÁC KÈO: 
   - [Tên kèo/vụ]: Kể lại ngắn gọn ai đã nói gì, chốt hạ ra sao. 
✅ VIỆC CẦN LÀM: (Liệt kê danh sách ai cần làm gì, ví dụ: 'Thằng Nam nhớ mang tiền', 'Tối nay 7h tập trung'...)"""
        
        final_summary = self._call_model(f"Dữ liệu:\n{topics_json}", sys_prompt)
        return final_summary