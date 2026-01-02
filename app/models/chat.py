from datetime import datetime
from app.extensions import db

room_members = db.Table('room_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('room_id', db.Integer, db.ForeignKey('room.id'), primary_key=True)
)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    is_private = db.Column(db.Boolean, default=False)
    tags = db.Column(db.String(200), default='') 
    summary = db.Column(db.Text, nullable=True)

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
        # Lưu ý: self.author được backref từ User trong user.py
        return f"Message('{self.body}', User ID: {self.user_id})"

class RoomRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    inviter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending_owner') 
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    room = db.relationship('Room', backref='requests')
    user = db.relationship('User', foreign_keys=[user_id], backref='room_requests')
    inviter = db.relationship('User', foreign_keys=[inviter_id], backref='sent_room_invites')

    def __repr__(self):
        return f"<RoomRequest Room:{self.room_id} User:{self.user_id} Status:{self.status}>"