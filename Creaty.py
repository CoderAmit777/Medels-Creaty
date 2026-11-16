from flask import Flask, render_template, request, redirect, url_for, session, make_response, flash, jsonify,send_file
import io
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, 
    get_jwt_identity, set_access_cookies, unset_jwt_cookies
)
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import random
import os

app = Flask(__name__)

# --- Configurations ---
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'creaty-session-secret-key-2026')

# Neon (PostgreSQL) বা লোকাল SQLite এর জন্য ডায়নামিক ইউআরআই
db_url = os.environ.get('DATABASE_URL', 'sqlite:///data.db')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'creaty-jwt-super-secret-key-2026')
app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_ACCESS_COOKIE_PATH'] = '/'
app.config['JWT_COOKIE_CSRF_PROTECT'] = False

# --- Flask-Mail Configuration ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'your_email@gmail.com') # তোমার জিমেইল এখানে দাও
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'your_app_password')     # জিমেইলের App Password এখানে দাও

mail = Mail(app)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
jwt = JWTManager(app)

@jwt.unauthorized_loader
def unauthorized_callback(callback):
    return redirect('/login')

@jwt.invalid_token_loader
def invalid_token_callback(callback):
    response = make_response(redirect('/login'))
    unset_jwt_cookies(response)
    return response

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    response = make_response(redirect('/login'))
    unset_jwt_cookies(response)
    return response


# --- Database Models ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password = db.Column(db.String(200), nullable=False)
    bio = db.Column(db.String(300), default="Hey there! I am using Creaty.")
    profile_pic = db.Column(db.String(200), default="default_avatar.png")

class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_username = db.Column(db.String(50), nullable=False)   
    following_username = db.Column(db.String(50), nullable=False)  

class suply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(400), nullable=False)
    qustion = db.Column(db.String(1000), nullable=False)
    solution = db.Column(db.String(1000))
    tags = db.Column(db.String(200), nullable=False, default="#general")
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    username = db.Column(db.String(50), nullable=False)
    
    images = db.relationship('PostImage', backref='post', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='post', lazy=True, cascade='all, delete-orphan')
    saved_by = db.relationship('SavedPost', backref='post', lazy=True, cascade='all, delete-orphan')

class PostImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    image_data = db.Column(db.LargeBinary, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('suply.id'), nullable=False)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)
    username = db.Column(db.String(50), nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    post_id = db.Column(db.Integer, db.ForeignKey('suply.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('CommentLike', backref='comment', lazy=True, cascade='all, delete-orphan')
    
    is_verified = db.Column(db.Boolean, default=False)
    is_pinned = db.Column(db.Boolean, default=False)

class CommentLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=False)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('suply.id'), nullable=False)

class SavedPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('suply.id'), nullable=False)

with app.app_context():
    db.create_all()


# --- Routes ---

@app.route('/')
@jwt_required(optional=True)
def Home():
    current_user = None
    current_user_obj = None
    try:
        identity = get_jwt_identity()
        if identity:
            user_record = User.query.filter_by(username=identity).first()
            if user_record:
                current_user = identity
                current_user_obj = user_record
    except Exception:
        current_user = None
        current_user_obj = None

    search_query = request.args.get('q', '').strip()
    filter_type = request.args.get('filter', 'all')
    
    query = suply.query.order_by(suply.date_posted.desc())
    
    if search_query:
        clean_q = search_query.lstrip('#')
        query = query.filter(suply.tags.ilike(f'%{clean_q}%'))
        
    all_matching_posts = query.all()
    
    posts = []
    for p in all_matching_posts:
        has_verified_comment = any(c.is_verified for c in p.comments)
        is_solved = has_verified_comment or bool(p.solution and p.solution.strip())
        
        if filter_type == 'solved' and is_solved:
            posts.append(p)
        elif filter_type == 'unsolved' and not is_solved:
            posts.append(p)
        elif filter_type == 'all':
            posts.append(p)
            
    not_found = (len(posts) == 0)
    
    liked_post_ids = set()
    saved_post_ids = set()
    liked_comment_ids = set()
    if current_user:
        liked_post_ids = {l.post_id for l in Like.query.filter_by(username=current_user).all()}
        saved_post_ids = {s.post_id for s in SavedPost.query.filter_by(username=current_user).all()}
        liked_comment_ids = {cl.comment_id for cl in CommentLike.query.filter_by(username=current_user).all()}

    response = make_response(render_template(
        'index.html',
        posts=posts,
        current_user=current_user,
        current_user_obj=current_user_obj,
        search_query=search_query,
        filter_type=filter_type,
        not_found=not_found,
        liked_post_ids=liked_post_ids,
        saved_post_ids=saved_post_ids,
        liked_comment_ids=liked_comment_ids
    ))
    
    if not current_user:
        unset_jwt_cookies(response)
        
    return response


@app.route('/api/search-users', methods=['GET'])
def api_search_users():
    query = request.args.get('q', '').strip()
    users_data = []
    if query:
        matched_users = User.query.filter(User.username.ilike(f'%{query}%')).limit(6).all()
        for u in matched_users:
            users_data.append({
                'username': u.username,
                'profile_pic': u.profile_pic if u.profile_pic else 'default_avatar.png',
                'bio': u.bio
            })
    return jsonify(users_data)


@app.route('/search-users', methods=['GET'])
@jwt_required(optional=True)
def search_users():
    current_user = None
    try:
        identity = get_jwt_identity()
        if identity and User.query.filter_by(username=identity).first():
            current_user = identity
    except Exception:
        current_user = None

    query = request.args.get('username', '').strip()
    users = []
    
    user_follow_status = {}
    if query:
        users = User.query.filter(User.username.ilike(f'%{query}%')).all()
        if current_user:
            for u in users:
                is_flw = Follow.query.filter_by(follower_username=current_user, following_username=u.username).first() is not None
                user_follow_status[u.username] = is_flw
        
    return render_template(
        'user_list.html', 
        title=f"Search Results for '{query}'", 
        users=users, 
        current_user=current_user,
        user_follow_status=user_follow_status
    )


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        email = request.form.get('email', '').strip()
        
        if not username or not password:
            return render_template('signup.html', error="Username and password are required.")
            
        if len(password) < 8:
            return render_template('signup.html', error="Password must be at least 8 characters long.")
            
        if User.query.filter_by(username=username).first():
            return render_template('signup.html', error="This username is already taken. Please choose another one.")
            
        if email:
            if User.query.filter_by(email=email).first():
                return render_template('signup.html', error="This email is already linked to another account.")
        else:
            email = None
            
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        access_token = create_access_token(identity=username)
        response = make_response(redirect('/'))
        set_access_cookies(response, access_token)
        return response
        
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            access_token = create_access_token(identity=username)
            response = make_response(redirect('/'))
            set_access_cookies(response, access_token)
            return response
        else:
            return render_template('login.html', error="Invalid username or password. Please try again.")
            
    return render_template('login.html')


# --- Forgot Password with OTP Routes ---

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        user = User.query.filter_by(username=username).first()
        
        if not user:
            return render_template('forgot_password.html', error="User not found with this username.")
            
        if not user.email:
            return render_template('forgot_password.html', error="Sorry, email can't be added / No email linked to this account.")
            
        # Generate 6 digit OTP
        otp = str(random.randint(100000, 999999))
        session['reset_otp'] = otp
        session['reset_username'] = user.username
        
        try:
            msg = Message('Password Reset OTP - Creaty', sender=app.config['MAIL_USERNAME'], recipients=[user.email])
            msg.body = f"Hello @{user.username},\n\nYour OTP for logging into Creaty is: {otp}\n\nIf you didn't request this, please ignore this email."
            mail.send(msg)
        except Exception as e:
            return render_template('forgot_password.html', error=f"Failed to send email. Check SMTP settings.")
            
        return redirect('/verify-otp')
        
    return render_template('forgot_password.html')


@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if 'reset_username' not in session:
        return redirect('/forgot-password')
        
    if request.method == 'POST':
        entered_otp = request.form.get('otp', '').strip()
        if entered_otp == session.get('reset_otp'):
            username = session.pop('reset_username')
            session.pop('reset_otp', None)
            
            access_token = create_access_token(identity=username)
            response = make_response(redirect('/'))
            set_access_cookies(response, access_token)
            return response
        else:
            return render_template('verify_otp.html', error="Invalid OTP. Please try again.")
            
    return render_template('verify_otp.html')


@app.route('/logout')
def logout():
    response = make_response(redirect('/'))
    unset_jwt_cookies(response)
    return response


@app.route('/create-post', methods=['GET', 'POST'])
@jwt_required()
def create_post():
    current_username = get_jwt_identity()
    
    if request.method == 'POST':
        title = request.form['title'].strip()
        qustion = request.form['qustion'].strip()
        solution = request.form.get('solution', '').strip()
        raw_tags = request.form.get('tags', '').strip()
        
        if not raw_tags:
            return render_template('create_post.html', current_user=current_username, error="Please add at least one category hashtag.")
            
        formatted_tags = " ".join([t if t.startswith('#') else f"#{t}" for t in raw_tags.split()])
        
        data = suply(
            title=title,
            qustion=qustion,
            solution=solution,
            tags=formatted_tags,
            username=current_username
        )
        db.session.add(data)
        db.session.commit()

        for file in request.files.getlist('images'):
                if file and file.filename != '':
                    filename = secure_filename(file.filename)
                    file_bytes = file.read()

                    image_record = PostImage(
                        filename=filename,
                        image_data=file_bytes,
                        post_id=data.id
                    )
                    db.session.add(image_record)

                db.session.commit()
                return redirect('/')
        
    return render_template('create_post.html', current_user=current_username)

@app.route('/post-image/<int:image_id>')
def get_post_image(image_id):
    img = PostImage.query.get_or_404(image_id)
    return send_file(io.BytesIO(img.image_data), mimetype='image/jpeg')

@app.route('/delete-post/<int:post_id>', methods=['POST'])
@jwt_required()
def delete_post(post_id):
    post_item = suply.query.get_or_404(post_id)
    current_username = get_jwt_identity()
    
    if post_item.username == current_username:
        db.session.delete(post_item)
        db.session.commit()
        
    return redirect(request.referrer or '/')


@app.route('/add-comment/<int:post_id>', methods=['POST'])
@jwt_required()
def add_comment(post_id):
    text = request.form['text'].strip()
    parent_id = request.form.get('parent_id')
    current_username = get_jwt_identity()
    
    if text:
        new_comment = Comment(
            text=text,
            username=current_username,
            post_id=post_id,
            parent_id=int(parent_id) if parent_id else None
        )
        db.session.add(new_comment)
        db.session.commit()
        
    return redirect(request.referrer or '/')


@app.route('/delete-comment/<int:comment_id>', methods=['POST'])
@jwt_required()
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    current_username = get_jwt_identity()
    
    if comment.username == current_username:
        db.session.delete(comment)
        db.session.commit()
        
    return redirect(request.referrer or '/')


@app.route('/like/<int:post_id>', methods=['POST'])
@jwt_required()
def like_post(post_id):
    current_username = get_jwt_identity()
    existing_like = Like.query.filter_by(username=current_username, post_id=post_id).first()
    
    if existing_like:
        db.session.delete(existing_like)
    else:
        db.session.add(Like(username=current_username, post_id=post_id))
        
    db.session.commit()
    return redirect(request.referrer or '/')


@app.route('/like-comment/<int:comment_id>', methods=['POST'])
@jwt_required()
def like_comment(comment_id):
    current_username = get_jwt_identity()
    existing_like = CommentLike.query.filter_by(username=current_username, comment_id=comment_id).first()
    
    if existing_like:
        db.session.delete(existing_like)
    else:
        db.session.add(CommentLike(username=current_username, comment_id=comment_id))
        
    db.session.commit()
    return redirect(request.referrer or '/')


@app.route('/save/<int:post_id>', methods=['POST'])
@jwt_required()
def save_post(post_id):
    current_username = get_jwt_identity()
    existing_save = SavedPost.query.filter_by(username=current_username, post_id=post_id).first()
    
    if existing_save:
        db.session.delete(existing_save)
    else:
        db.session.add(SavedPost(username=current_username, post_id=post_id))
        
    db.session.commit()
    return redirect(request.referrer or '/')


@app.route('/verify-comment/<int:comment_id>', methods=['POST'])
@jwt_required()
def verify_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    current_username = get_jwt_identity()
    
    if comment.post.username == current_username:
        comment.is_verified = not comment.is_verified
        db.session.commit()
        
    return redirect(request.referrer or '/')


@app.route('/follow/<username>', methods=['POST'])
@jwt_required()
def toggle_follow(username):
    current_username = get_jwt_identity()
    if current_username == username:
        return redirect(request.referrer or '/profile')
        
    target_user = User.query.filter_by(username=username).first_or_404()
    existing_follow = Follow.query.filter_by(
        follower_username=current_username,
        following_username=target_user.username
    ).first()
    
    if existing_follow:
        db.session.delete(existing_follow)
    else:
        db.session.add(Follow(follower_username=current_username, following_username=target_user.username))
        
    db.session.commit()
    return redirect(request.referrer or f'/profile/{username}')


@app.route('/profile/<username>/followers')
@jwt_required(optional=True)
def view_followers(username):
    user = User.query.filter_by(username=username).first_or_404()
    follower_rels = Follow.query.filter_by(following_username=username).all()
    follower_usernames = [r.follower_username for r in follower_rels]
    followers = User.query.filter(User.username.in_(follower_usernames)).all()
    
    current_user = None
    try:
        identity = get_jwt_identity()
        if identity and User.query.filter_by(username=identity).first():
            current_user = identity
    except Exception:
        current_user = None
        
    user_follow_status = {}
    if current_user:
        for u in followers:
            user_follow_status[u.username] = Follow.query.filter_by(follower_username=current_user, following_username=u.username).first() is not None

    return render_template('user_list.html', title=f"Followers of @{username}", users=followers, current_user=current_user, user_follow_status=user_follow_status)


@app.route('/profile/<username>/following')
@jwt_required(optional=True)
def view_following(username):
    user = User.query.filter_by(username=username).first_or_404()
    following_rels = Follow.query.filter_by(follower_username=username).all()
    following_usernames = [r.following_username for r in following_rels]
    following_users = User.query.filter(User.username.in_(following_usernames)).all()
    
    current_user = None
    try:
        identity = get_jwt_identity()
        if identity and User.query.filter_by(username=identity).first():
            current_user = identity
    except Exception:
        current_user = None
        
    user_follow_status = {}
    if current_user:
        for u in following_users:
            user_follow_status[u.username] = Follow.query.filter_by(follower_username=current_user, following_username=u.username).first() is not None

    return render_template('user_list.html', title=f"Users followed by @{username}", users=following_users, current_user=current_user, user_follow_status=user_follow_status)


@app.route('/profile')
@jwt_required()
def profile():
    current_username = get_jwt_identity()
    user = User.query.filter_by(username=current_username).first_or_404()
    
    user_posts = suply.query.filter_by(username=current_username).order_by(suply.date_posted.desc()).all()
    verified_stars_count = Comment.query.filter_by(username=current_username, is_verified=True).count()
    
    followers_count = Follow.query.filter_by(following_username=current_username).count()
    following_count = Follow.query.filter_by(follower_username=current_username).count()

    return render_template(
        'profile.html',
        user=user,
        posts=user_posts,
        verified_stars_count=verified_stars_count,
        followers_count=followers_count,
        following_count=following_count,
        current_user=current_username
    )


@app.route('/edit-profile', methods=['GET', 'POST'])
@jwt_required()
def edit_profile():
    current_username = get_jwt_identity()
    user = User.query.filter_by(username=current_username).first_or_404()
    
    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_email = request.form.get('email', '').strip()
        new_bio = request.form.get('bio', '').strip()
        new_password = request.form.get('new_password', '').strip()
        
        if not new_username:
            return render_template('edit_profile.html', user=user, error="Username cannot be empty.")
            
        if new_email:
            email_owner = User.query.filter_by(email=new_email).first()
            if email_owner and email_owner.id != user.id:
                return render_template('edit_profile.html', user=user, error="This email is already used by another account.")
            user.email = new_email
        else:
            user.email = None

        user.bio = new_bio
        
        if new_password:
            if len(new_password) < 8:
                return render_template('edit_profile.html', user=user, error="New password must be at least 8 characters long.")
            user.password = generate_password_hash(new_password)

        pic_file = request.files.get('profile_pic')
        if pic_file and pic_file.filename != '':
            filename = secure_filename(pic_file.filename)
            pic_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            user.profile_pic = filename

        if new_username != user.username:
            if User.query.filter_by(username=new_username).first():
                return render_template('edit_profile.html', user=user, error="This username is already taken. Please choose another.")
            
            old_username = user.username
            suply.query.filter_by(username=old_username).update({'username': new_username})
            Comment.query.filter_by(username=old_username).update({'username': new_username})
            Like.query.filter_by(username=old_username).update({'username': new_username})
            SavedPost.query.filter_by(username=old_username).update({'username': new_username})
            CommentLike.query.filter_by(username=old_username).update({'username': new_username})
            Follow.query.filter_by(follower_username=old_username).update({'follower_username': new_username})
            Follow.query.filter_by(following_username=old_username).update({'following_username': new_username})
            
            user.username = new_username
            db.session.commit()
            
            access_token = create_access_token(identity=new_username)
            response = make_response(redirect('/profile'))
            set_access_cookies(response, access_token)
            return response

        db.session.commit()
        return redirect('/profile')
        
    return render_template('edit_profile.html', user=user, current_user=current_username)


@app.route('/activity')
@jwt_required()
def user_activity():
    current_username = get_jwt_identity()
    user = User.query.filter_by(username=current_username).first_or_404()
    
    liked_posts = [like.post for like in Like.query.filter_by(username=current_username).all() if like.post]
    saved_posts = [save.post for save in SavedPost.query.filter_by(username=current_username).all() if save.post]
    
    commented_comments = Comment.query.filter_by(username=current_username).all()
    commented_posts = list({c.post for c in commented_comments if c.post})
    
    liked_comment_records = CommentLike.query.filter_by(username=current_username).all()
    liked_comments_data = []
    for cl in liked_comment_records:
        if cl.comment and cl.comment.post:
            liked_comments_data.append({
                'comment': cl.comment,
                'post': cl.comment.post
            })
    
    return render_template(
        'activity.html',
        user=user,
        liked_posts=liked_posts,
        saved_posts=saved_posts,
        commented_posts=commented_posts,
        liked_comments_data=liked_comments_data,
        current_user=current_username
    )


@app.route('/profile/<username>')
@jwt_required(optional=True)
def view_profile(username):
    current_user = None
    try:
        identity = get_jwt_identity()
        if identity and User.query.filter_by(username=identity).first():
            current_user = identity
    except Exception:
        current_user = None

    if current_user == username:
        return redirect('/profile')
        
    user = User.query.filter_by(username=username).first_or_404()
    user_posts = suply.query.filter_by(username=username).order_by(suply.date_posted.desc()).all()
    verified_stars_count = Comment.query.filter_by(username=username, is_verified=True).count()
    
    followers_count = Follow.query.filter_by(following_username=username).count()
    following_count = Follow.query.filter_by(follower_username=username).count()
    
    is_following = False
    if current_user:
        is_following = Follow.query.filter_by(
            follower_username=current_user,
            following_username=username
        ).first() is not None
        
    return render_template(
        'view_profile.html',
        user=user,
        posts=user_posts,
        verified_stars_count=verified_stars_count,
        followers_count=followers_count,
        following_count=following_count,
        is_following=is_following,
        current_user=current_user
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)