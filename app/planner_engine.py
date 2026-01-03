import json
import requests
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from openai import OpenAI
from flask import current_app
from config import Config

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# DATA MODELS
# ============================================================================
@dataclass
class GeoPoint:
    lat: float
    lon: float

@dataclass
class EnhancedUserContext:
    location: GeoPoint
    preferences: Dict[str, Any]

# ============================================================================
# HELPER: PARSE DURATION
# ============================================================================
def parse_duration_to_minutes(duration_str: str) -> int:
    """
    Chuyển đổi chuỗi thời gian AI (VD: "1 tiếng 30 phút", "90p", "2h") thành số phút (int).
    """
    if not duration_str: 
        return 60 # Default 1 tiếng nếu AI không trả về
    
    d_str = duration_str.lower()
    total_minutes = 0
    
    # Regex bắt các pattern: 1h, 1 giờ, 1 tiếng
    hours = re.search(r'(\d+)\s*(?:h|giờ|tiếng)', d_str)
    if hours:
        total_minutes += int(hours.group(1)) * 60
        
    # Regex bắt các pattern: 30p, 30 phút, 30m
    minutes = re.search(r'(\d+)\s*(?:p|phút|m\b)', d_str)
    if minutes:
        total_minutes += int(minutes.group(1))
        
    # Nếu không match pattern nào nhưng là số nguyên (VD: "90") -> coi là phút
    if total_minutes == 0 and d_str.strip().isdigit():
        return int(d_str.strip())
        
    return total_minutes if total_minutes > 0 else 60

# ============================================================================
# 1. SEARCH ENGINE
# ============================================================================

class HybridSearcher:
    def _call_nominatim(self, query: str, lat: float, lon: float, use_viewbox: bool = True) -> Optional[Dict]:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': query,
            'format': 'json',
            'limit': 1,
            'addressdetails': 1,
            'accept_language': 'vi',
        }
        if use_viewbox:
            params['viewbox'] = f"{lon-0.2},{lat-0.2},{lon+0.2},{lat+0.2}"
            params['bounded'] = 1
        else:
            params['bounded'] = 0

        headers = {'User-Agent': 'FriendUS-Planner/2.2'} 
        
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=5)
            if resp.status_code == 200:
                results = resp.json()
                if results:
                    item = results[0]
                    addr_obj = item.get('address', {})
                    road = addr_obj.get('road', '')
                    suburb = addr_obj.get('suburb') or addr_obj.get('district') or addr_obj.get('city', '')
                    
                    if road:
                        display_addr = f"{road}, {suburb}"
                    else:
                        display_addr = item.get('display_name').split(',')[0] + f", {suburb}"

                    return {
                        'name': item.get('name') or query,
                        'address': display_addr,
                        'lat': float(item.get('lat')),
                        'lon': float(item.get('lon')),
                        'source': 'osm'
                    }
        except Exception as e:
            logger.error(f"Nominatim Error: {e}")
        return None

    def search(self, query: str, lat: float, lon: float) -> Dict:
        attempts = []
        base_query = query
        if "hồ chí minh" not in base_query.lower() and "hcm" not in base_query.lower():
            base_query += " Ho Chi Minh City"
        attempts.append(base_query)

        q2 = re.sub(r'Q(\d+)', r'Quận \1', query, flags=re.IGNORECASE)
        q2 = re.sub(r'Q\.(\d+)', r'Quận \1', q2, flags=re.IGNORECASE)
        if q2 != query:
            if "hồ chí minh" not in q2.lower(): q2 += " Ho Chi Minh City"
            attempts.append(q2)

        split_parts = query.split(" - ")
        if len(split_parts) > 1:
            attempts.append(split_parts[0] + " Ho Chi Minh City")
        
        # 1. Local Search
        for attempt_q in attempts:
            result = self._call_nominatim(attempt_q, lat, lon, use_viewbox=True)
            if result: return result

        # 2. Broad Search
        for attempt_q in attempts:
            result = self._call_nominatim(attempt_q, lat, lon, use_viewbox=False)
            if result: return result

        # 3. Fallback
        clean_name = query.split(' - ')[0]
        return {
            'name': clean_name,
            'address': f"{clean_name}, TP. Hồ Chí Minh",
            'lat': lat,
            'lon': lon,
            'source': 'ai_hallucination'
        }

# ============================================================================
# 2. SEALION PLANNER (LOGIC TÍNH GIỜ CỤ THỂ)
# ============================================================================

class SeaLionPlanner:
    def __init__(self):
        self.client = OpenAI(
            api_key=Config.SEALION_API_KEY, 
            base_url=Config.SEALION_BASE_URL
        )
        self.model_name = "aisingapore/Gemma-SEA-LION-v4-27B-IT"
        self.searcher = HybridSearcher()

    def generate_plan(self, user_prompt: str, context_data: Dict) -> Dict:
        # Lấy giờ bắt đầu từ input của user (VD: "09:00 - 17:00" -> lấy "09:00")
        time_range_str = context_data.get('time_range', '09:00 - 21:00')
        start_time_str = time_range_str.split('-')[0].strip()
        
        # Tạo object datetime để cộng dồn
        try:
            # Giả lập ngày hôm nay để tính toán giờ (chỉ quan tâm giờ phút)
            current_cursor = datetime.strptime(start_time_str, "%H:%M")
        except:
            current_cursor = datetime.strptime("09:00", "%H:%M")

        system_prompt = f"""
Bạn là trợ lý du lịch AI (Trip Planner).
Nhiệm vụ: Lên lịch trình cụ thể tại {context_data.get('location_pref', 'TP.HCM')}.

INPUT:
- Thời gian: {context_data.get('time_range')}
- Ngân sách: {context_data.get('budget')} | Nhóm: {context_data.get('companions')}
- YÊU CẦU: "{user_prompt}"

OUTPUT JSON (Bắt buộc):
[
  {{
    "search_query": "Tên địa điểm ngắn gọn (VD: Cơm tấm Ba Ghiền)", 
    "description": "Lý do chọn nơi này...",
    "estimated_duration": "Thời gian ở lại (VD: 60 phút, 1 tiếng 30 phút)" 
  }}
]
"""
        try:
            logger.info("--- Calling SeaLion AI ---")
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Lên lịch trình chi tiết đi."}
                ],
                temperature=0.4,
                max_tokens=1500
            )
            raw_content = response.choices[0].message.content.strip()
            
            if "```json" in raw_content:
                raw_content = raw_content.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_content:
                raw_content = raw_content.replace("```", "").strip()

            try:
                ai_steps = json.loads(raw_content)
            except json.JSONDecodeError:
                return {'steps': [], 'status': 'error', 'msg': 'AI trả về format không đúng.'}
            
            final_steps = []
            # Tọa độ mặc định ban đầu
            current_lat = context_data.get('lat', 10.762622) 
            current_lon = context_data.get('lon', 106.660172)

            for i, step in enumerate(ai_steps):
                # 1. Tính toán thời gian cụ thể
                duration_minutes = parse_duration_to_minutes(step.get('estimated_duration', '60 phút'))
                
                step_start = current_cursor
                step_end = current_cursor + timedelta(minutes=duration_minutes)
                
                # Format ra chuỗi HH:MM để trả về Frontend
                time_display_start = step_start.strftime("%H:%M")
                time_display_end = step_end.strftime("%H:%M")
                
                # Cập nhật con trỏ thời gian cho step tiếp theo (cộng thêm 15p di chuyển)
                current_cursor = step_end + timedelta(minutes=15)

                # 2. Tìm kiếm địa điểm
                place_info = self.searcher.search(step['search_query'], current_lat, current_lon)
                
                final_steps.append({
                    'step_number': i + 1,
                    'intent': step['description'],
                    'place': {
                        'name': place_info['name'],
                        'address': place_info['address'],
                        'lat': place_info['lat'],
                        'lon': place_info['lon']
                    },
                    'time': {
                        'start': time_display_start, # Bây giờ là giờ cụ thể (VD: 09:00)
                        'end': time_display_end      # VD: 10:30
                    },
                    'start_full': step_start.strftime('%Y-%m-%d %H:%M:%S') # Dữ liệu full để lưu DB
                })
                
                if place_info['source'] == 'osm':
                    current_lat = place_info['lat']
                    current_lon = place_info['lon']

            return {
                'steps': final_steps,
                'status': 'success'
            }

        except Exception as e:
            logger.error(f"Planner Processing Error: {e}")
            return {'steps': [], 'status': 'error', 'msg': str(e)}

class BeamSearchPlanner:
    def __init__(self):
        self.engine = SeaLionPlanner()
    
    def generate_plan(self, message: str, context: EnhancedUserContext) -> Dict[str, Any]:
        prefs = context.preferences or {}
        ctx_data = {
            'date': prefs.get('date', 'Hôm nay'),
            'time_range': prefs.get('time_range', '09:00 - 21:00'), # Default range
            'budget': prefs.get('budget', 'Vừa phải'),
            'companions': prefs.get('companions', 'Bạn bè'),
            'location_pref': prefs.get('location', 'TP.HCM'),
            'lat': context.location.lat,
            'lon': context.location.lon
        }
        return self.engine.generate_plan(message, ctx_data)