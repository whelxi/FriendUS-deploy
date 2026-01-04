from flask import Blueprint, redirect, url_for, flash, request, jsonify, render_template
from flask_login import current_user, login_required
from app.extensions import db
from app.models import Room, Transaction
from app.forms import TransactionForm
from app.utils import simplify_debts

finance_bp = Blueprint('finance', __name__)

# --- [VIEW] Route hiển thị giao diện Finance ---
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

    # [FIX] Xử lý hide_nav chắc chắn hơn
    # Lấy giá trị chuỗi, so sánh với '1' để ra True/False
    hide_nav_param = request.args.get('hide_nav', '0')
    hide_nav = (hide_nav_param == '1')

    return render_template('finance.html', 
                           room=room, 
                           form=form, 
                           pending=pending, 
                           history=history,
                           hide_nav=hide_nav) # Truyền boolean vào template

# --- [ACTIONS] Các hàm xử lý (Redirect về chính nó) ---

@finance_bp.route('/room/<int:room_id>/add_transaction', methods=['POST'])
@login_required
def add_room_transaction(room_id):
    room = Room.query.get_or_404(room_id)
    form = TransactionForm()
    
    # Re-populate để validate
    form.receiver.choices = [(m.id, m.username) for m in room.members if m.id != current_user.id]
    if not form.receiver.choices: form.receiver.choices = [(0, 'No members')]

    if form.validate_on_submit():
        new_trans = Transaction(
            amount=form.amount.data, 
            description=form.description.data, 
            type=form.type.data,
            sender_id=current_user.id, 
            status='confirmed', # Auto confirm như bạn yêu cầu
            room_id=room.id,
            receiver_id=form.receiver.data
        )
        db.session.add(new_trans)
        db.session.commit()
    else:
        # Nếu lỗi form, flash message sẽ hiện trong iframe
        flash('Lỗi nhập liệu: Vui lòng kiểm tra số tiền và người nhận.', 'danger')
    
    # [FIX QUAN TRỌNG] 
    # 1. Lấy trạng thái hide_nav hiện tại (từ query string của action form)
    # 2. Redirect về lại view_finance (chính nó) kèm theo tham số hide_nav
    hide_nav_val = request.args.get('hide_nav', '0')
    return redirect(url_for('finance.view_finance', room_id=room.id, hide_nav=hide_nav_val))

@finance_bp.route('/confirm/<int:trans_id>', methods=['POST'])
@login_required
def confirm_transaction(trans_id):
    trans = Transaction.query.get_or_404(trans_id)
    room_id = trans.room.id 

    if trans.receiver_id == current_user.id:
        trans.status = 'confirmed'
        db.session.commit()
    
    # [FIX] Redirect về lại trang Finance, giữ nguyên trạng thái iframe
    hide_nav_val = request.args.get('hide_nav', '0')
    return redirect(url_for('finance.view_finance', room_id=room_id, hide_nav=hide_nav_val))

@finance_bp.route('/delete/<int:trans_id>', methods=['POST'])
@login_required
def delete_transaction(trans_id):
    trans = Transaction.query.get_or_404(trans_id)
    room_id = trans.room.id

    if trans.sender_id == current_user.id:
        db.session.delete(trans)
        db.session.commit()
        
    # [FIX] Redirect về lại trang Finance, giữ nguyên trạng thái iframe
    hide_nav_val = request.args.get('hide_nav', '0')
    return redirect(url_for('finance.view_finance', room_id=room_id, hide_nav=hide_nav_val))

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