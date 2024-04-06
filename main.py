from flask import Flask, request, session, render_template, redirect, url_for, flash, get_flashed_messages, jsonify
from flask.globals import current_app
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin, AnonymousUserMixin
from datetime import timedelta, datetime
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from os import error, path
from flask_sqlalchemy import SQLAlchemy
import random
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_session import Session

app = Flask(__name__)
DB_NAME = "spark.db"
app.config["SECRET_KEY"] = "1986319249872139865432"
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DB_NAME}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config['SESSION_TYPE'] = 'filesystem'


Session(app)

socketio = SocketIO(app, manage_session=False)

db = SQLAlchemy(app)
db.init_app(app)

def create_database(app):
    if not path.exists(DB_NAME):
        db.create_all(app=app)
        print("Created Database!")

class Tutor(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    tremail = db.Column(db.String(10000))
    trusername = db.Column(db.String(1200))
    subjects = db.Column(db.String(1200))
    session_length = db.Column(db.String(1200))

class Messages(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.String(1200), unique=True, nullable=False)
    content = db.Column(db.String(10000))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    username = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))
    tutors = db.relationship('Tutor')


create_database(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)
@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


@app.route("/")
@login_required
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET", 'POST'])
def login():
    if request.method == "POST":
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user:
            if check_password_hash(user.password, password):
                flash('Login successful!', category="success")
                login_user(user, remember=True)
                return redirect(url_for("home"))
            else:
                flash('Incorrect password! Please try again.', category="error")
        else:
            flash("Account does not exist. Please register to continue.", category="error")


    return render_template("login.html", user=current_user)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password1 = request.form.get('password1')
        password2 = request.form.get('password2')

        user = User.query.filter_by(email=email).first()
        if user:
            flash("Email already exists.", category="error")
        elif len(email) < 4:
            flash("Email must be greater than 3 characters.", category="error")
        elif len(username) < 2:
            flash("Username must be greater than 1 character.", category="error")
        elif password1 != password2:
            flash("Passwords do not match! Please try again.", category="error")
        elif len(password1) < 8:
            flash("Password must be greater than 7 characters.", category="error")
        else:
            new_user = User(email=email, username=username, password=generate_password_hash(password1, method='sha256'))
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user, remember=True)
            flash("Account successfully created!", category="success")

            return redirect(url_for('home'))

    return render_template("register.html", user=current_user)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out succcessfully!", category="success")
    return redirect(url_for('login'))

@app.route("/selection")
@login_required
def selection():
    return render_template("selection.html")

@app.route("/tutorform", methods=['GET', 'POST'])
@login_required
def tutorform():
    if request.method == 'POST':
        email = request.form.get('email')
        tremail = request.form.get('tremail')
        trusername = request.form.get('trusername')
        subjects = request.form.get('subjects')
        session_length = request.form.get('session_length')

        new_tutor = Tutor(user_id=current_user.id, tremail=tremail, trusername=trusername, subjects=subjects, session_length=session_length)
        db.session.add(new_tutor)
        db.session.commit()
        flash('Entry has been saved!', category='success')
        return redirect(url_for("display"))

    return render_template("tutorform.html", user=current_user)

@app.route("/tutoreeform", methods=['GET', 'POST'])
@login_required
def tutoreeform():
    if request.method == 'POST':
        flash("Tutoree Entry Successful!", category='success')
        return redirect(url_for("display"))

    return render_template("tutoreeform.html")

@app.route("/display")
@login_required
def display():
    users = Tutor.query.all()

    return render_template("display.html", users=users)

@login_required
@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if(request.method=='POST'):
        username = current_user.username
        room = request.form['room']
        #Store the data in session
        session['username'] = username
        session['room'] = room
        return render_template('chat.html', session = session)
    else:
        if(current_user.username is not None):
            return render_template('chat.html', session = session)
        else:
            return redirect(url_for('chatselection'))

class Anonymous(AnonymousUserMixin):
    def __init__(self):
        self.username = 'Guest'

@socketio.on('join', namespace='/chat')
@login_required
def join(message):
    room = session.get('room')
    join_room(room)
    emit('status', {'msg': current_user.username + ' has entered the room.'}, room=room)


@socketio.on('text', namespace='/chat')
@login_required
def text(message):
    room = session.get('room')

    message = Messages(room_id=room, content=message)
    db.session.add(message)
    db.session.commit()
    emit('message', {'msg': session.get('username') + ' : ' + message['msg']}, room=room)

@socketio.on('left', namespace='/chat')
@login_required
def left(message):
    room = session.get('room')
    leave_room(room)
    session.clear()
    emit('status', {'msg': current_user.username + ' has left the room.'}, room=room)

@app.route("/chatselection", methods=['GET', 'POST'])
def chatselection():
    return render_template("chatselection.html")


if __name__ == '__main__':
    db.create_all()
    socketio.run(app, debug=True)