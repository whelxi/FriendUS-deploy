from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, current_user, login_required
from app.extensions import db, oauth
from app.models import User, Post
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
    # Nếu user đã có interests -> Đẩy về trang chủ luôn
    if current_user.interests:
        return redirect(url_for('main.index'))

    # Lưu ý: Form này không cần class OnboardingForm phức tạp nếu bạn dùng JS custom
    # Nhưng nếu dùng form.validate_on_submit() thì phải đảm bảo frontend gửi đúng name="interests"
    if request.method == 'POST':
        # Lấy dữ liệu từ input hidden có name="interests"
        selected_interests = request.form.get('interests')
        
        if selected_interests:
            current_user.interests = selected_interests # Lưu chuỗi "Tag1,Tag2"
            db.session.commit()
            flash('Welcome! Your profile is ready.', 'success')
            return redirect(url_for('main.index'))
        else:
            flash('Please select at least one interest.', 'warning')
    
    return render_template('onboarding.html', title='Welcome', hide_nav=True)

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
            
            # [LOGIC MỚI] Kiểm tra xem đã có interests chưa
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
        
        # Xử lý interests khi đăng ký (nếu có)
        interests_str = ''
        if form.interests.data:
            interests_str = ','.join(form.interests.data)

        user = User(
            username=form.username.data, 
            email=fake_email, 
            password=form.password.data,
            interests=interests_str 
        )
        db.session.add(user)
        db.session.commit()
        
        flash(f'Account created for {form.username.data}!', 'success')
        return redirect(url_for('auth.login'))
        
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
    
    user = User.query.filter_by(email=email).first()

    if user:
        login_user(user)
        # [LOGIC MỚI] User cũ đăng nhập -> Kiểm tra interests
        if not user.interests:
            return redirect(url_for('auth.onboarding'))
        
        flash('Logged in successfully via Google!', 'success')
        return redirect(url_for('main.index'))
    else:
        # User mới tạo từ Google
        base_username = name.replace(" ", "")
        username = base_username
        if User.query.filter_by(username=username).first():
            username = f"{base_username}_{secrets.token_hex(3)}"
            
        random_password = secrets.token_urlsafe(16)
        
        # Lưu ý: interests mặc định là '' (rỗng)
        new_user = User(
            username=username, 
            email=email,
            password=random_password 
        )
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        # [LOGIC MỚI] User mới tinh -> Chắc chắn chưa có interests -> Vào onboarding
        flash('Account created! Please select your interests.', 'success')
        return redirect(url_for('auth.onboarding'))

# --- Account / Profile Routes ---

@auth_bp.route('/profile/<string:username>', methods=['GET', 'POST'])
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(author=user).order_by(Post.timestamp.desc()).all()
    
    form = UpdateAccountForm()
    
    if user == current_user:
        if form.validate_on_submit():
            # 1. Handle Picture Upload
            if form.picture.data:
                picture_file = save_picture(form.picture.data)
                current_user.image_file = picture_file
            
            # 2. Update Info
            current_user.username = form.username.data
            
            # 3. [UPDATED] Update Interests (List -> String)
            if form.interests.data:
                current_user.interests = ','.join(form.interests.data)
            else:
                current_user.interests = '' # Clear if empty
            
            db.session.commit()
            
            flash('Your account has been updated!', 'success')
            return redirect(url_for('auth.profile', username=current_user.username))
        
        elif request.method == 'GET':
            # Pre-fill form with current data
            form.username.data = current_user.username
            form.email.data = current_user.email
            
            # [UPDATED] Load Interests to Form (String -> List)
            if current_user.interests:
                form.interests.data = current_user.interests.split(',')

    return render_template('profile.html', title='Profile', user=user, posts=posts, form=form)

@auth_bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    # Route này có thể giữ lại hoặc bỏ tùy bạn, nhưng logic update cũng tương tự profile
    form = UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        # Update interests
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