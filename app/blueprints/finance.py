from flask import Blueprint, redirect, url_for, flash, request, jsonify, render_template
from flask_login import current_user, login_required
from app.extensions import db
from app.models import Room, Transaction, Outsider
from app.forms import TransactionForm
from app.utils import simplify_debts

finance_bp = Blueprint('finance', __name__)

# --- [NEW] Route hiển thị giao diện Finance (Dùng cho Iframe) ---
@finance_bp.route('/view/<int:room_id>', methods=['GET'])
@login_required
def view_finance(room_id):
    room = Room.query.get_or_404(room_id)
    form = TransactionForm()
    
    # Populate choices cho form
    form.receiver.choices = [(m.id, m.username) for m in room.members if m.id != current_user.id]
    if not form.receiver.choices: 
        form.receiver.choices = [(0, 'No members')]

    # Lấy dữ liệu hiển thị
    pending = Transaction.query.filter_by(room_id=room.id, status='pending').all()
    history = Transaction.query.filter_by(room_id=room.id).order_by(Transaction.timestamp.desc()).limit(20).all()

    # Nhận biến hide_nav từ URL (nếu gọi từ iframe)
    hide_nav = request.args.get('hide_nav', default=False, type=bool)

    return render_template('finance.html', 
                           room=room, 
                           form=form, 
                           pending=pending, 
                           history=history,
                           hide_nav=hide_nav)

# --- Các hàm xử lý (Đã sửa redirect) ---

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
            amount=form.amount.data, 
            description=form.description.data, 
            type=form.type.data,
            sender_id=current_user.id, 
            status='pending', 
            room_id=room.id,
            receiver_id=form.receiver.data
        )
        
        db.session.add(new_trans)
        db.session.commit()
        flash('Transaction recorded.', 'success')
    else:
        flash('Invalid transaction data.', 'danger')
    
    # [FIX] Nếu đang ở trong iframe (hide_nav=1), redirect về lại view_finance
    if request.args.get('hide_nav') == '1':
        return redirect(url_for('finance.view_finance', room_id=room.id, hide_nav=1))

    return redirect(url_for('chat.chat_room', room_name=room.name))

@finance_bp.route('/confirm/<int:trans_id>', methods=['POST'])
@login_required
def confirm_transaction(trans_id):
    trans = Transaction.query.get_or_404(trans_id)
    room_id = trans.room.id # Lấy ID phòng trước khi thao tác DB
    room_name = trans.room.name

    if trans.receiver_id == current_user.id:
        trans.status = 'confirmed'
        db.session.commit()
    
    # [FIX] Redirect thông minh
    if request.args.get('hide_nav') == '1':
        return redirect(url_for('finance.view_finance', room_id=room_id, hide_nav=1))

    return redirect(url_for('chat.chat_room', room_name=room_name))

@finance_bp.route('/delete/<int:trans_id>', methods=['POST'])
@login_required
def delete_transaction(trans_id):
    trans = Transaction.query.get_or_404(trans_id)
    room_id = trans.room.id
    room_name = trans.room.name

    if trans.sender_id == current_user.id:
        db.session.delete(trans)
        db.session.commit()
        
    # [FIX] Redirect thông minh
    if request.args.get('hide_nav') == '1':
        return redirect(url_for('finance.view_finance', room_id=room_id, hide_nav=1))

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