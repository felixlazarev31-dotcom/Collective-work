from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'super-secret-key-for-todo-app'  # Ключ для работы сессий

db = SQLAlchemy(app)


# Модель Пользователя
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    todos = db.relationship('Todo', backref='user', lazy=True)


# Модель Задачи (связана с пользователем)
class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    complete = db.Column(db.Boolean, default=False)
    category = db.Column(db.String(50), default='Общее')
    due_date = db.Column(db.Date, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


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

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
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
            session.permanent = True  # Браузер запомнит вас, даже если закрыть вкладку
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# --- МАРШРУТЫ СПИСКА ДЕЛ ---

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Сортировка: сначала невыполненные, только задачи текущего пользователя
    todo_list = Todo.query.filter_by(user_id=session['user_id']).order_by(Todo.complete.asc(),
                                                                          Todo.due_date.asc()).all()
    return render_template('index.html', todo_list=todo_list, username=session['username'])


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


if __name__ == "__main__":
    with app.app_context():
          # Пересоздаем таблицы для обновления структуры под пользователей
        db.create_all()
    app.run(debug=True)
