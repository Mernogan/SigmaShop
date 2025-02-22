import os
from flask import Flask, render_template, url_for, request, redirect, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError
from models import db, User, Product, ProductImage, Cart

app = Flask(__name__)
app.secret_key = "key"  # Обязательно измените в production!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Инициализируем SQLAlchemy с приложением Flask
db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
def home_page():
    return render_template('index.html')

@app.route("/shop")
def shop():
    query = request.args.get('query', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 9

    if query:
        products = Product.query.filter(Product.name.ilike(f'%{query}%')).paginate(page=page, per_page=per_page)
    else:
        products = Product.query.paginate(page=page, per_page=per_page)
    
    return render_template('shop.html', products=products)

@app.route("/profile")
@login_required
def profile():
    user_products = Product.query.filter_by(user_id=current_user.id).all()
    return render_template("profile.html", products=user_products)

@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Проверка, существует ли пользователь с таким email или username
        existing_user = User.query.filter((User.email == email) | (User.username == username)).first()
        if existing_user:
            flash('Пользователь с таким email или именем уже существует!', 'danger')
            return redirect(url_for('register'))

        # Создание нового пользователя
        user = User(username=username, email=email, password=password)
        db.session.add(user)

        try:
            db.session.commit()
            flash('Регистрация прошла успешно!', 'success')
            return redirect(url_for('login'))
        except IntegrityError:
            db.session.rollback()
            flash('Произошла ошибка при регистрации. Пользователь с таким email или именем уже существует.', 'danger')
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_input = request.form['login_input']
        password = request.form['password']
        user = User.query.filter((User.username == login_input) | (User.email == login_input)).first()
        if user and user.password == password:
            login_user(user)
            flash('Вход выполнен успешно!', 'success')
            return redirect(url_for('profile'))
        else:
            flash('Неверные данные для входа', 'danger')
    return render_template('login.html')

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('home_page'))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

@app.route("/add_product", methods=['GET', 'POST'])
@login_required
def add_product():
    if not current_user.is_approved:
        flash('Вы не одобрены для добавления товаров. Обратитесь к администратору.', 'danger')
        return redirect(url_for('shop'))

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = request.form['price']
        images = request.files.getlist('images')

        # Создаем товар
        product = Product(name=name, description=description, price=price, user_id=current_user.id)
        db.session.add(product)
        db.session.commit()

        # Обрабатываем изображения
        for image in images:
            if image and allowed_file(image.filename):
                filename = secure_filename(image.filename)
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image.save(image_path)
                product_image = ProductImage(image_path=url_for('static', filename=f'uploads/{filename}'), product_id=product.id)
                db.session.add(product_image)

        db.session.commit()
        flash('Товар успешно добавлен!', 'success')
        return redirect(url_for('shop'))

    return render_template('add_product.html')

@app.route("/delete_product/<int:product_id>", methods=['POST'])
@login_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Проверяем, что текущий пользователь является владельцем товара
    if product.user_id != current_user.id:
        flash('У вас нет прав на удаление этого товара.', 'danger')
        return redirect(url_for('profile'))

    # Удаляем изображения товара
    for image in product.images:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(image.image_path)))
        except FileNotFoundError:
            pass  # Если файл не найден, просто пропускаем

    # Удаляем товар из базы данных
    db.session.delete(product)
    db.session.commit()
    flash('Товар успешно удален.', 'success')
    return redirect(url_for('profile'))

@app.route("/edit_product/<int:product_id>", methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Проверяем, что текущий пользователь является владельцем товара
    if product.user_id != current_user.id:
        flash('У вас нет прав на редактирование этого товара.', 'danger')
        return redirect(url_for('profile'))

    if request.method == 'POST':
        # Обновляем данные товара
        product.name = request.form['name']
        product.description = request.form['description']
        product.price = request.form['price']

        # Обрабатываем новые изображения
        new_images = request.files.getlist('images')
        for image in new_images:
            if image and allowed_file(image.filename):
                filename = secure_filename(image.filename)
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image.save(image_path)
                product_image = ProductImage(image_path=url_for('static', filename=f'uploads/{filename}'), product_id=product.id)
                db.session.add(product_image)

        db.session.commit()
        flash('Товар успешно обновлен!', 'success')
        return redirect(url_for('profile'))

    return render_template('edit_product.html', product=product)

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('product_detail.html', product=product)

@app.route("/add_to_cart/<int:product_id>")
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    cart_item = Cart.query.filter_by(user_id=current_user.id, product_id=product.id).first()
    if cart_item:
        cart_item.quantity += 1
    else:
        cart_item = Cart(user_id=current_user.id, product_id=product.id)
        db.session.add(cart_item)
    db.session.commit()
    flash('Товар добавлен в корзину!', 'success')
    return redirect(url_for('shop'))

@app.route("/cart")
@login_required
def cart():
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route("/remove_from_cart/<int:cart_id>")
@login_required
def remove_from_cart(cart_id):
    cart_item = Cart.query.get_or_404(cart_id)
    if cart_item.user_id != current_user.id:
        flash('У вас нет прав на удаление этого товара.', 'danger')
        return redirect(url_for('cart'))

    db.session.delete(cart_item)
    db.session.commit()
    flash('Товар удален из корзины.', 'success')
    return redirect(url_for('cart'))

if __name__ == "__main__":
    with app.app_context():
        # Создаем папку для загрузки изображений, если она не существует
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        
        db.create_all()
    app.run(debug=True)