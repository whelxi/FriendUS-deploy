from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user, login_required
from app.extensions import db, socketio
from app.models import Room, Message, Activity, Constraint, Transaction, User, RoomRequest 
from app.forms import CreateRoomForm, ActivityForm, ConstraintForm, TransactionForm
from app.utils import auto_update_user_interest, score_from_matrix_personalized, check_conflicts

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    form = CreateRoomForm()
    if form.validate_on_submit():
        is_private_bool = True if form.privacy.data == 'private' else False
        tags_str = ",".join(form.tags.data) if form.tags.data else ""
        new_room = Room(name=form.name.data, description=form.description.data, is_private=is_private_bool, tags=tags_str, creator=current_user)
        new_room.members.append(current_user)
        db.session.add(new_room)
        db.session.commit()
        return redirect(url_for('chat.chat_room', room_name=new_room.name))

    my_rooms = current_user.rooms.all()
    my_room_ids = [r.id for r in my_rooms]
    raw_public_rooms = Room.query.filter(Room.is_private == False).filter(Room.id.notin_(my_room_ids)).all()

    # [MỚI] Tính điểm và Sort giống hệt bên main.py
    ranked_rooms = []
    for room in raw_public_rooms:
        # Tách tag của room (VD: "Travel,Eating" -> ['Travel', 'Eating'])
        room_tags = room.tags.split(',') if room.tags else []
        score = score_from_matrix_personalized(current_user.id, room_tags)
        ranked_rooms.append((room, score))
    
    # Sort giảm dần theo điểm
    ranked_rooms.sort(key=lambda x: x[1], reverse=True)
    public_rooms = [x[0] for x in ranked_rooms] # Lấy danh sách room đã sort
    
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
    
    if room_to_delete.name == 'general':
          flash('The general room cannot be deleted.', 'danger')
          return redirect(url_for('chat.chat'))
    
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
    
    # Kiểm tra xem đã gửi yêu cầu chưa
    existing_req = RoomRequest.query.filter_by(user_id=current_user.id, room_id=room.id).first()
    if existing_req:
        flash('Request already pending.', 'warning')
        return redirect(url_for('chat.chat'))

    # Tạo yêu cầu mới -> Chờ chủ phòng duyệt
    req = RoomRequest(room_id=room.id, user_id=current_user.id, status='pending_owner')
    db.session.add(req)
    
    # [Optional] Tạo thông báo hệ thống vào phòng chat để chủ phòng thấy ngay
    sys_msg = Message(body=f"System: {current_user.username} wants to join this room.", 
                      room=room.name, user_id=current_user.id) # user_id tạm để current, hoặc tạo 1 user system ảo
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
        # LOGIC CŨ: Thêm user vào ngay (SAI với yêu cầu mới)
        # room.members.append(user_to_add) ...
        
        # LOGIC MỚI: 
        # A (Creator) duyệt yêu cầu của C -> Chuyển status thành 'pending_user' 
        # Lúc này B (User) sẽ nhận được lời mời trong danh sách của họ
        req.status = 'pending_user'
        db.session.commit()
        
        # Gửi thông báo SocketIO cho User B biết là họ vừa nhận được lời mời
        # (Lời mời này thực chất do C tạo, nhưng giờ A mới duyệt cho đi)
        socketio.emit('new_invitation', {
            'msg': f'You have been invited to join {room.name} (Approved by owner)'
        }, to=f"user_{req.user_id}") # req.user_id là ID của B
        
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
