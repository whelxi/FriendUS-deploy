from flask import Blueprint, redirect, url_for, flash, request, jsonify
from flask_login import current_user, login_required
from app.extensions import db
from app.models import Room, Transaction, Outsider
from app.forms import TransactionForm
from app.utils import simplify_debts

finance_bp = Blueprint('finance', __name__)

@finance_bp.route('/room/<int:room_id>/add_transaction', methods=['POST'])
@login_required
def add_room_transaction(room_id):
    room = Room.query.get_or_404(room_id)
    form = TransactionForm()
    # Re-populate choices for validation
    form.receiver.choices = [(m.id, m.username) for m in room.members if m.id != current_user.id]
    if not form.receiver.choices: form.receiver.choices = [(0, 'No members')]

    if form.validate_on_submit():
        new_trans = Transaction(
            amount=form.amount.data, description=form.description.data, type=form.type.data,
            sender_id=current_user.id, status='pending', room_id=room.id 
        )
        if form.is_outside.data and form.outsider_name.data:
            o_name = form.outsider_name.data.strip()
            outsider = Outsider.query.filter_by(name=o_name, creator_id=current_user.id).first()
            if not outsider:
                outsider = Outsider(name=o_name, creator_id=current_user.id)
                db.session.add(outsider)
                db.session.commit()
            new_trans.outsider_id = outsider.id
            new_trans.status = 'confirmed' 
        else:
            new_trans.receiver_id = form.receiver.data
        
        db.session.add(new_trans)
        db.session.commit()
        flash('Transaction recorded.', 'success')
    else:
        flash('Invalid transaction data.', 'danger')
    return redirect(url_for('chat.chat_room', room_name=room.name))

@finance_bp.route('/confirm/<int:trans_id>', methods=['POST'])
@login_required
def confirm_transaction(trans_id):
    trans = Transaction.query.get_or_404(trans_id)
    room_name = trans.room.name
    if trans.receiver_id != current_user.id:
        return redirect(url_for('chat.chat_room', room_name=room_name))
    trans.status = 'confirmed'
    db.session.commit()
    return redirect(url_for('chat.chat_room', room_name=room_name))

@finance_bp.route('/delete/<int:trans_id>', methods=['POST'])
@login_required
def delete_transaction(trans_id):
    trans = Transaction.query.get_or_404(trans_id)
    room_name = trans.room.name
    if trans.sender_id == current_user.id:
        db.session.delete(trans)
        db.session.commit()
    return redirect(url_for('chat.chat_room', room_name=room_name))

@finance_bp.route('/api/graph')
@login_required
def api_finance_graph():
    room_id = request.args.get('room_id', type=int)
    if not room_id: return jsonify({'nodes': [], 'edges': []})

    transactions = Transaction.query.filter_by(room_id=room_id).filter(
        (Transaction.status == 'confirmed') | (Transaction.status == 'pending')
    ).all()
    
    edges = simplify_debts(transactions)
    nodes_set = set()
    for e in edges:
        nodes_set.add(e['from'])
        nodes_set.add(e['to'])
    nodes = [{'id': n, 'label': n, 'shape': 'dot', 'size': 20} for n in nodes_set]
    return jsonify({'nodes': nodes, 'edges': edges})