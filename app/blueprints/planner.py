from flask import Blueprint, redirect, url_for, flash
from flask_login import current_user, login_required
from app.extensions import db
from app.models import Room, Activity, Constraint
from app.forms import ActivityForm, ConstraintForm

planner_bp = Blueprint('planner', __name__)

@planner_bp.route('/room/<int:room_id>/add_activity', methods=['POST'])
@login_required
def add_room_activity(room_id):
    room = Room.query.get_or_404(room_id)
    form = ActivityForm()
    if form.validate_on_submit():
        new_act = Activity(
            name=form.name.data, location=form.location.data, price=form.price.data,
            start_time=form.start_time.data, end_time=form.end_time.data,
            rating=form.rating.data if form.rating.data else 0, room=room
        )
        db.session.add(new_act)
        db.session.commit()
        flash('Activity added!', 'success')
    else:
        flash('Error adding activity.', 'danger')
    return redirect(url_for('chat.chat_room', room_name=room.name))

@planner_bp.route('/room/<int:room_id>/add_constraint', methods=['POST'])
@login_required
def add_room_constraint(room_id):
    room = Room.query.get_or_404(room_id)
    form = ConstraintForm()
    
    if form.validate_on_submit():
        new_cons = Constraint(
            type=form.type.data, 
            intensity=form.intensity.data, 
            value=form.value.data,
            user=current_user, 
            room_id=room.id
        )
        db.session.add(new_cons)
        db.session.commit()
        flash('Constraint added successfully.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {field}: {error}", 'danger')
                
    return redirect(url_for('chat.chat_room', room_name=room.name))

@planner_bp.route('/delete_activity/<int:id>')
@login_required
def delete_activity(id):
    act = Activity.query.get_or_404(id)
    room_name = act.room.name
    db.session.delete(act)
    db.session.commit()
    return redirect(url_for('chat.chat_room', room_name=room_name))

@planner_bp.route('/delete_constraint/<int:id>')
@login_required
def delete_constraint(id):
    cons = Constraint.query.get_or_404(id)
    room_name = cons.room.name
    if cons.user_id == current_user.id:
        db.session.delete(cons)
        db.session.commit()
    return redirect(url_for('chat.chat_room', room_name=room_name))