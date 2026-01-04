from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import current_user, login_required
from app.extensions import db, socketio
from app.models import Room, Message, Activity, Constraint, Transaction, User, RoomRequest 
from app.forms import CreateRoomForm, ActivityForm, ConstraintForm, TransactionForm
from app.utils import auto_update_user_interest, score_from_matrix_personalized, check_conflicts, UserTagScore
from app.ai_summary import SeaLionDialogueSystem 
import requests
import os
import time

# [LƯU Ý] Không cần import torch, transformers, peft nữa vì chạy qua API

chat_bp = Blueprint('chat', __name__)

# --- CẤU HÌNH API HUGGING FACE ---
# Đây là đường dẫn API Inference miễn phí của Hugging Face
API_URL = "https://api-inference.huggingface.co/models/whelxi/bartpho-teencode"

# ⚠️ BẠN CẦN LẤY TOKEN CỦA BẠN: https://huggingface.co/settings/tokens
# Nên để trong biến môi trường, nhưng nếu test thì điền trực tiếp vào đây
HF_TOKEN = os.environ.get("HF_TOKEN")

headers = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}

def query_huggingface_api(payload):
    """
    Hàm gửi request lên Hugging Face Server
    """
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        return response.json()
    except Exception as e:
        print(f"API Connection Error: {e}")
        return {"error": str(e)}

@chat_bp.route('/api/suggest-text', methods=['POST'])
def suggest_text():
    data = request.json
    input_text = data.get('text', '')
    
    if not input_text:
        return jsonify({'suggestion': ''})

    # Cấu hình tham số gửi đi (giống như model.generate)
    payload = {
        "inputs": input_text,
        "parameters": {
            "max_length": 128,
            "num_beams": 4,
            "early_stopping": True,
            "length_penalty": 1.0,
            "wait_for_model": True # Bắt buộc server HF chờ load model nếu model đang ngủ
        }
    }

    print(f"☁️ Calling HF API for: {input_text}")
    
    # Gọi API
    api_response = query_huggingface_api(payload)
    
    # Xử lý kết quả trả về từ API
    # API thường trả về list: [{'generated_text': 'Kết quả...'}]
    try:
        if isinstance(api_response, list) and len(api_response) > 0:
            if 'generated_text' in api_response[0]:
                suggestion = api_response[0]['generated_text']
                return jsonify({'suggestion': suggestion})
        
        # Xử lý trường hợp model đang load (Cold boot)
        if isinstance(api_response, dict) and 'error' in api_response:
            err_msg = api_response['error']
            print(f"❌ HF API Error: {err_msg}")
            
            if "loading" in err_msg.lower():
                return jsonify({'suggestion': 'Đang khởi động AI, vui lòng thử lại sau 20s...'})
                
        return jsonify({'suggestion': ''})

    except Exception as e:
        print(f"❌ Parse Error: {e}")
        return jsonify({'suggestion': ''})

# ... (GIỮ NGUYÊN PHẦN CÒN LẠI CỦA FILE TỪ route /chat/summary TRỞ XUỐNG) ...

@chat_bp.route('/chat/summary/<int:room_id>', methods=['GET'])
@login_required
def get_chat_summary(room_id):
    # ... (Giữ nguyên code cũ) ...
    mode = request.args.get('mode', 'normal') 
    room = Room.query.get_or_404(room_id)
    # ... Copy y nguyên đoạn dưới từ file cũ ...
    if room.is_private and current_user not in room.members:
        return {"error": "Unauthorized"}, 403

    messages = Message.query.filter_by(room=room.name)\
                            .order_by(Message.timestamp.desc())\
                            .limit(40).all()
    
    messages.reverse()
    
    if not messages:
        return {"short": "Chưa có tin nhắn", "full": "Chưa có nội dung để tóm tắt"}

    chat_history = [{"speaker": msg.author.username, "text": msg.body} for msg in messages]

    try:
        sealion = SeaLionDialogueSystem()
        if mode == 'paper':
            final_report = sealion.process(chat_history)
            short_msg = "🦁 SeaLion (Paper Mode) đã phân tích sâu hội thoại!"
        else:
            final_report = sealion.simple_process(chat_history)
            short_msg = "⚡ AI Recap (Fast Mode) đã tóm tắt nhanh!"

        return {
            "short": short_msg,
            "full": final_report
        }
    except Exception as e:
        print(f"AI Error: {e}")
        return {"short": "Lỗi AI", "full": "Hệ thống đang bận, vui lòng thử lại sau."}

@chat_bp.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    # ... (Giữ nguyên toàn bộ logic chat lobby) ...
    form = CreateRoomForm()
    if form.validate_on_submit():
        is_private_bool = True if form.privacy.data == 'private' else False
        tags_str = ",".join(form.tags.data) if form.tags.data else ""
        new_room = Room(name=form.name.data, description=form.description.data, is_private=is_private_bool, allow_auto_join=form.allow_auto_join.data, tags=tags_str, creator=current_user)
        new_room.members.append(current_user)
        db.session.add(new_room)
        db.session.commit()
        return redirect(url_for('chat.chat_room', room_name=new_room.name))

    my_rooms = current_user.rooms.all()
    my_room_ids = [r.id for r in my_rooms]
    raw_public_rooms = Room.query.filter(Room.is_private == False).filter(Room.id.notin_(my_room_ids)).all()
    current_user_scores = UserTagScore.query.filter_by(user_id=current_user.id).all()
    
    import random
    if request.args.get('sort') == 'match':
        ranked_rooms = []
        for room in raw_public_rooms:
            room_tags = room.tags.split(',') if room.tags else []
            score = score_from_matrix_personalized(current_user.id, room_tags, user_scores_cache=current_user_scores)
            ranked_rooms.append((room, score))
        ranked_rooms.sort(key=lambda x: x[1], reverse=True)
        public_rooms = [x[0] for x in ranked_rooms] 
        flash('✨ Algorithm activated! Rooms sorted by compatibility.', 'success')
    else:
        public_rooms = raw_public_rooms
        random.shuffle(public_rooms)
    
    my_requests = RoomRequest.query.filter_by(user_id=current_user.id).all()
    pending_room_ids = [req.room_id for req in my_requests]
    my_invitations = RoomRequest.query.filter_by(user_id=current_user.id, status='pending_user').all()
    return render_template('chat_lobby.html', title='Chat Lobby', form=form, my_rooms=my_rooms, public_rooms=public_rooms, pending_room_ids=pending_room_ids, my_invitations=my_invitations)

@chat_bp.route('/chat/<string:room_name>', methods=['GET'])
@login_required
def chat_room(room_name):
    # ... (Giữ nguyên logic chat room) ...
    room = Room.query.filter_by(name=room_name).first_or_404()
    if room.is_private and current_user not in room.members:
        flash('This is a private room. You need an invitation to join.', 'danger')
        return redirect(url_for('chat.chat'))
    if current_user not in room.members and not room.is_private:
        room.members.append(current_user)
        db.session.commit()
        flash(f'Joined room: {room.name}', 'info')
    
    current_member_ids = [m.id for m in room.members]
    invitable_friends = []
    seen_ids = set() 
    for friend in current_user.friends: 
        if friend.id not in current_member_ids and friend.id not in seen_ids:
            invitable_friends.append(friend)
            seen_ids.add(friend.id)

    act_form = ActivityForm()
    cons_form = ConstraintForm()
    activities = Activity.query.filter_by(room_id=room.id).all()
    timeline_data = [{'name': a.name, 'start': a.start_time, 'end': a.end_time} for a in activities]
    my_constraints = Constraint.query.filter_by(user_id=current_user.id, room_id=room.id).all()
    conflicts = check_conflicts(activities, my_constraints)
    trans_form = TransactionForm()
    trans_form.receiver.choices = [(m.id, m.username) for m in room.members if m.id != current_user.id] or [(0, 'No other members')]
    pending_trans = Transaction.query.filter_by(room_id=room.id, receiver_id=current_user.id, status='pending').all()
    history_trans = Transaction.query.filter(Transaction.room_id == room.id).filter((Transaction.sender_id == current_user.id) | (Transaction.receiver_id == current_user.id)).order_by(Transaction.timestamp.desc()).all()
    pending_requests = []
    if current_user.id == room.creator_id:
        pending_requests = RoomRequest.query.filter_by(room_id=room.id, status='pending_owner').all()
    
    return render_template('chat_room.html', title=f'Trip: {room.name}', room=room, act_form=act_form, cons_form=cons_form, activities=activities, timeline_data=timeline_data, constraints=my_constraints, conflicts=conflicts, trans_form=trans_form, pending_trans=pending_trans, history_trans=history_trans, invitable_friends=invitable_friends, pending_requests=pending_requests)

@chat_bp.route('/chat/invite/<int:room_id>', methods=['POST'])
@login_required
def invite_to_room(room_id):
    # ... (Giữ nguyên) ...
    room = Room.query.get_or_404(room_id)
    if current_user not in room.members: return redirect(url_for('chat.chat'))
    friend_ids = request.form.getlist('friend_ids')
    for f_id in friend_ids:
        user_to_invite = User.query.get(int(f_id))
        existing_req = RoomRequest.query.filter_by(room_id=room.id, user_id=user_to_invite.id).first()
        if existing_req: continue
        if user_to_invite and user_to_invite not in room.members:
            if current_user.id == room.creator_id:
                req = RoomRequest(room_id=room.id, user_id=user_to_invite.id, inviter_id=current_user.id, status='pending_user')
                db.session.add(req)
                socketio.emit('new_invitation', {'msg': f'{current_user.username} invited you to {room.name}'}, to=f"user_{user_to_invite.id}")
                flash(f'Invitation sent to {user_to_invite.username}.', 'success')
            else:
                req = RoomRequest(room_id=room.id, user_id=user_to_invite.id, inviter_id=current_user.id, status='pending_owner')
                db.session.add(req)
                socketio.emit('new_request', {'msg': f'{current_user.username} wants to invite {user_to_invite.username}'}, to=f"user_{room.creator_id}")
                flash(f'Request to invite {user_to_invite.username} sent to room owner.', 'info')
    db.session.commit()
    return redirect(url_for('chat.chat_room', room_name=room.name))

@chat_bp.route('/chat/delete/<int:room_id>', methods=['POST'])
@login_required
def delete_chat_room(room_id):
    # ... (Giữ nguyên) ...
    room_to_delete = Room.query.get_or_404(room_id)
    if room_to_delete.creator != current_user:
        flash('You do not have permission to delete this room.', 'danger')
        return redirect(url_for('chat.chat'))
    try:
        Message.query.filter_by(room=room_to_delete.name).delete()
        db.session.delete(room_to_delete)
        db.session.commit()
        flash(f'Room "{room_to_delete.name}" has been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting room: {e}', 'danger')
    return redirect(url_for('chat.chat'))

@chat_bp.route('/chat/leave/<int:room_id>', methods=['POST'])
@login_required
def leave_chat_room(room_id):
    # ... (Giữ nguyên) ...
    room = Room.query.get_or_404(room_id)
    if room.creator_id == current_user.id:
        flash('Owner cannot leave the room. Please delete the room if you wish to disband it.', 'danger')
        return redirect(url_for('chat.chat_room', room_name=room.name))
    if current_user in room.members:
        room.members.remove(current_user)
        db.session.commit()
        socketio.emit('status', {'msg': f'{current_user.username} left the group.'}, to=room.name)
        flash(f'You have left the room "{room.name}".', 'warning')
    return redirect(url_for('chat.chat'))

@chat_bp.route('/chat/join_request/<int:room_id>', methods=['POST'])
@login_required
def request_join_room(room_id):
    # ... (Giữ nguyên) ...
    room = Room.query.get_or_404(room_id)
    if current_user in room.members:
        flash('You are already in this room.', 'info')
        return redirect(url_for('chat.chat'))
    if room.allow_auto_join:
        room.members.append(current_user)
        if room.tags:
            tags_list = room.tags.split(',')
            auto_update_user_interest(current_user.id, tags_list, weight_increment=2.0)
        sys_msg = Message(body=f"has joined the room directly.", room=room.name, author=current_user)
        db.session.add(sys_msg)
        db.session.commit()
        socketio.emit('status', {'msg': f'{current_user.username} joined.'}, to=room.name)
        flash(f'Welcome aboard! You have joined {room.name}.', 'success')
        return redirect(url_for('chat.chat_room', room_name=room.name))
    existing_req = RoomRequest.query.filter_by(user_id=current_user.id, room_id=room.id).first()
    if existing_req:
        flash('Request already pending.', 'warning')
        return redirect(url_for('chat.chat'))
    req = RoomRequest(room_id=room.id, user_id=current_user.id, status='pending_owner')
    db.session.add(req)
    sys_msg = Message(body=f"System: {current_user.username} wants to join this room.", room=room.name, user_id=current_user.id) 
    db.session.add(sys_msg)
    db.session.commit()
    flash('Join request sent to the room owner.', 'success')
    return redirect(url_for('chat.chat'))

@chat_bp.route('/chat/manage_request/<int:req_id>/<string:action>', methods=['POST'])
@login_required
def manage_request(req_id, action):
    # ... (Giữ nguyên) ...
    req = RoomRequest.query.get_or_404(req_id)
    room = Room.query.get(req.room_id)
    if room.creator_id != current_user.id:
        flash('Only the room owner can manage these requests.', 'danger')
        return redirect(url_for('chat.chat_room', room_name=room.name))
    if action == 'accept':
        if req.inviter_id is None:
            room.members.append(req.user)
            db.session.delete(req) 
            if room.tags:
                tags_list = room.tags.split(',')
                auto_update_user_interest(req.user_id, tags_list, weight_increment=2.0)
            db.session.commit()
            socketio.emit('request_approved', {'room_id': room.id, 'room_name': room.name, 'msg': f'Welcome! Your request to join {room.name} has been approved.'}, to=f"user_{req.user_id}")
            flash(f'Approved {req.user.username} to join the room.', 'success')
        else:
            req.status = 'pending_user'
            db.session.commit()
            socketio.emit('new_invitation', {'msg': f'You have been invited to join {room.name} (Approved by owner)'}, to=f"user_{req.user_id}")
            flash(f'Request approved. Invitation sent to {req.user.username}.', 'success')
    elif action == 'reject':
        db.session.delete(req)
        db.session.commit()
        flash('Request rejected.', 'secondary')
    return redirect(url_for('chat.chat_room', room_name=room.name))

@chat_bp.route('/chat/respond_invite/<int:req_id>/<string:action>', methods=['POST'])
@login_required
def respond_invite(req_id, action):
    # ... (Giữ nguyên) ...
    req = RoomRequest.query.get_or_404(req_id)
    if req.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('chat.chat'))
    room = Room.query.get(req.room_id)
    if action == 'accept':
        room.members.append(current_user)
        db.session.delete(req) 
        if room.tags:
            tags_list = room.tags.split(',')
            auto_update_user_interest(current_user.id, tags_list, weight_increment=2.0)
        msg = Message(body=f"joined the room via invitation.", room=room.name, author=current_user)
        db.session.add(msg)
        db.session.commit()
        socketio.emit('status', {'msg': f'{current_user.username} joined.'}, to=room.name)
        flash(f'You joined {room.name}.', 'success')
        return redirect(url_for('chat.chat_room', room_name=room.name))
    elif action == 'reject':
        db.session.delete(req)
        db.session.commit()
        flash(f'You declined the invitation to {room.name}.', 'secondary')
    return redirect(url_for('chat.chat'))