import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
from flask import Blueprint, jsonify, request, render_template
from app.models import Room

weather_bp = Blueprint('weather', __name__)

# ==============================================================================
# CLASS CLIENT
# ==============================================================================
class OpenMeteoClient:
    BASE_URL = "https://api.open-meteo.com/v1/forecast"
    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

    DEFAULT_DAILY_VARS = ['temperature_2m_max', 'temperature_2m_min', 'precipitation_sum', 'weathercode', 'wind_speed_10m_max']
    DEFAULT_HOURLY_VARS = ['temperature_2m', 'weathercode', 'is_day']
    DEFAULT_CURRENT_VARS = ['temperature_2m', 'is_day', 'precipitation', 'weather_code', 'wind_speed_10m']

    def __init__(self, default_timezone: str = 'Asia/Ho_Chi_Minh'):
        self.default_timezone = default_timezone

    def _map_weather_code(self, wmo_code: int) -> str:
        if wmo_code in [0, 1]: return "Trời quang"
        elif wmo_code == 2: return "Mây rải rác"
        elif wmo_code == 3: return "Nhiều mây"
        elif wmo_code in [45, 48]: return "Sương mù"
        elif wmo_code in [51, 61, 63, 65]: return "Mưa nhỏ"
        elif wmo_code in [80, 81, 82]: return "Mưa rào"
        elif wmo_code in [95, 96, 99]: return "Dông bão"
        return "Khác"

    def _analyze_daily_risk(self, temp_max: float, temp_min: float, precip_sum: float, wind_max: float) -> List[str]:
        risks = []
        if precip_sum > 5.0: risks.append("RISK_HEAVY_RAIN")
        elif precip_sum >= 0.5: risks.append("WARNING_LIGHT_RAIN")
        if temp_max > 35.0: risks.append("RISK_EXTREME_HEAT")
        elif temp_min < 15.0: risks.append("WARNING_CHILLY")
        if wind_max > 30.0: risks.append("RISK_HIGH_WIND")
        return risks if risks else ["NORMAL"]

    # --- [QUAN TRỌNG] HÀM TÌM KIẾM TRẢ VỀ DANH SÁCH ---
    def search_locations(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Trả về danh sách tối đa 5 địa điểm."""
        try:
            params = {'name': query, 'count': limit, 'language': 'en', 'format': 'json'}
            response = requests.get(self.GEOCODING_URL, params=params)
            data = response.json()
            results = []
            if 'results' in data and data['results']:
                for item in data['results']:
                    # Tạo tên hiển thị đầy đủ: "Paris, Ile-de-France, FR"
                    parts = [item.get('name')]
                    if item.get('admin1'): parts.append(item.get('admin1'))
                    if item.get('country_code'): parts.append(item.get('country_code'))
                    
                    results.append({
                        'name': ", ".join(parts),
                        'lat': item['latitude'],
                        'lon': item['longitude'],
                        'flag': item.get('country_code', '').lower() 
                    })
            return results
        except Exception as e:
            print(f"Search error: {e}")
            return []

    def get_full_forecast(self, lat: float, lon: float) -> Dict[str, Any]:
        params = {
            'latitude': lat, 'longitude': lon,
            'current': ",".join(self.DEFAULT_CURRENT_VARS),
            'daily': ",".join(self.DEFAULT_DAILY_VARS),
            'hourly': ",".join(self.DEFAULT_HOURLY_VARS), 
            'timezone': self.default_timezone,
            'forecast_days': 3, 'temperature_unit': 'celsius', 'wind_speed_unit': 'kmh'
        }
        try:
            response = requests.get(self.BASE_URL, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    def process_forecast_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        if 'error' in raw_data: return raw_data
        daily = raw_data.get('daily', {})
        current = raw_data.get('current', {})
        hourly = raw_data.get('hourly', {})

        t_max = daily['temperature_2m_max'][0] if daily.get('time') else 0
        t_min = daily['temperature_2m_min'][0] if daily.get('time') else 0
        precip = daily['precipitation_sum'][0] if daily.get('time') else 0
        w_max = daily['wind_speed_10m_max'][0] if daily.get('time') else 0
        risks = self._analyze_daily_risk(t_max, t_min, precip, w_max)

        current_obj = {
            'temperature': current.get('temperature_2m'),
            'weather_desc': self._map_weather_code(current.get('weather_code', 0)),
            'daily_risks': risks,
            'precipitation_sum': precip,
            'wind_max_kmh': current.get('wind_speed_10m', 0),
            'temp_max': t_max,
            'temp_min': t_min
        }

        processed_hourly = []
        now = datetime.now()
        if hourly.get('time'):
            times = hourly['time']
            temps = hourly['temperature_2m']
            codes = hourly['weathercode']
            for i in range(len(times)):
                try:
                    time_str = times[i]
                    item_dt = datetime.strptime(time_str, "%Y-%m-%dT%H:%M")
                    if item_dt >= now or (now - item_dt).total_seconds() < 3600:
                        processed_hourly.append({
                            'hour': item_dt.strftime("%H:%M"),
                            'temp': temps[i],
                            'weather_desc': self._map_weather_code(codes[i]),
                            'full_time': time_str
                        })
                    if len(processed_hourly) >= 24: break
                except ValueError: continue

        return {
            'current_weather': current_obj,
            'hourly_forecast': processed_hourly
        }

weather_service = OpenMeteoClient(default_timezone='Asia/Ho_Chi_Minh')

# ==============================================================================
# ROUTE HANDLERS
# ==============================================================================

@weather_bp.route('/<int:room_id>', methods=['GET'])
def view_weather(room_id):
    room = Room.query.get_or_404(room_id)
    # Mặc định render trang với HCM City
    lat, lon = 10.8231, 106.6297
    display_location = "Hồ Chí Minh, VN"
    
    raw_data = weather_service.get_full_forecast(lat, lon)
    weather_data = weather_service.process_forecast_data(raw_data)

    return render_template('weather.html', room=room, weather=weather_data, location_name=display_location)

# --- [QUAN TRỌNG] API TÌM KIẾM ĐỊA ĐIỂM (ĐÂY LÀ HÀM BẠN ĐANG THIẾU) ---
@weather_bp.route('/api/search', methods=['GET'])
def search_city():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    results = weather_service.search_locations(query)
    return jsonify(results)

# --- API LẤY THỜI TIẾT THEO TỌA ĐỘ ---
@weather_bp.route('/api/forecast', methods=['GET'])
def get_forecast():
    # Frontend giờ sẽ gửi lat/lon trực tiếp sau khi user chọn từ list
    lat = float(request.args.get('lat', 10.8231))
    lon = float(request.args.get('lon', 106.6297))
    
    # Frontend gửi kèm tên hiển thị để Backend trả lại (hoặc Frontend tự render)
    location_name = request.args.get('name', 'Hồ Chí Minh, VN')

    raw_data = weather_service.get_full_forecast(lat, lon)
    result = weather_service.process_forecast_data(raw_data)
    result['location_name'] = location_name
    
    return jsonify(result)