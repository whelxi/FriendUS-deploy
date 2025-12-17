from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, current_user, login_required
from app.extensions import db, oauth
from app.models import User, Post, UserTagScore
# [QUAN TRỌNG] Đảm bảo đã import OnboardingForm
from app.forms import LoginForm, RegisterForm, UpdateAccountForm, OnboardingForm
from app.utils import save_picture
import secrets

auth_bp = Blueprint('auth', __name__)

@auth_bp.before_app_request
def check_onboarding():
    """
    Hàm này chạy trước mọi request.
    Nếu user đã login nhưng chưa có interests -> Bắt buộc về trang onboarding.
    Trừ phi họ đang ở trang onboarding, logout hoặc đang tải file tĩnh (css/js).
    """
    if current_user.is_authenticated:
        # Kiểm tra nếu chưa có interests (coi như chưa onboarding)
        if not current_user.interests:
            # Danh sách các endpoint được phép truy cập
            allowed_endpoints = ['auth.onboarding', 'auth.logout', 'static']
            
            # Nếu endpoint hiện tại không nằm trong danh sách cho phép -> Redirect
            if request.endpoint and request.endpoint not in allowed_endpoints:
                return redirect(url_for('auth.onboarding'))

@auth_bp.route('/onboarding', methods=['GET', 'POST'])
@login_required
def onboarding():
    if current_user.interests:
        return redirect(url_for('main.index'))

    form = OnboardingForm()

    if form.validate_on_submit():
        selected_tags = form.interests.data
        
        if selected_tags:
            # 1. Lưu dạng chuỗi (để hiển thị profile cho dễ)
            current_user.interests = ','.join(selected_tags)
            
            # 2. [FIX QUAN TRỌNG] Khởi tạo điểm số ban đầu vào bảng UserTagScore
            # Cho điểm cao (ví dụ 5.0) vì đây là cái họ chủ động chọn
            for tag in selected_tags:
                # Kiểm tra tránh duplicate
                exists = UserTagScore.query.filter_by(user_id=current_user.id, tag=tag).first()
                if not exists:
                    init_score = UserTagScore(user_id=current_user.id, tag=tag, score=5.0)
                    db.session.add(init_score)
            
            db.session.commit()
            flash('Welcome! Your profile is ready.', 'success')
            return redirect(url_for('main.index'))
        else:
            # Trường hợp form pass validate nhưng list rỗng (hiếm khi xảy ra do validator)
            flash('Please select at least one interest.', 'warning')
    
    # 3. [QUAN TRỌNG] Truyền biến form=form sang template
    return render_template('onboarding.html', title='Welcome', form=form, hide_nav=True)

# --- Standard Login Routes ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        
        if user and user.password == form.password.data:
            login_user(user, remember=form.remember.data)
            
            # Kiểm tra xem đã có interests chưa
            if not user.interests: 
                return redirect(url_for('auth.onboarding'))
            
            return redirect(url_for('main.index'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
            
    return render_template('login.html', title='Login', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = RegisterForm()
    if form.validate_on_submit():
        fake_email = f"{form.username.data}@friendus.local"
        
        user = User(
            username=form.username.data, 
            email=fake_email, 
            password=form.password.data,
            interests='' # Để trống để trigger onboarding
        )
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        flash(f'Account created! Please select your interests to get started.', 'success')
        return redirect(url_for('auth.onboarding'))
        
    return render_template('register.html', title='Register', form=form)

@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

# --- Google OAuth Routes ---

@auth_bp.route('/google')
def google_login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

# --- Google OAuth Routes (CẬP NHẬT) ---

@auth_bp.route('/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        resp = oauth.google.get('userinfo')
        user_info = resp.json()
    except Exception as e:
        flash(f'Google authentication failed: {str(e)}', 'danger')
        return redirect(url_for('auth.login'))

    email = user_info.get('email')
    name = user_info.get('name')
    picture = user_info.get('picture') # Lấy link avatar
    
    user = User.query.filter_by(email=email).first()

    if user:
        # [NEW] Cập nhật avatar nếu user đăng nhập lại bằng Google
        # Chỉ cập nhật nếu user đang dùng ảnh default (để tránh ghi đè ảnh họ tự upload)
        if 'default.jpg' in user.image_file and picture:
             user.image_file = picture
             db.session.commit()
             
        login_user(user)
        if not user.interests:
            return redirect(url_for('auth.onboarding'))
        flash('Logged in successfully via Google!', 'success')
        return redirect(url_for('main.index'))
    else:
        # [NEW] Tạo user mới với Avatar Google
        base_username = name.replace(" ", "")
        username = base_username
        if User.query.filter_by(username=username).first():
            username = f"{base_username}_{secrets.token_hex(3)}"
            
        random_password = secrets.token_urlsafe(16)
        
        new_user = User(
            username=username, 
            email=email,
            image_file=picture if picture else 'default.jpg', # Lưu link ảnh
            password=random_password,
            interests='' 
        )
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        flash('Account created! Please select your interests.', 'success')
        return redirect(url_for('auth.onboarding'))

# --- Account / Profile Routes (CẬP NHẬT) ---

@auth_bp.route('/profile/<string:username>', methods=['GET', 'POST'])
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(author=user).order_by(Post.timestamp.desc()).all()
    
    form = UpdateAccountForm()
    
    if user == current_user:
        if form.validate_on_submit():
            if form.picture.data:
                picture_file = save_picture(form.picture.data)
                current_user.image_file = picture_file
            
            current_user.username = form.username.data
            
            # [NEW] Lưu Bio (Bạn cần thêm field bio vào UpdateAccountForm trong forms.py nhé)
            # Vì bạn không gửi file forms.py, tôi giả định bạn sẽ thêm field bio vào đó.
            # Nếu form chưa có field bio, dòng dưới sẽ bị lỗi. Hãy kiểm tra forms.py.
            if hasattr(form, 'bio'): 
                current_user.bio = form.bio.data

            if form.interests.data:
                current_user.interests = ','.join(form.interests.data)
            else:
                current_user.interests = ''
            
            db.session.commit()
            flash('Your account has been updated!', 'success')
            return redirect(url_for('auth.profile', username=current_user.username))
        
        elif request.method == 'GET':
            form.username.data = current_user.username
            form.email.data = current_user.email
            # [NEW] Load Bio hiện tại
            if hasattr(form, 'bio'):
                form.bio.data = current_user.bio
                
            if current_user.interests:
                form.interests.data = current_user.interests.split(',')

    return render_template('profile.html', title='Profile', user=user, posts=posts, form=form)

@auth_bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        if form.interests.data:
            current_user.interests = ','.join(form.interests.data)
        db.session.commit()
        flash('Account updated!', 'success')
        return redirect(url_for('auth.account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
        if current_user.interests:
            form.interests.data = current_user.interests.split(',')
    image_file = url_for('static', filename='profile_pics/' + current_user.image_file)
    return render_template('account.html', title='Account', image_file=image_file, form=form)