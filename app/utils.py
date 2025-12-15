import os
import secrets
from PIL import Image
from flask import current_app
import datetime
import google.generativeai as genai
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from config import Config
from app.models import UserTagScore, db
from sqlalchemy.sql import func

# --- CẤU HÌNH AI & THUẬT TOÁN ---
# Nếu chưa có API KEY thì bọc try/except để app không crash
try:
    genai.configure(api_key=Config.GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
except Exception as e:
    print(f"Warning: Google AI Key missing or invalid. {e}")
    model = None

# [CẤU HÌNH] Danh sách Tag và Interest chuẩn của hệ thống (Knowledge Base)
# Bạn nên mở rộng danh sách này đầy đủ các chủ đề mà App hỗ trợ
INTERESTS_ALL = [
    "du lịch bụi", "nghỉ dưỡng", "ẩm thực", "khám phá", 
    "chụp ảnh", "lịch sử", "công nghệ", "nghệ thuật", 
    "thể thao", "mạo hiểm", "đọc sách", "âm nhạc"
]

TAGS_ALL = [
    "leo núi", "biển", "rừng", "resort", "street food", 
    "bảo tàng", "check-in", "coding", "triển lãm", 
    "bóng đá", "camping", "sách", "concert", "cafe"
]

# Khởi tạo Vectorizer và Matrix (Chạy 1 lần khi import)
try:
    vectorizer_matrix = TfidfVectorizer(lowercase=True, ngram_range=(1, 2))
    docs = INTERESTS_ALL + TAGS_ALL
    tfidf_matrix = vectorizer_matrix.fit_transform(docs)
    
    interest_vecs = tfidf_matrix[:len(INTERESTS_ALL)]
    tag_vecs = tfidf_matrix[len(INTERESTS_ALL):]
    
    # Ma trận trọng số W (Interest x Tags)
    W = cosine_similarity(interest_vecs, tag_vecs)
    
    # Index map để tra cứu nhanh
    INTEREST_INDEX = {v: i for i, v in enumerate(INTERESTS_ALL)}
    TAG_INDEX = {v: i for i, v in enumerate(TAGS_ALL)}
except Exception as e:
    print(f"Error initializing ML Matrix: {e}")
    W = None
    INTEREST_INDEX = {}
    TAG_INDEX = {}

# [NEW] Helper to save profile pictures
def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(current_app.root_path, 'static/profile_pics', picture_fn)

    output_size = (125, 125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn

# Helper logic functions
def simplify_debts(transactions):
    pair_balances = {} 

    for t in transactions:
        s_name = t.sender.username
        
        if t.receiver:
            r_name = t.receiver.username
        elif t.outsider:
            r_name = f"{t.outsider.name} (Outside)"
        else:
            continue 

        amount = float(t.amount)
        p1, p2 = sorted((s_name, r_name))
        key = (p1, p2)
        
        if key not in pair_balances: pair_balances[key] = 0.0

        if t.type == 'debt':
            if s_name == p1: pair_balances[key] += amount
            else: pair_balances[key] -= amount
        elif t.type == 'repayment':
            if s_name == p1: pair_balances[key] -= amount
            else: pair_balances[key] += amount

    direct_edges = []
    for (p1, p2), bal in pair_balances.items():
        if bal > 0:
            direct_edges.append({'from': p1, 'to': p2, 'amount': bal, 'label': f"{bal:,.0f}"})
        elif bal < 0:
            direct_edges.append({'from': p2, 'to': p1, 'amount': abs(bal), 'label': f"{abs(bal):,.0f}"})

    return direct_edges

def check_conflicts(activities, constraints):
    conflicts = {} 
    for act in activities:
        act_conflicts = []
        for cons in constraints:
            if cons.type == 'price':
                try:
                    limit = float(cons.value)
                    if act.price > limit:
                        msg = f"Over budget (${limit})"
                        act_conflicts.append({'msg': msg, 'level': 'critical' if cons.intensity == 'rough' else 'warning'})
                except ValueError: pass
            
            if cons.type == 'time':
                if act.start_time and act.start_time < cons.value:
                    msg = f"Too early (Before {cons.value})"
                    act_conflicts.append({'msg': msg, 'level': 'critical' if cons.intensity == 'rough' else 'warning'})

        if act_conflicts:
            conflicts[act.id] = act_conflicts
            
    return conflicts

def summarize_chat(chats):
    if not model: return "AI Error", "AI Error"
    chat_lines = chats[-40:]
    chat_text = "\n".join(chat_lines)
    
    # (Giữ nguyên prompt của bạn)
    short_summary_prompt = f"Tóm tắt đoạn chat tiếng Việt sau đây thành một bản tóm tắt ngắn gọn, tối đa 30 từ... Đoạn chat:\n{chat_text}"
    full_summary_prompt = f"Tóm tắt đoạn chat tiếng Việt sau đây thành một bản tóm tắt đầy đủ, tối đa 80 từ... Đoạn chat:\n{chat_text}"

    try:
        short_summary = model.generate_content(short_summary_prompt).text
    except: short_summary = "Lỗi không thể tóm tắt"
    
    try:
        full_summary = model.generate_content(full_summary_prompt).text
    except: full_summary = "Lỗi không thể tóm tắt"
    
    return short_summary, full_summary

# [NEW] Hàm tự động học: Cập nhật trọng số khi User tương tác
def auto_update_user_interest(user_id, tags_list, weight_increment=1.0):
    """
    user_id: ID người dùng
    tags_list: List các tag của bài viết/nhóm mà user vừa tương tác
    weight_increment: Mức độ tăng điểm (Ví dụ: Click xem = 0.5, Join nhóm = 2.0)
    """
    if not tags_list: return

    for tag in tags_list:
        tag_clean = tag.strip().lower()
        if not tag_clean: continue

        # Tìm xem user đã có điểm cho tag này chưa
        record = UserTagScore.query.filter_by(user_id=user_id, tag=tag_clean).first()
        
        if record:
            record.score += weight_increment
            record.last_interaction = datetime.utcnow()
        else:
            # Nếu chưa có, tạo mới
            new_record = UserTagScore(user_id=user_id, tag=tag_clean, score=weight_increment)
            db.session.add(new_record)
    
    db.session.commit()

# [UPDATED] Hàm tính điểm có xét đến trọng số cá nhân
def score_from_matrix_personalized(user_id, item_tags):
    """
    user_id: ID người dùng để lấy bảng điểm cá nhân
    item_tags: Tags của bài post hoặc room cần chấm điểm
    """
    if W is None: return 0.0

    # 1. Lấy tất cả các tag mà user này CÓ ĐIỂM trong database
    user_scores = UserTagScore.query.filter_by(user_id=user_id).all()
    if not user_scores: return 0.0 # User mới tinh chưa có sở thích

    # Tạo dictionary {tag: score} của user
    # Ví dụ: {'du lịch': 5.0, 'code': 1.0}
    user_interest_map = {u.tag: u.score for u in user_scores}
    
    rows = []
    # Duyệt qua các sở thích user ĐÃ CÓ trong DB
    for u_tag, u_score in user_interest_map.items():
        # Map tag của user vào Index của Ma trận AI (nếu có trong knowledge base)
        # Lưu ý: Ta dùng thuật toán matching gần đúng của AI hoặc exact match
        # Ở đây giả sử dùng exact match với keys trong INTEREST_INDEX của utils
        if u_tag not in INTEREST_INDEX: continue 
        
        ii = INTEREST_INDEX[u_tag]
        row = []
        
        for t in item_tags:
            if t in TAG_INDEX:
                # CÔNG THỨC MỚI:
                # Điểm = (Độ tương đồng ngữ nghĩa AI) * (Điểm quan tâm cá nhân của User)
                # Ví dụ: AI thấy "Du lịch" ~ "Biển" (0.8). User thích "Du lịch" (Score 5).
                # => Điểm match = 0.8 * 5 = 4.0
                ai_similarity = W[ii][TAG_INDEX[t]]
                weighted_score = ai_similarity * u_score
                row.append(weighted_score)
        
        if row: rows.append(row)

    if not rows: return 0.0

    # Logic Max-Pooling cũ của bạn
    row_max_sum = sum(max(r) for r in rows)
    if len(rows) > 0:
        score_row = row_max_sum / len(rows)
    else: 
        score_row = 0

    # Normalize lại điểm (vì u_score có thể tăng vô tận)
    # Ta có thể dùng log hoặc sigmoid nếu điểm quá lớn, tạm thời để nguyên
    return round(score_row * 10, 2)