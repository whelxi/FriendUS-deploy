import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from sqlalchemy import func, or_ # [NEW] Import để query OR cho tìm kiếm 
from app.extensions import db
from app.models import Post, Review, Location, User, FriendRequest
from app.forms import PostForm
from app.utils import score_from_matrix_personalized

main_bp = Blueprint('main', __name__)

@main_bp.route('/update_interests', methods=['POST'])
@login_required
def update_interests():
    data = request.get_json()
    interests = data.get('interests', []) # Nhận list mảng ['du lịch bụi', 'ẩm thực']
    
    if not isinstance(interests, list):
        return jsonify({'status': 'error', 'message': 'Invalid data format'}), 400
    
    # Chuyển list thành string CSV để lưu vào DB
    # Ví dụ: "du lịch bụi,ẩm thực"
    interests_str = ",".join(interests)
    
    current_user.interests = interests_str
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'Interests updated'})

@main_bp.route('/api/track_interest', methods=['POST'])
@login_required
def track_interest():
    data = request.get_json()
    tag = data.get('tag')
    
    if tag:
        # Tăng nhẹ (+0.5) cho hành động click xem/filter tag
        from app.utils import auto_update_user_interest
        auto_update_user_interest(current_user.id, [tag], weight_increment=0.5)
        return jsonify({'status': 'success', 'msg': f'Interest in {tag} recorded'})
    
    return jsonify({'status': 'error'}), 400

@main_bp.route('/', methods=['GET', 'POST'])
@main_bp.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    form = PostForm()
    if form.validate_on_submit():
        filename = None
        if form.media.data:
            file = form.media.data
            filename = secure_filename(file.filename)
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
            if not os.path.exists(upload_folder): os.makedirs(upload_folder)
            file.save(os.path.join(upload_folder, filename))

        tags_str = ''
        if form.tags.data:
            tags_str = ','.join(form.tags.data)

        # Tạo post với tags
        post = Post(
            body=form.body.data, 
            author=current_user, 
            media_filename=filename,
            tags=tags_str 
        )
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('main.index'))
    
    all_posts = Post.query.order_by(Post.timestamp.desc()).all()
    
    ranked_posts = []
    for p in all_posts:
        post_tags = p.tags.split(',') if p.tags else []
        # Dùng hàm tính điểm Personalize mới
        score = score_from_matrix_personalized(current_user.id, post_tags)
        ranked_posts.append((p, score))
        
    ranked_posts.sort(key=lambda x: x[1], reverse=True)
    final_posts = [x[0] for x in ranked_posts]

    # --- [THÊM ĐOẠN CODE NÀY ĐỂ ĐỊNH NGHĨA SUGGESTIONS] ---
    # Lấy ngẫu nhiên 3 user không phải là mình để gợi ý kết bạn
    # Lưu ý: Cần import func từ sqlalchemy nếu chưa có: from sqlalchemy import func
    suggestions = User.query.filter(User.id != current_user.id).order_by(func.random()).limit(3).all()
    # -------------------------------------------------------

    return render_template('index.html', title='Home', form=form, posts=final_posts, suggestions=suggestions)

# --- FRIEND SYSTEM ROUTES ---

@main_bp.route('/friends', methods=['GET', 'POST'])
@login_required
def friends():
    # 1. Xử lý Tìm kiếm
    search_query = request.args.get('q')
    search_results = []
    if search_query:
        # Tìm User theo username hoặc email (trừ bản thân)
        search_results = User.query.filter(
            (User.username.ilike(f'%{search_query}%')) | (User.email.ilike(f'%{search_query}%')),
            User.id != current_user.id
        ).all()

    # 2. Lấy danh sách bạn bè & Lời mời
    my_friends = current_user.friends.all()
    pending_requests = current_user.received_requests
    
    return render_template('friends.html', 
                           title='My Friends', 
                           friends=my_friends, 
                           requests=pending_requests,
                           search_results=search_results,
                           search_query=search_query)

@main_bp.route('/friend/add/<int:user_id>')
@login_required
def send_friend_request(user_id):
    user = User.query.get_or_404(user_id)
    current_user.send_request(user)
    flash(f'Friend request sent to {user.username}!', 'success')
    return redirect(request.referrer or url_for('main.friends'))

@main_bp.route('/friend/accept/<int:req_id>')
@login_required
def accept_friend_request(req_id):
    current_user.accept_request(req_id)
    flash('Friend request accepted!', 'success')
    return redirect(url_for('main.friends'))

@main_bp.route('/friend/reject/<int:req_id>')
@login_required
def reject_friend_request(req_id):
    req = FriendRequest.query.get_or_404(req_id)
    if req.receiver_id == current_user.id:
        db.session.delete(req)
        db.session.commit()
        flash('Request declined.', 'info')
    return redirect(url_for('main.friends'))

@main_bp.route('/friend/unfriend/<int:user_id>')
@login_required
def unfriend(user_id):
    user = User.query.get_or_404(user_id)
    current_user.remove_friend(user)
    flash(f'You unfriended {user.username}.', 'info')
    return redirect(request.referrer or url_for('main.friends'))