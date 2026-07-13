import os
from datetime import datetime, date
from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_super_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///todo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
# Инициализируем SocketIO для сетевого чата
socketio = SocketIO(app, cors_allowed_origins="*")


# --- МОДЕЛИ ДАННЫХ ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    todos = db.relationship('Todo', backref='user', lazy=True)
    messages = db.relationship('Message', backref='user', lazy=True)


class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    complete = db.Column(db.Boolean, default=False)
    category = db.Column(db.String(50), default='Общее')
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_all_users_stats():
    today = date.today()
    users = User.query.all()
    stats = []
    for user in users:
        total_tasks = Todo.query.filter_by(user_id=user.id).count()
        completed_tasks = Todo.query.filter_by(user_id=user.id, complete=True).count()
        today_tasks = Todo.query.filter_by(user_id=user.id, complete=False).filter(Todo.due_date == today).count()

        completed_today = Todo.query.filter_by(user_id=user.id, complete=True).filter(
            Todo.completed_at >= datetime(today.year, today.month, today.day)
        ).count()

        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        stats.append({
            'username': user.username,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'completion_rate': round(completion_rate, 1),
            'today_tasks': today_tasks,
            'completed_today': completed_today,
            'is_current_user': user.id == session.get('user_id')
        })
    stats.sort(key=lambda x: x['completed_tasks'], reverse=True)
    for i, stat in enumerate(stats, 1):
        stat['rank'] = i
    return stats


# --- МАРШРУТЫ АВТОРИЗАЦИИ ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_exists = User.query.filter_by(username=username).first()
        if user_exists:
            flash('Пользователь с таким именем уже существует!', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Регистрация успешна! Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# --- МАРШРУТЫ ПРИЛОЖЕНИЯ ---

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    todo_list = Todo.query.filter_by(user_id=session['user_id']).order_by(Todo.complete.asc(),
                                                                          Todo.due_date.asc()).all()
    chat_messages = Message.query.order_by(Message.timestamp.asc()).all()[-50:]
    all_users_stats = get_all_users_stats()

    return render_template('index.html',
                           todo_list=todo_list,
                           username=session.get('username'),
                           chat_messages=chat_messages,
                           all_users_stats=all_users_stats)


@app.route('/add', methods=['POST'])
def add():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    title = request.form.get('title')
    category = request.form.get('category') or 'Общее'
    date_str = request.form.get('due_date')
    due_date = None
    if date_str:
        due_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    if title:
        new_todo = Todo(title=title, complete=False, category=category, due_date=due_date, user_id=session['user_id'])
        db.session.add(new_todo)
        db.session.commit()
    return redirect(url_for('index'))


@app.route('/complete/<int:todo_id>')
def complete(todo_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    todo = Todo.query.get_or_404(todo_id)
    if todo.user_id == session['user_id']:
        todo.complete = not todo.complete
        todo.completed_at = datetime.utcnow() if todo.complete else None
        db.session.commit()
    return redirect(url_for('index'))


@app.route('/delete/<int:todo_id>')
def delete(todo_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    todo = Todo.query.get_or_404(todo_id)
    if todo.user_id == session['user_id']:
        db.session.delete(todo)
        db.session.commit()
    return redirect(url_for('index'))


# API для получения просроченных/невыполненных задач (для уведомлений)
@app.route('/api/overdue_tasks')
def overdue_tasks():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    today = date.today()
    # Ищем невыполненные задачи, у которых срок выполнения сегодня или уже прошёл
    tasks = Todo.query.filter_by(user_id=session['user_id'], complete=False).filter(Todo.due_date <= today).all()
    return jsonify([{'id': t.id, 'title': t.title, 'due_date': str(t.due_date)} for t in tasks])


@app.route('/api/stats')
def api_stats():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify(get_all_users_stats())


# --- ОБРАБОТЧИК СЕТЕВОГО ЧАТА (WebSocket) ---

@socketio.on('send_message')
def handle_message(data):
    # Метод получает данные без перезагрузки страницы и транслирует их всем
    user_id = session.get('user_id')
    username = session.get('username')
    if not user_id:
        return False

    content = data.get('message', '').strip()
    if content:
        new_msg = Message(content=content, user_id=user_id)
        db.session.add(new_msg)
        db.session.commit()

        # Рассылаем сообщение абсолютно всем подключенным пользователям сети
        emit('render_message', {
            'username': username,
            'content': content,
            'timestamp': datetime.utcnow().strftime('%H:%M')
        }, broadcast=True)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # Запуск через socketio вместо app.run для поддержки веб-сокетов
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)

