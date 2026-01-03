from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, FloatField, SelectField, RadioField, SelectMultipleField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Optional
from flask_login import current_user
from app.models import User, Room
from app.utils import TAG_CHOICES

class CommentForm(FlaskForm):
    body = StringField('Comment', validators=[DataRequired(), Length(min=1, max=200)])
    submit = SubmitField('Post')

class OnboardingForm(FlaskForm):
    # [FIX 1] Thêm validate_choice=False để tránh lỗi trên Render
    interests = SelectMultipleField('Choose your interests (1-5 tags)', choices=TAG_CHOICES, validate_choice=False)
    submit = SubmitField('Get Started')

    def validate_interests(self, interests):
        if not interests.data or len(interests.data) == 0:
            raise ValidationError('Please select at least one interest to continue.')
        if len(interests.data) > 5:
            raise ValidationError('You can only select up to 5 interests.')

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    
    submit = SubmitField('Sign Up')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('That username is taken. Please choose another.')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class PostForm(FlaskForm):
    body = TextAreaField('What\'s on your mind?', validators=[DataRequired(), Length(min=1, max=1000)])
    media = FileField('Upload Image/Video', validators=[
        FileAllowed(['jpg', 'png', 'jpeg', 'gif', 'mp4', 'mov', 'avi'], 'Images and Videos only!')
    ])
    
    # [FIX 2] validate_choice=False
    tags = SelectMultipleField('Tags', choices=TAG_CHOICES, validate_choice=False)
    
    submit = SubmitField('Post')

    def validate_tags(self, tags):
        if not tags.data or len(tags.data) == 0:
            raise ValidationError('Please select at least one tag for your post.')

class UpdateAccountForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    picture = FileField('Update Profile Picture', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])
    
    # [FIX 3 - MỚI] Thêm field Bio vào form để user có thể chỉnh sửa
    bio = TextAreaField('Bio', validators=[Length(max=250)])

    # [FIX 4 - QUAN TRỌNG] validate_choice=False sửa lỗi không lưu được interests
    interests = SelectMultipleField('Update Interests', choices=TAG_CHOICES, validate_choice=False)
    
    submit = SubmitField('Update Account')

    def validate_username(self, username):
        if username.data != current_user.username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('That username is taken. Please choose another.')

    def validate_email(self, email):
        if email.data != current_user.email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('That email is already in use.')

    def validate_interests(self, interests):
        if not interests.data or len(interests.data) == 0:
            raise ValidationError('Please select at least one interest.')

# --- CÁC FORM CŨ ---

class ReviewForm(FlaskForm):
    rating = SelectField('Rating', 
                         choices=[('5', '5 Stars'), ('4', '4 Stars'), ('3', '3 Stars'), ('2', '2 Stars'), ('1', '1 Star')], 
                         validators=[DataRequired()])
    body = TextAreaField('Your Review', validators=[DataRequired(), Length(min=10)])
    submit = SubmitField('Submit Review')

class CreateRoomForm(FlaskForm):
    name = StringField('Room Name', 
                         validators=[DataRequired(), Length(min=3, max=50)])
    description = TextAreaField('Description', 
                                validators=[Optional(), Length(max=200)])
    
    privacy = RadioField('Privacy Setting', 
                         choices=[('public', 'Public (Anyone can join)'), 
                                  ('private', 'Private (Invite only)')],
                         default='public',
                         validators=[DataRequired()])
    
    # [FIX 5] validate_choice=False
    tags = SelectMultipleField('Tags (Max 5)', choices=TAG_CHOICES, validate_choice=False)

    # [NEW] Checkbox cho phép vào luôn
    allow_auto_join = BooleanField('Allow Instant Join (Skip Admin Approval)', default=False)

    submit = SubmitField('Create Room')

    def validate_name(self, name):
        room = Room.query.filter_by(name=name.data).first()
        if room:
            raise ValidationError('That room name is taken. Please choose another.')

    def validate_tags(self, tags):
        if not tags.data or len(tags.data) == 0:
            raise ValidationError('Please select at least one tag for the room.')
        if len(tags.data) > 5:
            raise ValidationError('You can only select up to 5 tags.')

class TransactionForm(FlaskForm):
    amount = FloatField('Amount (VNĐ)', validators=[DataRequired()])
    description = StringField('Description', validators=[DataRequired()])
    type = RadioField('Transaction Type', choices=[
        ('debt', 'I Owe them (Ghi nợ)'), 
        ('repayment', 'I Paid them (Trả nợ)')
    ], default='debt', validators=[DataRequired()])
    receiver = SelectField('Receiver (Member)', choices=[], coerce=int, validators=[Optional()])
    is_outside = BooleanField('Outside/Stranger?')
    outsider_name = StringField('Outsider Name')
    submit = SubmitField('Create Transaction')

class ActivityForm(FlaskForm):
    name = StringField('Activity Name', validators=[DataRequired()])
    location = StringField('Location')
    price = FloatField('Est. Price ($)', validators=[DataRequired()])
    start_time = StringField('Start Time (e.g. 09:00)') 
    end_time = StringField('End Time (e.g. 11:00)')
    rating = FloatField('Initial Rating (1-5)', validators=[Optional()])
    submit = SubmitField('Add Activity')

class ConstraintForm(FlaskForm):
    type = SelectField('Type', choices=[('price', 'Price'), ('time', 'Time'), ('location', 'Location')])
    intensity = RadioField('Intensity', choices=[('soft', 'Soft (!)'), ('rough', 'Rough (!!) - Hard Rule')], default='soft')
    value = StringField('Value (e.g. 25 for price, 08:00 for time)', validators=[DataRequired()])
    submit = SubmitField('Add Constraint')