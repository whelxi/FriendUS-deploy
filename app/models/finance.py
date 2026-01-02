from datetime import datetime
from app.extensions import db

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