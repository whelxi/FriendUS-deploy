from app.extensions import db

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