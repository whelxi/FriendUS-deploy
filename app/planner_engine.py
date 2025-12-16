import math
import yaml
import time
import requests
import logging
import os
import json
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from flask import current_app

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

    def distance_to(self, other: 'GeoPoint') -> float:
        R = 6371
        dlat = math.radians(other.lat - self.lat)
        dlon = math.radians(other.lon - self.lon)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(self.lat)) * math.cos(math.radians(other.lat)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

@dataclass
class TimeSlot:
    start_time: datetime
    duration_min: int
    weather_conditions: Dict[str, float] = field(default_factory=dict)
    @property
    def end_time(self):
        return self.start_time + timedelta(minutes=self.duration_min)

@dataclass
class EnhancedPlace:
    id: str
    name: str
    address: str
    location: GeoPoint
    indoor: bool
    category: str
    rating: Optional[float] = None
    popularity: Optional[float] = None
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'lat': self.location.lat,
            'lon': self.location.lon,
            'category': self.category
        }

@dataclass
class EnhancedPlanStep:
    intent: str
    place: EnhancedPlace
    time_slot: TimeSlot
    travel_from_previous: Optional[Tuple[int, float]] = None
    score_components: Dict[str, float] = field(default_factory=dict)

@dataclass
class EnhancedUserContext:
    location: GeoPoint
    preferences: Dict[str, Any] = field(default_factory=dict)
    hourly_forecast: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class SearchState:
    steps: List[EnhancedPlanStep]
    score: float
    location: GeoPoint
    current_time: datetime
    visited_place_ids: Set[str]
    depth: int

# ============================================================================
# EXTERNAL SERVICES (VIETMAP API REAL)
# ============================================================================

class EnhancedVietmapClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def _get_place_detail(self, ref_id: str) -> Optional[GeoPoint]:
        """
        Bước 3: Dùng ref_id để gọi Place Detail V3 lấy tọa độ.
        Endpoint: /api/place/v3 
        """
        url = "https://maps.vietmap.vn/api/place/v3"
        params = {
            "apikey": self.api_key,
            "refid": ref_id
        }
        
        try:
            # print(f"   ... Step 3: Getting Detail for Ref ID: {ref_id} ...")
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # Place V3 có cấu trúc lat/lng trực tiếp hoặc trong location
                lat = data.get('lat') or data.get('location', {}).get('lat')
                lng = data.get('lng') or data.get('location', {}).get('lng')

                if lat and lng:
                    return GeoPoint(lat=float(lat), lon=float(lng))
            return None
        except Exception as e:
            print(f"   [PLACE DETAIL V3 ERROR] {e}")
            return None

    def _get_ref_id(self, text_query: str) -> Optional[str]:
        """
        Bước 2: Dùng địa chỉ/tên (từ V4) để gọi Search V3, lấy ref_id.
        Endpoint: /api/search (Search V3)
        """
        url = "https://maps.vietmap.vn/api/search"
        params = {
            "apikey": self.api_key,
            "text": text_query,
            "api-version": "1.1" 
        }
        
        try:
            # print(f"   ... Step 2: Geocoding/Search for Ref ID: '{text_query}' ...")
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    # Lấy ref_id của kết quả tốt nhất
                    return data[0].get('ref_id')
            return None
        except Exception as e:
            print(f"   [SEARCH V3 ERROR] {e}")
            return None


    def search(self, query: str, location: GeoPoint, radius_km: float = 5.0) -> List[EnhancedPlace]:
        """
        Quy trình 3 bước:
        1. Autocomplete V4 (lấy gợi ý tên)
        2. Search V3 (lấy ref_id)
        3. Place Detail V3 (lấy tọa độ)
        """
        url = "https://maps.vietmap.vn/api/autocomplete/v4"
        
        params = {
            "apikey": self.api_key,
            "text": query,
            "focus": f"{location.lat},{location.lon}", 
        }
        
        print(f"\n\033[94m--- [VIETMAP SEARCH] Query: '{query}' ---\033[0m")
        
        try:
            # --- BƯỚC 1: AUTOCOMPLETE V4 ---
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                print(f"\033[91m--- [V4 ERROR] Status: {response.status_code} ---\033[0m")
                return []
            
            data = response.json()
            items = data if isinstance(data, list) else data.get('data', [])
            
            # Limit top 3 để xử lý tọa độ
            top_items = items[:3]
            print(f"   Found {len(items)} raw items. Processing top {len(top_items)} items...")

            results = []
            for item in top_items:
                display_name = item.get('display', '')
                place_name = item.get('name')
                if not place_name:
                     place_name = display_name.split(',')[0] if display_name else query
                
                # Cố gắng lấy ref_id từ V4 trước
                ref_id = item.get('ref_id')

                geo_point = None
                
                # --- BƯỚC 2 & 3: Lấy tọa độ ---
                if not ref_id and display_name:
                    # Nếu V4 không có ref_id, gọi Search V3 để lấy ref_id
                    ref_id = self._get_ref_id(display_name)

                if ref_id:
                    # Dùng ref_id để gọi Place Detail V3 lấy tọa độ
                    geo_point = self._get_place_detail(ref_id)
                
                if not geo_point:
                    print(f"   -> Skip '{place_name}': Ref ID not found or Detail API failed.")
                    continue
                    
                place = EnhancedPlace(
                    id=ref_id,
                    name=place_name,
                    address=display_name,
                    location=geo_point,
                    indoor=self._guess_indoor(place_name, query),
                    category='general',
                    rating=0.0,
                    popularity=0.5
                )
                results.append(place)
                print(f"   -> Resolved: {place.name} (Ref ID: {ref_id}) at ({place.location.lat:.4f}, {place.location.lon:.4f})")
            
            return results
        except Exception as e:
            print(f"\033[91m--- [VIETMAP EXCEPTION] {e} ---\033[0m")
            return []

    def _guess_indoor(self, name: str, query: str) -> bool:
        keywords_indoor = ['mall', 'center', 'plaza', 'cafe', 'coffee', 'nhà hàng', 'restaurant', 'museum', 'bảo tàng', 'cinema', 'rạp']
        text = (name + " " + query).lower()
        return any(k in text for k in keywords_indoor)

    def route_time(self, loc1: GeoPoint, loc2: GeoPoint) -> int:
        dist = loc1.distance_to(loc2)
        return int((dist / 25) * 60) + 5

# ============================================================================
# FUZZY ENGINE & SCORER & PLANNER
# ============================================================================

class AdvancedFuzzyEngine:
    def infer(self, inputs: Dict[str, float]) -> Dict[str, float]:
        rain = inputs.get('rain_probability', 0)
        penalty = rain * 0.8
        return {'defuzzified': penalty}

class MultiFactorScorer:
    def __init__(self, fuzzy_engine):
        self.fuzzy_engine = fuzzy_engine
        self.weights = {'weather': 0.4, 'distance': 0.2, 'time_of_day': 0.2, 'popularity': 0.2}
        if current_app:
            self.weights = current_app.config.get('SCORING_WEIGHTS', self.weights)

    def calculate_total_score(self, step: EnhancedPlanStep, context: EnhancedUserContext, weather_data: Dict) -> Dict:
        weather_penalty = self.fuzzy_engine.infer(weather_data).get('defuzzified', 0)
        weather_score = 1.0 - weather_penalty if not step.place.indoor else 1.0
        dist_km = step.travel_from_previous[1] if step.travel_from_previous else 0
        dist_score = math.exp(-0.3 * dist_km)
        components = {'weather': weather_score, 'distance': dist_score, 'time_of_day': 0.8, 'popularity': 0.5, 'user_preference': 0.5}
        total = sum(components[k] * self.weights.get(k, 0.2) for k in components)
        return {'total': total}

class BeamSearchPlanner:
    def __init__(self):
        # API Key cứng
        api_key = "479e5176082849ab6eecaddfe6aaa28bdf9930e4ccf94245"
        self.map_client = EnhancedVietmapClient(api_key)
        self.fuzzy_engine = AdvancedFuzzyEngine()
        self.scorer = MultiFactorScorer(self.fuzzy_engine)

    def generate_plan(self, message: str, context: EnhancedUserContext) -> Dict[str, Any]:
        intents = self._parse_intents(message)
        
        start_time = datetime.now()
        if start_time.hour > 20:
             start_time = start_time.replace(hour=9, minute=0, second=0) + timedelta(days=1)

        initial_state = SearchState(
            steps=[], score=0.0, location=context.location,
            current_time=start_time, visited_place_ids=set(), depth=0
        )

        beam = [initial_state]
        
        for intent in intents:
            next_beam = []
            for state in beam:
                candidates = self.map_client.search(intent['text'], state.location)
                
                if not candidates:
                    candidates = [EnhancedPlace(
                        id=f"fallback_{intent['text']}",
                        name=f"Địa điểm: {intent['text']}",
                        address="Chưa xác định",
                        location=state.location,
                        indoor=True,
                        category='general'
                    )]

                for place in candidates:
                    if place.id in state.visited_place_ids:
                        continue

                    travel_min = self.map_client.route_time(state.location, place.location)
                    arrival_time = state.current_time + timedelta(minutes=travel_min)
                    weather_at_time = {'rain_probability': 0.1, 'temperature': 28}
                    
                    step = EnhancedPlanStep(
                        intent=intent['text'],
                        place=place,
                        time_slot=TimeSlot(start_time=arrival_time, duration_min=90),
                        travel_from_previous=(travel_min, state.location.distance_to(place.location))
                    )
                    
                    score_res = self.scorer.calculate_total_score(step, context, weather_at_time)
                    
                    new_state = SearchState(
                        steps=state.steps + [step],
                        score=state.score + score_res['total'],
                        location=place.location,
                        current_time=step.time_slot.end_time,
                        visited_place_ids=state.visited_place_ids | {place.id},
                        depth=state.depth + 1
                    )
                    next_beam.append(new_state)
            
            next_beam.sort(key=lambda x: x.score, reverse=True)
            beam_width = current_app.config.get('SEARCH_BEAM_WIDTH', 3)
            beam = next_beam[:beam_width]

        best_plan = beam[0] if beam else initial_state
        print(f"\n\033[95m--- [PLANNER RESULT] Best Plan Selected {len(best_plan.steps)} steps ---\033[0m")
        for step in best_plan.steps:
            print(f"   -> Step: {step.intent} => {step.place.name} ({step.place.address})")

        return self._format_plan(best_plan)

    def _parse_intents(self, message: str) -> List[Dict]:
        separators = [',', ' rồi ', ' sau đó ', ' và ', ' to ']
        temp_msg = message
        for sep in separators:
            temp_msg = temp_msg.replace(sep, '|')
        parts = [p.strip() for p in temp_msg.split('|') if p.strip()]
        return [{'text': p} for p in parts]

    def _format_plan(self, state: SearchState) -> Dict:
        steps_data = []
        for i, step in enumerate(state.steps):
            steps_data.append({
                'step_number': i + 1,
                'intent': step.intent,
                'place': step.place.to_dict(),
                'time': {
                    'start': step.time_slot.start_time.strftime('%H:%M'),
                    'end': step.time_slot.end_time.strftime('%H:%M'),
                    'start_full': step.time_slot.start_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'end_full': step.time_slot.end_time.strftime('%Y-%m-%d %H:%M:%S')
                },
                'travel_minutes': step.travel_from_previous[0] if step.travel_from_previous else 0
            })
        return {
            'steps': steps_data, 
            'total_score': state.score,
            'timestamp': datetime.now().isoformat()
        }