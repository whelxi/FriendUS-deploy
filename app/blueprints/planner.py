from flask import Blueprint, redirect, url_for, flash, render_template, request, jsonify, current_app
from flask_login import current_user, login_required
from app.extensions import db, socketio
from app.models import Room, Activity, Constraint
from app.forms import ActivityForm, ConstraintForm
from app.blueprints.weather import weather_service
from app.planner_engine import BeamSearchPlanner, EnhancedUserContext, GeoPoint
from datetime import datetime
import traceback

planner_bp = Blueprint('planner', __name__)

# =========================================================
# HELPER: PHÂN TÍCH TÁC ĐỘNG THỜI TIẾT
# =========================================================
def analyze_weather_impact(activities, weather_data):
    impacts = {}
    if not weather_data or 'five_day_forecast' not in weather_data:
        return impacts
    
    forecast_list = weather_data['five_day_forecast']
    for act in activities:
        act_warnings = []
        # Lấy ngày của Activity
        act_date_str = str(act.start_time).split(' ')[0] if act.start_time else ""
        matched_day = next((day for day in forecast_list if day['date'] == act_date_str), None)

        if matched_day:
            risks = matched_day.get('risks', [])
            is_outdoor = any(k in act.name.lower() for k in ['picnic', 'park', 'outdoor', 'bơi', 'dạo'])

            if 'RISK_HEAVY_RAIN' in risks:
                act_warnings.append({'level': 'critical', 'msg': f"☔ Mưa lớn ({matched_day['precipitation_sum']}mm)."})
            elif 'WARNING_LIGHT_RAIN' in risks and is_outdoor:
                act_warnings.append({'level': 'warning', 'msg': "🌧️ Có mưa nhẹ."})
            if 'RISK_EXTREME_HEAT' in risks:
                act_warnings.append({'level': 'warning', 'msg': "☀️ Nắng nóng >35°C."})

        if act_warnings:
            impacts[act.id] = act_warnings
    return impacts

def check_conflicts(activities, constraints):
    return {}

# =========================================================
# BACKGROUND TASK: AI PLANNER
# =========================================================
def generate_plan_background(app, room_id, message, lat, lon, preferences):
    """
    Chạy thuật toán Planner trong Thread riêng.
    Cần nhận 'app' object để push context.
    """
    with app.app_context():
        try:
            # 1. Khởi tạo Context
            context = EnhancedUserContext(
                location=GeoPoint(lat=lat, lon=lon),
                preferences=preferences
            )
            
            # 2. Chạy Planner
            planner = BeamSearchPlanner()
            result = planner.generate_plan(message, context)
            
            # 3. Gửi kết quả về Client
            socketio.emit('plan_generated', {
                'status': 'success',
                'room_id': room_id,
                'data': result
            }, room=f"planner_room_{room_id}")
            
        except Exception as e:
            print(f"Planning Error: {e}")
            traceback.print_exc()
            socketio.emit('plan_error', {
                'message': f"Lỗi hệ thống: {str(e)}"
            }, room=f"planner_room_{room_id}")

# =========================================================
# SOCKET EVENTS
# =========================================================

@socketio.on('join_planner')
def on_join_planner(data):
    from flask_socketio import join_room
    room_id = data.get('room_id')
    join_room(f"planner_room_{room_id}")

@socketio.on('request_ai_plan')
def on_request_ai_plan(data):
    """Client gửi yêu cầu -> Server chạy background task"""
    room_id = data.get('room_id')
    message = data.get('message')
    lat = data.get('lat', 10.762622) # Default HCM
    lon = data.get('lon', 106.660172)
    preferences = data.get('preferences', {})
    
    # Lấy real app object để tránh lỗi 'Working outside of application context'
    app = current_app._get_current_object()
    
    socketio.start_background_task(
        generate_plan_background, app, room_id, message, lat, lon, preferences
    )

@socketio.on('save_ai_plan')
def on_save_ai_plan(data):
    """Lưu kế hoạch vào Database"""
    room_id = data.get('room_id')
    plan_steps = data.get('plan_steps', [])

    # --- THÊM LOG ĐỂ CHECK DATA NHẬN ĐƯỢC ---
    print(f"\n\033[96m--- [SAVING PLAN TO DB] Room: {room_id} ---\033[0m")
    for idx, step in enumerate(plan_steps):
        print(f"   Step {idx+1}: Name='{step['place']['name']}' | Address='{step['place']['address']}'")
    # -----------------------------------------

    if not plan_steps:
        return
        
    try:
        room = Room.query.get(room_id)
        if not room:
            return

        for i, step in enumerate(plan_steps):
            # Ưu tiên lấy tên địa điểm tìm được, nếu fallback thì lấy intent
            place_name = step['place']['name']
            if "Địa điểm:" in place_name and "Chưa xác định" in step['place']['address']:
                 # Nếu là fallback place, ta đặt tên đẹp hơn chút
                 act_name = f"Hoạt động {i+1}"
            else:
                 act_name = place_name

            # Parse thời gian full datetime từ planner engine gửi về
            # Nếu planner engine chỉ gửi giờ, phải ghép với ngày hiện tại (hoặc ngày mai)
            time_info = step['time']
            if 'start_full' in time_info:
                start_dt = datetime.strptime(time_info['start_full'], '%Y-%m-%d %H:%M:%S')
                end_dt = datetime.strptime(time_info['end_full'], '%Y-%m-%d %H:%M:%S')
            else:
                # Fallback logic cũ
                today_str = datetime.now().strftime('%Y-%m-%d')
                start_dt = datetime.strptime(f"{today_str} {time_info['start']}", '%Y-%m-%d %H:%M')
                end_dt = datetime.strptime(f"{today_str} {time_info['end']}", '%Y-%m-%d %H:%M')

            new_act = Activity(
                name=act_name,
                location=step['place']['address'],
                price=0,
                start_time=start_dt,
                end_time=end_dt,
                rating=0,
                room_id=room.id
            )
            db.session.add(new_act)
            print(f"   -> Added to Session: {new_act.name}") # Log thêm dòng này
        
        db.session.commit()
        print("   -> COMMIT SUCCESS!")
        
        # Bắn event báo thành công -> Client reload trang
        socketio.emit('plan_saved_success', {'room_id': room_id}, room=f"planner_room_{room_id}")
        
    except Exception as e:
        db.session.rollback()
        print(f"Save DB Error: {e}")
        traceback.print_exc()
        socketio.emit('plan_error', {'message': 'Lỗi lưu dữ liệu.'}, room=f"planner_room_{room_id}")

# =========================================================
# HTTP ROUTES
# =========================================================

@planner_bp.route('/room/<int:room_id>/plan')
@login_required
def view_planner(room_id):
    room = Room.query.get_or_404(room_id)
    # Load activities & constraints
    activities = Activity.query.filter_by(room_id=room.id).order_by(Activity.start_time).all()
    for act in activities:
        if isinstance(act.start_time, str):
            try:
                # Thử parse format chuẩn ISO (có T) hoặc format SQL (có khoảng trắng)
                if 'T' in act.start_time:
                    act.start_time = datetime.strptime(act.start_time, '%Y-%m-%dT%H:%M')
                else:
                    act.start_time = datetime.strptime(act.start_time, '%Y-%m-%d %H:%M:%S')
            except:
                pass # Nếu lỗi quá thì chịu, template sẽ hiển thị raw string
        
        if isinstance(act.end_time, str):
            try:
                if 'T' in act.end_time:
                    act.end_time = datetime.strptime(act.end_time, '%Y-%m-%dT%H:%M')
                else:
                    act.end_time = datetime.strptime(act.end_time, '%Y-%m-%d %H:%M:%S')
            except:
                pass
    constraints = Constraint.query.filter_by(room_id=room.id, user_id=current_user.id).all()
    
    act_form = ActivityForm()
    cons_form = ConstraintForm()
    
    # Weather Forecast
    try:
        raw_weather = weather_service.get_full_forecast(lat=10.762622, lon=106.660172, days=7)
        weather_data = weather_service.process_forecast_data(raw_weather)
    except Exception as e:
        weather_data = None

    conflicts = check_conflicts(activities, constraints)
    weather_impacts = analyze_weather_impact(activities, weather_data)

    return render_template(
        'planner.html',
        room=room,
        activities=activities,
        constraints=constraints,
        act_form=act_form,
        cons_form=cons_form,
        conflicts=conflicts,
        weather=weather_data,
        weather_impacts=weather_impacts
    )

@planner_bp.route('/room/<int:room_id>/add_activity', methods=['POST'])
@login_required
def add_room_activity(room_id):
    room = Room.query.get_or_404(room_id)
    name = request.form.get('name')
    location = request.form.get('location')
    price = request.form.get('price', 0)
    start_str = request.form.get('start_time') # Dạng '2025-12-16T14:30'
    end_str = request.form.get('end_time')

    try:
        # [FIX] Parse chuỗi thành datetime object
        start_dt = datetime.strptime(start_str, '%Y-%m-%dT%H:%M') if start_str else None
        end_dt = datetime.strptime(end_str, '%Y-%m-%dT%H:%M') if end_str else None
        
        new_act = Activity(
            name=name,
            location=location,
            price=float(price) if price else 0,
            start_time=start_dt,
            end_time=end_dt,
            rating=0,
            room=room
        )
        db.session.add(new_act)
        db.session.commit()
        flash('Đã thêm hoạt động!', 'success')
        
    except ValueError as e:
        flash(f'Lỗi định dạng ngày tháng: {e}', 'danger')
    except Exception as e:
        flash(f'Lỗi hệ thống: {e}', 'danger')
        
    return redirect(url_for('planner.view_planner', room_id=room.id))

@planner_bp.route('/delete_activity/<int:id>')
@login_required
def delete_activity(id):
    act = Activity.query.get_or_404(id)
    room_id = act.room.id
    db.session.delete(act)
    db.session.commit()
    return redirect(url_for('planner.view_planner', room_id=room_id))

@planner_bp.route('/room/<int:room_id>/add_constraint', methods=['POST'])
@login_required
def add_room_constraint(room_id):
    room = Room.query.get_or_404(room_id)
    form = ConstraintForm()
    if form.validate_on_submit():
        new_cons = Constraint(type=form.type.data, intensity=form.intensity.data, value=form.value.data, user=current_user, room_id=room.id)
        db.session.add(new_cons)
        db.session.commit()
    return redirect(url_for('planner.view_planner', room_id=room.id))

@planner_bp.route('/delete_constraint/<int:id>')
@login_required
def delete_constraint(id):
    cons = Constraint.query.get_or_404(id)
    room_id = cons.room.id
    if cons.user_id == current_user.id:
        db.session.delete(cons)
        db.session.commit()
    return redirect(url_for('planner.view_planner', room_id=room_id))