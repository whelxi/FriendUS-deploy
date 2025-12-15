from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import current_user, login_required
import requests
from app.extensions import db
from app.models import Location, Review
from app.forms import ReviewForm

map_bp = Blueprint('map', __name__)

@map_bp.route('/map')
@login_required
def map():
    return redirect(url_for('map.map_search'))

@map_bp.route('/map/search')
@login_required
def map_search():
    saved_locations = Location.query.all()
    locations_data = []
    for loc in saved_locations:
        locations_data.append({
            'id': loc.id, 
            'name': loc.name, 
            'desc': loc.description,
            'lat': loc.latitude, 
            'lon': loc.longitude,
            'url': url_for('map.location_detail', location_id=loc.id),
            'rating': 5.0 
        })
    
    # [FIX] Get the TILE KEY (safe for browser)
    tile_key = current_app.config.get('VIETMAP_TILE_KEY', '')
    
    # [NOTE] We pass it as 'vietmap_api_key' because your map.html 
    # already uses {{ vietmap_api_key }} in the template.
    return render_template('map.html', title='Map', 
                           locations_data=locations_data, 
                           vietmap_api_key=tile_key)

# --- HELPER: HEADERS ---
def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (compatible; MyMapApp/1.0)',
        'Accept': 'application/json'
    }

@map_bp.route('/map/api/search')
@login_required
def api_search():
    query = request.args.get('query', '')
    
    # [FIX] Get the SERVICE KEY (for backend search)
    service_key = current_app.config.get('VIETMAP_SERVICE_KEY', '')
    
    if not service_key:
        print("ERROR: VIETMAP_SERVICE_KEY is missing in config.")
        return jsonify({"error": "Missing Service Key"}), 500
    
    if not query: return jsonify([])

    url = "https://maps.vietmap.vn/api/autocomplete/v3"
    params = {
        'apikey': service_key,  # Use Service Key here
        'text': query
    }
    
    try:
        resp = requests.get(url, params=params, headers=get_headers(), timeout=10)
        
        if resp.status_code != 200:
            print(f"VietMap API Error [{resp.status_code}]: {resp.text}")
            return jsonify({"error": f"API Error {resp.status_code}"}), resp.status_code

        return jsonify(resp.json())
    except Exception as e:
        print(f"Search Exception: {e}")
        return jsonify({"error": str(e)}), 500
    
@map_bp.route('/map/api/route')
@login_required
def api_route():
    p1 = request.args.get('point1') 
    p2 = request.args.get('point2')
    
    service_key = current_app.config.get('VIETMAP_SERVICE_KEY', '')
    
    if not p1 or not p2:
        return jsonify({"error": "Missing coordinates"}), 400

    url = "https://maps.vietmap.vn/api/route"
    params = {
        'api-version': '1.1',
        'apikey': service_key,
        'point': [p1, p2], 
        'vehicle': 'car',
        'points_encoded': False  # [CRITICAL FIX] Request raw GeoJSON coordinates
    }
    
    try:
        resp = requests.get(url, params=params, headers=get_headers(), timeout=10)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@map_bp.route('/map/api/reverse')
@login_required
def api_reverse():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    
    # [FIX] Get the SERVICE KEY (for backend reverse geocoding)
    service_key = current_app.config.get('VIETMAP_SERVICE_KEY', '')

    if not lat or not lon: return jsonify([])

    url = "https://maps.vietmap.vn/api/reverse/v3"
    params = {
        'apikey': service_key, # Use Service Key here
        'lat': lat, 
        'lng': lon
    }
    
    try:
        resp = requests.get(url, params=params, headers=get_headers(), timeout=10)
        return jsonify(resp.json())
    except Exception as e:
        print(f"Reverse Exception: {e}")
        return jsonify([])

# ... (Remaining routes like location_detail keep existing logic) ...
@map_bp.route('/location/<int:location_id>', methods=['GET', 'POST'])
@login_required
def location_detail(location_id):
    location = Location.query.get_or_404(location_id)
    form = ReviewForm()
    is_favorited = current_user.favorite_locations.filter(Location.id == location.id).count() > 0
    if form.validate_on_submit():
        review = Review(body=form.body.data, rating=int(form.rating.data), author=current_user, location=location)
        db.session.add(review)
        db.session.commit()
        return redirect(url_for('map.location_detail', location_id=location.id))
    reviews = Review.query.filter_by(location=location).order_by(Review.timestamp.desc()).all()
    return render_template('location_detail.html', title=location.name, location=location, form=form, reviews=reviews, is_favorited=is_favorited)

@map_bp.route('/api/create_location_on_click', methods=['POST'])
@login_required
def create_location_on_click():
    data = request.json
    new_loc = Location(
        name=data['name'] or "Dropped Pin", description=f"Address: {data['address']}",
        latitude=data['lat'], longitude=data['lon'], type="Custom", price_range=0
    )
    db.session.add(new_loc)
    db.session.commit()
    return jsonify({'url': url_for('map.location_detail', location_id=new_loc.id)})

# ... inside map.py ...

@map_bp.route('/map/api/detail')
@login_required
def api_detail():
    ref_id = request.args.get('ref_id')
    service_key = current_app.config.get('VIETMAP_SERVICE_KEY', '')
    
    if not ref_id: return jsonify({"error": "No Ref ID"}), 400

    # Documentation: https://maps.vietmap.vn/api/place/v3
    url = "https://maps.vietmap.vn/api/place/v3"
    params = {
        'apikey': service_key, 
        'refid': ref_id
    }
    
    try:
        resp = requests.get(url, params=params, headers=get_headers(), timeout=10)
        return jsonify(resp.json())
    except Exception as e:
        print(f"Detail API Exception: {e}")
        return jsonify({"error": str(e)}), 500