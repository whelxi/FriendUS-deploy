from datetime import datetime
from flask_login import UserMixin
from app.extensions import db

# Bảng phụ lưu quan hệ bạn bè
friendship = db.Table('friendship',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('friend_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

class UserTagScore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tag = db.Column(db.String(50), nullable=False, index=True)
    score = db.Column(db.Float, default=1.0)
    last_interaction = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('tag_scores', lazy='dynamic'))

    def __repr__(self):
        return f"<UserTagScore {self.user.username} - {self.tag}: {self.score}>"

class FriendRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_requests')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_requests')

    def __repr__(self):
        return f"<FriendRequest {self.sender_id}->{self.receiver_id}>"

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    image_file = db.Column(db.String(200), nullable=False, default='default.jpg') 
    bio = db.Column(db.String(250), nullable=True)
    password = db.Column(db.String(60), nullable=False) 
    interests = db.Column(db.String(500), default='')

    # Relationships
    posts = db.relationship('Post', backref='author', lazy=True)
    reviews = db.relationship('Review', backref='author', lazy=True)
    messages = db.relationship('Message', backref='author', lazy=True)
    
    # Lưu ý: 'room_members' là string reference để tránh import vòng lặp
    rooms = db.relationship('Room', secondary='room_members',
                            back_populates='members', lazy='dynamic')
    
    created_rooms = db.relationship('Room', back_populates='creator', lazy='dynamic')

    # Lưu ý: 'user_favorites' là string reference
    favorite_locations = db.relationship('Location', secondary='user_favorites',
                                         back_populates='favorited_by', lazy='dynamic')
    
    friends = db.relationship('User', secondary=friendship,
                              primaryjoin=lambda: friendship.c.user_id == User.id,
                              secondaryjoin=lambda: friendship.c.friend_id == User.id,
                              backref=db.backref('friend_of', lazy='dynamic'), 
                              lazy='dynamic')

    def send_request(self, user):
        if not self.is_friend(user) and not self.has_sent_request(user):
            req = FriendRequest(sender_id=self.id, receiver_id=user.id)
            db.session.add(req)
            db.session.commit()

    def accept_request(self, request_id):
        req = FriendRequest.query.get(request_id)
        if req and req.receiver_id == self.id:
            req.status = 'accepted'
            self.friends.append(req.sender)
            req.sender.friends.append(self)
            db.session.delete(req) 
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

    def __repr__(self):
        return f"User('{self.username}', '{self.email}')"