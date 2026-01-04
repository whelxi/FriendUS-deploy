from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import current_user, login_required
from app.extensions import db, socketio
from app.models import Room, Message, Activity, Constraint, Transaction, User, RoomRequest 
from app.forms import CreateRoomForm, ActivityForm, ConstraintForm, TransactionForm
from app.utils import auto_update_user_interest, score_from_matrix_personalized, check_conflicts, UserTagScore
from app.ai_summary import SeaLionDialogueSystem 
import requests
import os
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
# [FIX] Cần import PeftModel để chạy Adapter
from peft import PeftModel 

chat_bp = Blueprint('chat', __name__)

# --- CẤU HÌNH MODEL ---
# Sử dụng cấu hình giống test.py đã chạy thành công
BASE_MODEL_ID = "vinai/bartpho-syllable"
ADAPTER_MODEL_ID = "whelxi/bartpho-teencode" 

# Biến global cache
local_tokenizer = None
local_model = None

def get_model_and_tokenizer():
    """
    Load model chuẩn theo quy trình Peft/LoRA:
    1. Load Tokenizer
    2. Load Base Model (BartPho)
    3. Load Peft Adapter (Teencode)
    """
    global local_tokenizer, local_model
    
    if local_model is None:
        print("🔄 Đang khởi tạo model dịch Teencode (Local)...")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        try:
            # 1. Load Tokenizer (Lấy từ adapter path vẫn ok, hoặc lấy từ base đều được)
            print(f"⏳ Loading Tokenizer từ {ADAPTER_MODEL_ID}...")
            local_tokenizer = AutoTokenizer.from_pretrained(ADAPTER_MODEL_ID)
            
            # 2. Load Base Model (Bắt buộc phải có cái này trước)
            print(f"⏳ Loading Base Model từ {BASE_MODEL_ID}...")
            base_model = AutoModelForSeq2SeqLM.from_pretrained(
                BASE_MODEL_ID,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32
            )
            
            # 3. Gắn Adapter vào Base Model
            print(f"🔗 Đang gắn LoRA Adapter từ {ADAPTER_MODEL_ID}...")
            local_model = PeftModel.from_pretrained(base_model, ADAPTER_MODEL_ID)
            
            # 4. Chuyển sang thiết bị (GPU/CPU)
            local_model.to(device)
            local_model.eval() # Chuyển sang chế độ eval
            
            print(f"✅ Load model thành công trên thiết bị: {device}")
            
        except Exception as e:
            print(f"❌ Lỗi load model local: {e}")
            return None, None
            
    return local_tokenizer, local_model

@chat_bp.route('/api/suggest-text', methods=['POST'])
def suggest_text():
    data = request.json
    input_text = data.get('text', '')
    
    if not input_text:
        return jsonify({'suggestion': ''})

    # Lấy model đã load
    tokenizer, model = get_model_and_tokenizer()
    
    if not model or not tokenizer:
        return jsonify({'suggestion': 'Lỗi: Không load được model'})

    try:
        device = model.device
        
        # 1. Chuẩn bị input (giống hàm normalize_teencode trong test.py)
        inputs = tokenizer(
            input_text, 
            return_tensors="pt", 
            max_length=128, 
            truncation=True,
            padding="max_length" # Thêm padding giống test.py để ổn định
        ).to(device)
        
        # 2. Generate (Sinh văn bản)
        with torch.no_grad():
            outputs = model.generate(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                max_length=128,
                num_beams=4,           
                early_stopping=True,
                length_penalty=1.0 
            )
        
        # 3. Decode kết quả
        suggestion = tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        return jsonify({'suggestion': suggestion})

    except Exception as e:
        print(f"Local Inference Error: {e}")
        return jsonify({'suggestion': ''})

@chat_bp.route('/chat/summary/<int:room_id>', methods=['GET'])
@login_required
def get_chat_summary(room_id):
    mode = request.args.get('mode', 'normal') # Mặc định là normal
    room = Room.query.get_or_404(room_id)
    
    # Check quyền truy cập (nếu private)
    if room.is_private and current_user not in room.members:
        return {"error": "Unauthorized"}, 403

    # Lấy 40 tin nhắn gần nhất
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
            # Paper Version: Deep Processing (Normalize -> Coref -> Topic)
            final_report = sealion.process(chat_history)
            short_msg = "🦁 SeaLion (Paper Mode) đã phân tích sâu hội thoại!"
        else:
            # Normal Version: Fast Summarization
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
    form = CreateRoomForm()
    if form.validate_on_submit():
        is_private_bool = True if form.privacy.data == 'private' else False
        tags_str = ",".join(form.tags.data) if form.tags.data else ""
        
        # [NEW] Thêm tham số allow_auto_join lấy từ form
        new_room = Room(
            name=form.name.data, 
            description=form.description.data, 
            is_private=is_private_bool, 
            allow_auto_join=form.allow_auto_join.data, # <--- Dòng mới
            tags=tags_str, 
            creator=current_user
        )
        new_room.members.append(current_user)
        db.session.add(new_room)
        db.session.commit()
        return redirect(url_for('chat.chat_room', room_name=new_room.name))

    my_rooms = current_user.rooms.all()
    my_room_ids = [r.id for r in my_rooms]
    raw_public_rooms = Room.query.filter(Room.is_private == False).filter(Room.id.notin_(my_room_ids)).all()

    # [TỐI ƯU] Lấy sở thích user 1 lần duy nhất
    current_user_scores = UserTagScore.query.filter_by(user_id=current_user.id).all()

    # [DEMO ALGORITHM] Chỉ chạy thuật toán khi bấm nút tìm kiếm
    import random
    if request.args.get('sort') == 'match':
        ranked_rooms = []
        for room in raw_public_rooms:
            room_tags = room.tags.split(',') if room.tags else []
            # Truyền list sở thích vào đây
            score = score_from_matrix_personalized(current_user.id, room_tags, user_scores_cache=current_user_scores)
            ranked_rooms.append((room, score))
        
        # Sort giảm dần theo điểm (Matching)
        ranked_rooms.sort(key=lambda x: x[1], reverse=True)
        public_rooms = [x[0] for x in ranked_rooms] 
        flash('✨ Algorithm activated! Rooms sorted by compatibility.', 'success')
    else:
        # Mặc định: Trộn ngẫu nhiên (Linh tinh) để chứng minh chưa sort
        public_rooms = raw_public_rooms
        random.shuffle(public_rooms)
    
    # Check các phòng đang chờ owner duyệt (để hiện status Pending)
    my_requests = RoomRequest.query.filter_by(user_id=current_user.id).all()
    pending_room_ids = [req.room_id for req in my_requests]

    # [NEW] Lấy danh sách lời mời gửi đến TÔI (B) đang chờ TÔI đồng ý
    # Status = 'pending_user' nghĩa là Creator đã duyệt hoặc Creator mời trực tiếp
    my_invitations = RoomRequest.query.filter_by(user_id=current_user.id, status='pending_user').all()

    return render_template('chat_lobby.html', title='Chat Lobby', form=form, 
                           my_rooms=my_rooms, 
                           public_rooms=public_rooms,
                           pending_room_ids=pending_room_ids,
                           my_invitations=my_invitations) # Truyền biến này ra Lobby

@chat_bp.route('/chat/<string:room_name>', methods=['GET'])
@login_required
def chat_room(room_name):
    room = Room.query.filter_by(name=room_name).first_or_404()
    
    if room.is_private and current_user not in room.members:
        flash('This is a private room. You need an invitation to join.', 'danger')
        return redirect(url_for('chat.chat'))
    
    # Logic Auto-join cũ cho Public room (User tự vào không cần duyệt)
    # Nếu bạn muốn Public cũng phải duyệt thì comment đoạn này lại
    if current_user not in room.members and not room.is_private:
        room.members.append(current_user)
        db.session.commit()
        flash(f'Joined room: {room.name}', 'info')

    # 1. Lấy danh sách ID thành viên đang có trong phòng
    current_member_ids = [m.id for m in room.members]

    # 2. Lọc danh sách bạn bè (SỬA ĐOẠN NÀY ĐỂ CHỐNG LẶP)
    invitable_friends = []
    seen_ids = set() # Tạo một tập hợp để lưu các ID đã kiểm tra

    for friend in current_user.friends: 
        # Logic lọc:
        # - friend.id not in current_member_ids: Chưa tham gia phòng
        # - friend.id not in seen_ids: Chưa có trong danh sách mời (Chống lặp)
        if friend.id not in current_member_ids and friend.id not in seen_ids:
            invitable_friends.append(friend)
            seen_ids.add(friend.id) # Đánh dấu ID này đã được thêm

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
    
    timeline_data = []
    for act in activities:
        timeline_data.append({
            'name': act.name,
            'start': act.start_time,
            'end': act.end_time
        })

    my_constraints = Constraint.query.filter_by(user_id=current_user.id, room_id=room.id).all()
    conflicts = check_conflicts(activities, my_constraints)

    # --- FINANCE DATA --- (Giữ nguyên code cũ)
    trans_form = TransactionForm()
    # Cập nhật choices cho receiver (chỉ hiện thành viên khác)
    trans_form.receiver.choices = [(m.id, m.username) for m in room.members if m.id != current_user.id]
    if not trans_form.receiver.choices: trans_form.receiver.choices = [(0, 'No other members')]

    pending_trans = Transaction.query.filter_by(room_id=room.id, receiver_id=current_user.id, status='pending').all()
    history_trans = Transaction.query.filter(Transaction.room_id == room.id).filter(
        (Transaction.sender_id == current_user.id) | (Transaction.receiver_id == current_user.id)
    ).order_by(Transaction.timestamp.desc()).all()

    pending_requests = []
    if current_user.id == room.creator_id:
        pending_requests = RoomRequest.query.filter_by(room_id=room.id, status='pending_owner').all()
    
    return render_template('chat_room.html', title=f'Trip: {room.name}', room=room,
                           act_form=act_form, cons_form=cons_form, activities=activities, timeline_data=timeline_data,
                           constraints=my_constraints, conflicts=conflicts,
                           trans_form=trans_form, pending_trans=pending_trans, history_trans=history_trans,
                           invitable_friends=invitable_friends, pending_requests=pending_requests)

# [CHECK] Hàm invite_to_room của bạn logic đã đúng hướng, 
# nhưng hãy đảm bảo giữ nguyên logic phân chia Creator/Member như sau:
@chat_bp.route('/chat/invite/<int:room_id>', methods=['POST'])
@login_required
def invite_to_room(room_id):
    room = Room.query.get_or_404(room_id)
    if current_user not in room.members: return redirect(url_for('chat.chat'))

    friend_ids = request.form.getlist('friend_ids')
    for f_id in friend_ids:
        user_to_invite = User.query.get(int(f_id))
        
        # Check if request already exists
        existing_req = RoomRequest.query.filter_by(room_id=room.id, user_id=user_to_invite.id).first()
        if existing_req: continue

        if user_to_invite and user_to_invite not in room.members:
            # Nếu là Creator mời: Gửi thẳng cho B (B chỉ cần đồng ý) -> status: pending_user
            if current_user.id == room.creator_id:
                req = RoomRequest(room_id=room.id, user_id=user_to_invite.id, inviter_id=current_user.id, status='pending_user')
                db.session.add(req)
                socketio.emit('new_invitation', {'msg': f'{current_user.username} invited you to {room.name}'}, to=f"user_{user_to_invite.id}")
                flash(f'Invitation sent to {user_to_invite.username}.', 'success')
            
            # Nếu là Member (C) mời: Cần Creator duyệt -> status: pending_owner
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
    room = Room.query.get_or_404(room_id)
    
    # Không cho phép chủ phòng rời phòng (Chủ phòng phải xóa phòng hoặc chuyển quyền - ở đây ta chặn rời)
    if room.creator_id == current_user.id:
        flash('Owner cannot leave the room. Please delete the room if you wish to disband it.', 'danger')
        return redirect(url_for('chat.chat_room', room_name=room.name))

    if current_user in room.members:
        room.members.remove(current_user)
        db.session.commit()
        
        # Gửi thông báo socket là user này đã thoát hẳn
        socketio.emit('status', {'msg': f'{current_user.username} left the group.'}, to=room.name)
        # Cập nhật lại danh sách member cho những người còn lại
        from app.events import broadcast_user_list # Import hàm helper chúng ta sẽ viết ở events.py
        broadcast_user_list(room.name)

        flash(f'You have left the room "{room.name}".', 'warning')
    
    return redirect(url_for('chat.chat'))

# [NEW] User tự xin tham gia phòng Public
@chat_bp.route('/chat/join_request/<int:room_id>', methods=['POST'])
@login_required
def request_join_room(room_id):
    room = Room.query.get_or_404(room_id)
    if current_user in room.members:
        flash('You are already in this room.', 'info')
        return redirect(url_for('chat.chat'))
    
    # [LOGIC MỚI] Nếu phòng cho phép Auto Join -> Vào thẳng luôn
    if room.allow_auto_join:
        room.members.append(current_user)
        
        # Cập nhật sở thích AI (User thích phòng này)
        if room.tags:
            tags_list = room.tags.split(',')
            auto_update_user_interest(current_user.id, tags_list, weight_increment=2.0)

        # Thông báo vào phòng
        sys_msg = Message(body=f"has joined the room directly.", room=room.name, author=current_user)
        db.session.add(sys_msg)
        db.session.commit()
        
        # Bắn socket cập nhật danh sách
        socketio.emit('status', {'msg': f'{current_user.username} joined.'}, to=room.name)
        
        flash(f'Welcome aboard! You have joined {room.name}.', 'success')
        return redirect(url_for('chat.chat_room', room_name=room.name))

    # --- LOGIC CŨ (Cần duyệt) ---
    # Kiểm tra xem đã gửi yêu cầu chưa
    existing_req = RoomRequest.query.filter_by(user_id=current_user.id, room_id=room.id).first()
    if existing_req:
        flash('Request already pending.', 'warning')
        return redirect(url_for('chat.chat'))

    # Tạo yêu cầu mới -> Chờ chủ phòng duyệt
    req = RoomRequest(room_id=room.id, user_id=current_user.id, status='pending_owner')
    db.session.add(req)
    
    sys_msg = Message(body=f"System: {current_user.username} wants to join this room.", 
                      room=room.name, user_id=current_user.id) 
    db.session.add(sys_msg)
    
    db.session.commit()
    flash('Join request sent to the room owner.', 'success')
    return redirect(url_for('chat.chat'))

@chat_bp.route('/chat/manage_request/<int:req_id>/<string:action>', methods=['POST'])
@login_required
def manage_request(req_id, action):
    req = RoomRequest.query.get_or_404(req_id)
    room = Room.query.get(req.room_id)
    
    # Chỉ chủ phòng mới được duyệt status 'pending_owner'
    if room.creator_id != current_user.id:
        flash('Only the room owner can manage these requests.', 'danger')
        return redirect(url_for('chat.chat_room', room_name=room.name))

    if action == 'accept':
        # --- [LOGIC MỚI] ---
        # TRƯỜNG HỢP 1: User tự xin vào (Join Request) -> Không có người mời (inviter_id is None)
        # Hành động: Thêm thẳng vào phòng luôn.
        if req.inviter_id is None:
            room.members.append(req.user)
            db.session.delete(req) # Xóa request vì đã hoàn tất
            
            # (Tùy chọn) Cập nhật sở thích cho User vì đã được vào phòng
            if room.tags:
                tags_list = room.tags.split(',')
                auto_update_user_interest(req.user_id, tags_list, weight_increment=2.0)

            db.session.commit()
            
            # Gửi thông báo SocketIO để User biết mình đã được vào (nếu đang online)
            socketio.emit('request_approved', {
                'room_id': room.id, 
                'room_name': room.name,
                'msg': f'Welcome! Your request to join {room.name} has been approved.'
            }, to=f"user_{req.user_id}")
            
            flash(f'Approved {req.user.username} to join the room.', 'success')

        # TRƯỜNG HỢP 2: Thành viên C mời User B (Invitation) -> Có người mời
        # Hành động: Duyệt xong thì gửi lời mời chính thức cho B (B cần Accept)
        else:
            req.status = 'pending_user'
            db.session.commit()
            
            # Gửi thông báo SocketIO cho User B
            socketio.emit('new_invitation', {
                'msg': f'You have been invited to join {room.name} (Approved by owner)'
            }, to=f"user_{req.user_id}")
            
            flash(f'Request approved. Invitation sent to {req.user.username}.', 'success')
        
    elif action == 'reject':
        db.session.delete(req)
        db.session.commit()
        flash('Request rejected.', 'secondary')
        
    return redirect(url_for('chat.chat_room', room_name=room.name))

# [NEW] User (B) phản hồi lời mời (Accept/Decline)
# Route này sẽ được gọi từ Chat Lobby (nơi B thấy lời mời)
@chat_bp.route('/chat/respond_invite/<int:req_id>/<string:action>', methods=['POST'])
@login_required
def respond_invite(req_id, action):
    req = RoomRequest.query.get_or_404(req_id)
    
    # Security check: Phải là user B mới được xử lý
    if req.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('chat.chat'))
    
    room = Room.query.get(req.room_id)

    if action == 'accept':
        # B đồng ý -> Vào phòng
        room.members.append(current_user)
        db.session.delete(req) # Xóa request

        if room.tags:
            tags_list = room.tags.split(',')
            # Tăng trọng số mạnh (+2.0) vì hành động join room thể hiện sự quan tâm cao
            auto_update_user_interest(current_user.id, tags_list, weight_increment=2.0)
        
        # Notify Room
        msg = Message(body=f"joined the room via invitation.", room=room.name, author=current_user)
        db.session.add(msg)
        db.session.commit()
        
        socketio.emit('status', {'msg': f'{current_user.username} joined.'}, to=room.name)
        flash(f'You joined {room.name}.', 'success')
        return redirect(url_for('chat.chat_room', room_name=room.name))
        
    elif action == 'reject':
        # B từ chối -> Hủy
        db.session.delete(req)
        db.session.commit()
        flash(f'You declined the invitation to {room.name}.', 'secondary')
        
    return redirect(url_for('chat.chat'))
