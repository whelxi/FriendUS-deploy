from flask_login import UserMixin
from datetime import datetime
from app.extensions import db, login_manager

# 1. Bảng trung gian để lưu User nào đã Like Post nào
post_likes = db.Table('post_likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'), primary_key=True)
)

# 2. Model cho Comment
class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    
    # Quan hệ để truy xuất người comment
    author = db.relationship('User', backref='comments')

# Bảng lưu điểm trọng số sở thích của User (Hệ thống tự học)
class UserTagScore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tag = db.Column(db.String(50), nullable=False, index=True) # Ví dụ: "du lịch bụi"
    score = db.Column(db.Float, default=1.0) # Điểm số tích lũy (càng cao càng thích)
    last_interaction = db.Column(db.DateTime, default=datetime.utcnow) # Để sau này có thể giảm điểm theo thời gian (decay)

    user = db.relationship('User', backref=db.backref('tag_scores', lazy='dynamic'))

    def __repr__(self):
        return f"<UserTagScore {self.user.username} - {self.tag}: {self.score}>"

# Bảng phụ lưu quan hệ bạn bè (User A là bạn User B)
friendship = db.Table('friendship',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('friend_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

# --- BẢNG QUAN HỆ MỚI CHO "YÊU THÍCH" ---
user_favorites = db.Table('user_favorites',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('location_id', db.Integer, db.ForeignKey('location.id'), primary_key=True)
)

# --- Bảng quan hệ cho Thành viên phòng chat ---
room_members = db.Table('room_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('room_id', db.Integer, db.ForeignKey('room.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # [NEW] Profile Picture
    image_file = db.Column(db.String(20), nullable=False, default='default.jpg')
    password = db.Column(db.String(60), nullable=False) 
    
    # Relationships
    posts = db.relationship('Post', backref='author', lazy=True)
    reviews = db.relationship('Review', backref='author', lazy=True)
    messages = db.relationship('Message', backref='author', lazy=True)
    
    rooms = db.relationship('Room', secondary=room_members,
                            back_populates='members', lazy='dynamic')
    
    created_rooms = db.relationship('Room', back_populates='creator', lazy='dynamic')

    favorite_locations = db.relationship('Location', secondary=user_favorites,
                                         back_populates='favorited_by', lazy='dynamic')
    
    # [NEW] Quan hệ bạn bè (Self-referential)
    friends = db.relationship('User', secondary=friendship,
                              primaryjoin=(friendship.c.user_id == id),
                              secondaryjoin=(friendship.c.friend_id == id),
                              backref=db.backref('friend_of', lazy='dynamic'), 
                              lazy='dynamic')

    # [NEW] Các hàm helper xử lý bạn bè
    def send_request(self, user):
        if not self.is_friend(user) and not self.has_sent_request(user):
            req = FriendRequest(sender_id=self.id, receiver_id=user.id)
            db.session.add(req)
            db.session.commit()

    def accept_request(self, request_id):
        req = FriendRequest.query.get(request_id)
        if req and req.receiver_id == self.id:
            req.status = 'accepted'
            # Add to friends list (both ways)
            self.friends.append(req.sender)
            req.sender.friends.append(self)
            db.session.delete(req) # Xóa request sau khi accept
            db.session.commit()

    def remove_friend(self, user):
        if self.is_friend(user):
            self.friends.remove(user)
            user.friends.remove(self)
            db.session.commit()

    def is_friend(self, user):
        return self.friends.filter(friendship.c.friend_id == user.id).count() > 0

    def has_sent_request(self, user):
        return FriendRequest.query.filter_by(sender_id=self.id, receiver_id=user.id, status='pending').count() > 0

    def has_received_request(self, user):
        return FriendRequest.query.filter_by(sender_id=user.id, receiver_id=self.id, status='pending').count() > 0

    interests = db.Column(db.String(500), default='')

    def __repr__(self):
        return f"User('{self.username}', '{self.email}')"

class Post(db.Model):
    media_filename = db.Column(db.String(100), nullable=True)
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(140), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    # [NEW] Relationship Likes
    likes = db.relationship('User', secondary=post_likes, backref=db.backref('liked_posts', lazy='dynamic'))
    
    # [NEW] Relationship Comments
    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade="all, delete-orphan")
    
    # [NEW] Đếm số lượt share (đơn giản nhất)
    shares_count = db.Column(db.Integer, default=0)

    # Helper function để check user đã like chưa
    def is_liked_by(self, user):
        return user in self.likes

    def __repr__(self):
        return f"Post('{self.body}')"
    
    tags = db.Column(db.String(200), default='')

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    hours = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    website = db.Column(db.String(100), nullable=True)
    
    type = db.Column(db.String(50), nullable=True, index=True)
    price_range = db.Column(db.Integer, nullable=True)
    
    reviews = db.relationship('Review', backref='location', lazy=True)
    favorited_by = db.relationship('User', secondary=user_favorites,
                                   back_populates='favorite_locations', lazy='dynamic')

    def __repr__(self):
        return f"Location('{self.name}')"

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, nullable=False, default=5)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=False)

    def __repr__(self):
        return f"Review('{self.body}', {self.rating})"

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    
    # [NEW] Các trường mới
    is_private = db.Column(db.Boolean, default=False) # False = Public, True = Private
    tags = db.Column(db.String(200), default='') # Lưu dạng chuỗi: "Travel,Eating"
    summary = db.Column(db.Text, nullable=True) # Nội dung tóm tắt (ẩn với user khi tạo)

    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    creator = db.relationship('User', back_populates='created_rooms')
    members = db.relationship('User', secondary=room_members,
                              back_populates='rooms', lazy='dynamic')

    def __repr__(self):
        return f"Room('{self.name}', Private={self.is_private})"

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    room = db.Column(db.String(50), nullable=False) 
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"Message('{self.body}', '{self.author.username}')"

# --- PHẦN FINANCE MỚI ---

class Outsider(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    creator = db.relationship('User', backref='outsiders')

    def __repr__(self):
        return f"<Outsider {self.name}>"

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(20), default='debt') 
    status = db.Column(db.String(20), default='pending') 
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    outsider_id = db.Column(db.Integer, db.ForeignKey('outsider.id'), nullable=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=True)
    room = db.relationship('Room', backref='transactions')
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_transactions')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_transactions')
    outsider = db.relationship('Outsider', backref='transactions')

    def __repr__(self):
        return f"<Transaction {self.amount} ({self.type})>"
    
class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100))
    price = db.Column(db.Float, nullable=False, default=0.0)
    start_time = db.Column(db.String(20)) 
    end_time = db.Column(db.String(20))
    rating = db.Column(db.Float, default=0.0)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    room = db.relationship('Room', backref='activities')

    def __repr__(self):
        return f"<Activity {self.name}>"

class Constraint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)
    intensity = db.Column(db.String(10), nullable=False)
    value = db.Column(db.String(50), nullable=False) 
    operator = db.Column(db.String(5), default="<") 
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    user = db.relationship('User', backref='constraints')

    def __repr__(self):
        return f"<Constraint {self.type} {self.intensity}>"

# [NEW] Model quản lý lời mời kết bạn
class FriendRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending') # pending, accepted, rejected
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_requests')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_requests')

    def __repr__(self):
        return f"<FriendRequest {self.sender_id}->{self.receiver_id}>"
    
# [NEW] Bảng quản lý yêu cầu tham gia phòng
class RoomRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Người muốn vào phòng
    inviter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Người mời (nếu có)
    
    # Status flows:
    # 1. User tự xin vào Public Room -> status='pending_owner' (Chờ chủ phòng duyệt)
    # 2. Chủ phòng mời User -> status='pending_user' (Chờ user đồng ý)
    # 3. Member mời User -> status='pending_user' -> User đồng ý -> status='pending_owner' (Chờ chủ phòng chốt)
    status = db.Column(db.String(20), nullable=False, default='pending_owner') 
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    room = db.relationship('Room', backref='requests')
    user = db.relationship('User', foreign_keys=[user_id], backref='room_requests')
    inviter = db.relationship('User', foreign_keys=[inviter_id], backref='sent_room_invites')

    def __repr__(self):
        return f"<RoomRequest Room:{self.room_id} User:{self.user_id} Status:{self.status}>"