import random
from datetime import datetime, timedelta
from faker import Faker
from app import create_app, db
from app.models import User, Room, UserTagScore, Post, Message, room_members
from werkzeug.security import generate_password_hash

# Khởi tạo Faker
fake = Faker()
app = create_app()

# ==========================================
# 1. BỘ DỮ LIỆU CHAT GIẢ LẬP
# ==========================================
TOPICS = {
    "Travel_DaLat": [
        "Mọi người ơi, cuối tuần này đi Đà Lạt không?",
        "Nghe hợp lý đó, dạo này Sài Gòn nóng quá.",
        "Đi xe Thành Bưởi hay Phương Trang nhỉ?",
        "Tui book homestay nhé, có chỗ này view đồi thông đẹp lắm.",
        "Thôi ở khách sạn đi cho tiện, homestay sợ ma lắm.",
        "Chi phí dự kiến khoảng bao nhiêu một người?",
        "Tầm 2-3 triệu là ăn chơi xả láng rồi.",
        "Nhớ mang áo ấm nha, nghe bảo tối lạnh 14 độ.",
        "Có ai biết quán nướng ngói nào ngon không?",
        "Đi Lẩu Gà Lá É Tao Ngộ đi, bao ngon.",
        "Sáng dậy sớm săn mây ở Cầu Gỗ nha mọi người.",
        "Tui không dậy sớm được đâu, mọi người đi thì đi.",
        "Chốt lịch trình chưa? Gửi vào nhóm đi.",
        "Tối thứ 6 xuất phát, tối chủ nhật về nhé."
    ],
    "Tech_Python": [
        "Có ai fix được lỗi ImportError này không?",
        "Thử kiểm tra lại biến môi trường xem sao.",
        "Python dạo này ra bản 3.12 chạy nhanh phết.",
        "Tui vẫn thích dùng Java hơn, Python lỏng lẻo quá.",
        "Nhưng Python làm AI/ML là trùm rồi, thư viện nhiều.",
        "Django với Flask cái nào ngon hơn cho dự án nhỏ?",
        "Flask đi, linh hoạt, dễ custom.",
        "Django có sẵn admin page tiện mà, đỡ phải code nhiều.",
        "Mọi người deploy lên AWS hay Heroku?",
        "Dùng Docker đóng gói rồi quăng lên đâu chả được.",
        "Code xong chưa merge request đi tui review cho.",
        "Đang bị conflict git, cứu tui với.",
        "Ông nào push code mà không chạy test vậy??",
        "Bug này lạ quá, trên máy tui chạy bình thường mà."
    ],
    "Drama_Office": [
        "Ê nghe nói sếp mới sắp về team mình đấy.",
        "Tin chuẩn không? Nghe bảo ông này khó tính lắm.",
        "Lại sắp phải OT sấp mặt rồi.",
        "Trưa nay đi ăn gì đây mọi người?",
        "Ăn bún đậu mắm tôm đi, thèm quá.",
        "Thôi ăn cơm văn phòng đi, hết tiền rồi.",
        "Bà A phòng kế toán mới cãi nhau với sếp tổng kìa.",
        "Căng vậy? Vụ gì thế kể nghe coi.",
        "Hình như là sai sót trong báo cáo tài chính quý vừa rồi.",
        "Công ty dạo này nhiều biến quá, tính nhảy việc không?",
        "Đợi nhận thưởng tết xong đã rồi tính.",
        "Deadline dí tới cổ rồi mà vẫn ngồi chat chit à?",
        "Xả stress tí làm gì căng.",
        "Chiều nay 4h họp toàn công ty nhé."
    ]
}

FILLERS = [
    "Haha chuẩn luôn.", "Ok chốt.", "Thật á?", "Không thể tin được.", 
    "Hmm...", "Để suy nghĩ đã.", "Vote 1 phiếu.", "Tuyệt vời.",
    "Cũng được.", "Sao cũng được.", "Tùy mọi người.", "Like mạnh.",
    "Thả tim <3", "Kkk", "Đúng rồi.", "Sai rồi.", "Chán thế.", 
    "Vui vãi.", "Cứu tuiii", "Alo alo"
]

TAG_LIST = [
    'Travel', 'Food', 'Coffee', 'Music', 'Sports', 'Gaming', 
    'Technology', 'Movies', 'Reading', 'Study', 'Camping', 
    'Shopping', 'Photography', 'Billiards', 'Just Chatting'
]

# ==========================================
# 2. HÀM SEEDING CHÍNH
# ==========================================
def seed_database():
    with app.app_context():
        print("🗑️  Đang dọn dẹp dữ liệu cũ (Message, Post, Room, User)...")
        try:
            db.session.query(Message).delete()
            db.session.query(Post).delete()
            db.session.execute(room_members.delete()) 
            db.session.query(Room).delete()
            db.session.query(UserTagScore).delete()
            db.session.query(User).delete()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"⚠️  Lỗi khi xóa: {e}")

        print("🚀 Bắt đầu Seed dữ liệu mới...")

        # --- 1. TẠO USER ---
        print("👤 Đang tạo User...")
        demo_user = User(
            username='demo', email='demo@test.com',
            password=generate_password_hash('123456'),
            image_file='default.jpg', bio="I am the Tester!"
        )
        db.session.add(demo_user)

        bots = []
        for i in range(20):
            bot = User(
                username=f'bot_{i}',
                email=f'bot_{i}@test.com',
                password=generate_password_hash('123456'),
                image_file='default.jpg',
                bio=fake.sentence()
            )
            db.session.add(bot)
            bots.append(bot)
        
        db.session.commit()
        all_users = [demo_user] + bots

        # --- 2. TẠO POSTS ---
        print("📝 Đang tạo Posts...")
        for _ in range(30):
            author = random.choice(all_users)
            post = Post(
                body=fake.text(max_nb_chars=140),
                author=author,
                tags=random.choice(TAG_LIST),
                timestamp=datetime.utcnow() - timedelta(hours=random.randint(1, 100))
            )
            db.session.add(post)
        db.session.commit()

        # --- 3. TẠO ROOM & TIN NHẮN (ĐÃ SỬA: INSTANT JOIN) ---
        print("💬 Đang tạo Chat Rooms (Instant Join) và spam tin nhắn...")

        scenarios = [
            ("Hội Đam Mê Du Lịch", "Travel_DaLat", "Travel,Food,Photography"),
            ("Cộng Đồng Dev Python", "Tech_Python", "Technology,Study,Gaming"),
            ("Hóng Biến Công Sở", "Drama_Office", "Just Chatting,Coffee,Shopping"),
            ("Gaming Zone", "Tech_Python", "Gaming,Billiards"),
        ]

        for room_name, topic_key, tags in scenarios:
            creator = random.choice(bots)
            
            room = Room(
                name=room_name,
                description=f"Group chat about {tags}",
                is_private=False,
                allow_auto_join=True,  # <--- ĐÃ THÊM: Cho phép vào ngay
                tags=tags,
                creator=creator
            )
            db.session.add(room)
            db.session.commit()

            # Add members (Instant Join logic)
            for u in all_users:
                room.members.append(u)
            
            # Spam tin nhắn
            print(f"   -> Đang spam 350 tin nhắn vào phòng: {room_name}")
            topic_sentences = TOPICS.get(topic_key, TOPICS["Travel_DaLat"])
            base_time = datetime.utcnow() - timedelta(days=5)

            batch_messages = []
            for i in range(350):
                sender = random.choice(all_users)
                rand_val = random.random()
                if rand_val < 0.4:
                    content = random.choice(topic_sentences)
                elif rand_val < 0.7:
                    content = random.choice(FILLERS)
                else:
                    content = fake.sentence()

                msg_time = base_time + timedelta(minutes=i*2 + random.randint(1, 10))

                msg = Message(
                    body=content,
                    room=room.name, 
                    user_id=sender.id,
                    timestamp=msg_time
                )
                db.session.add(msg)
            
            db.session.commit()

        # Tạo thêm phòng ngẫu nhiên (Cũng là Instant Join)
        print("🎲 Đang tạo thêm các phòng ngẫu nhiên khác...")
        for i in range(5):
            r = Room(
                name=f"Random Room {i}", 
                description="Just a random room", 
                tags="Just Chatting",
                is_private=False,
                allow_auto_join=True, # <--- ĐÃ THÊM: Cho phép vào ngay
                creator=random.choice(bots)
            )
            db.session.add(r)
        db.session.commit()

        print("✅ HOÀN TẤT! Tất cả phòng đã được set Instant Join.")
        print("👉 User test: 'demo' / '123456'")

if __name__ == '__main__':
    seed_database()