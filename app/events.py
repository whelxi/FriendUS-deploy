from flask import request
from flask_socketio import emit, join_room, leave_room
from flask_login import current_user
from app.extensions import db, socketio
from app.models import Message, User, Room # Cần import Room

# Global state for online users (map: room_name -> {sid: username})
online_users_in_rooms = {}

def get_online_usernames(room_name):
    """Helper trả về list username đang online trong room"""
    if room_name in online_users_in_rooms:
        return list(set(online_users_in_rooms[room_name].values()))
    return []

def broadcast_user_list(room_name):
    """
    Hàm này lấy tất cả thành viên từ DB, so sánh với list online
    để phân loại Online/Offline và gửi về Client.
    """
    # [BẢO VỆ] Thêm try-except để tránh sập socket nếu DB mất kết nối tạm thời
    try:
        room = Room.query.filter_by(name=room_name).first()
        if not room:
            return

        # 1. Lấy tất cả thành viên từ DB
        all_members = [m.username for m in room.members]
        
        # 2. Lấy danh sách đang online từ biến toàn cục
        online_usernames = get_online_usernames(room_name)
        
        # 3. Tính toán offline (có trong DB nhưng không có trong list online)
        offline_members = list(set(all_members) - set(online_usernames))
        
        # Gửi về client object chứa cả 2 danh sách
        socketio.emit('user_list', {
            'online': online_usernames,
            'offline': offline_members,
            'total_count': len(all_members)
        }, to=room_name)
    except Exception as e:
        print(f"Error broadcasting user list: {e}")

def register_socketio_events(socketio):
    @socketio.on('connect')
    def handle_connect():
        if not current_user.is_authenticated: return False
        join_room(f"user_{current_user.id}")

    @socketio.on('join')
    def handle_join(data):
        if not current_user.is_authenticated: return
        room_name = data['room']
        
        if room_name not in online_users_in_rooms: 
            online_users_in_rooms[room_name] = {}
        
        # Clean up old connections for this user (nếu user refresh tab)
        current_sids = [sid for sid, user in online_users_in_rooms[room_name].items() if user == current_user.username]
        for old_sid in current_sids:
            del online_users_in_rooms[room_name][old_sid]

        online_users_in_rooms[room_name][request.sid] = current_user.username
        join_room(room_name)
        
        emit('status', {'msg': f'{current_user.username} has joined.'}, to=room_name)
        
        # Load lịch sử chat
        try:
            messages = Message.query.filter_by(room=room_name).order_by(Message.timestamp.asc()).limit(50).all()
            history = [{'msg': m.body, 'username': m.author.username, 'timestamp': m.timestamp.strftime('%Y-%m-%d %H:%M')} for m in messages]
            emit('load_history', history, to=request.sid)
        except Exception as e: print(f"Error history: {e}")
        
        # [NEW] Gửi danh sách Online/Offline
        broadcast_user_list(room_name)

    @socketio.on('send_message')
    def handle_send_message(data):
        if current_user.is_authenticated:
            try:
                new_msg = Message(body=data['msg'], room=data['room'], author=current_user)
                db.session.add(new_msg)
                db.session.commit()
                emit('receive_message', {
                    'msg': new_msg.body, 'username': new_msg.author.username,
                    'timestamp': new_msg.timestamp.strftime('%Y-%m-%d %H:%M')
                }, to=data['room'])
            except Exception: db.session.rollback()

    @socketio.on('leave')
    def handle_leave(data):
        if not current_user.is_authenticated: return
        room_name = data['room']
        leave_room(room_name)
        
        # Xóa user khỏi list online
        if room_name in online_users_in_rooms and request.sid in online_users_in_rooms[room_name]:
            username = online_users_in_rooms[room_name].pop(request.sid)
            emit('status', {'msg': f'{username} has left.'}, to=room_name)
            
            # [NEW] Cập nhật lại list
            broadcast_user_list(room_name)

    # --- [FIX QUAN TRỌNG] Sửa hàm handle_disconnect ---
    # Thêm *args để nhận bất kỳ tham số nào (EngineIO thường gửi lý do disconnect)
    # Khắc phục lỗi: "TypeError: handle_disconnect() takes 0 positional arguments but 1 was given"
    @socketio.on('disconnect')
    def handle_disconnect(*args):
        # Có thể không truy cập được current_user lúc disconnect nếu session đã chết
        # Nên dùng try-except hoặc kiểm tra kỹ
        try:
            if not current_user.is_authenticated: return
        except:
            return # Nếu lỗi truy cập user, thoát luôn

        for room_name, users in online_users_in_rooms.items():
            if request.sid in users:
                username = users.pop(request.sid)
                emit('status', {'msg': f'{username} has left.'}, to=room_name)
                
                # [NEW] Cập nhật lại list
                broadcast_user_list(room_name)
                break

    @socketio.on('typing')
    def handle_typing(data):
        if current_user.is_authenticated:
            emit('typing_status', {'username': current_user.username, 'isTyping': True}, to=data['room'], include_self=False)

    @socketio.on('stopped_typing')
    def handle_stopped_typing(data):
        if current_user.is_authenticated:
            emit('typing_status', {'username': current_user.username, 'isTyping': False}, to=data['room'], include_self=False)