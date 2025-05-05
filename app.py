import os
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, g, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from flask_migrate import Migrate



# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config.update(
    SECRET_KEY='change-this-secret-key',
    SQLALCHEMY_DATABASE_URI='sqlite:///app.db',  # Убедитесь, что используете SQLite для хранения данных
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_FOLDER=UPLOAD_FOLDER
)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
# в app.py, рядом с другими моделями

favorites = db.Table('favorites',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('product_id', db.Integer, db.ForeignKey('product.id'))
)

# --- Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    reviews = db.relationship('Review', backref='user', lazy=True)
    purchases = db.relationship('Purchase', backref='user', lazy=True)
    favorites = db.relationship('Product', secondary=favorites, backref='liked_by')
    name = db.Column(db.String(100))
    email = db.Column(db.String(120))
    birthdate = db.Column(db.String(20))  # Можно также использовать Date, если хочется
    address = db.Column(db.String(200))


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    status = db.Column(db.String(50), default='In progress')
    date = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='orders')
    product = db.relationship('Product')

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    specs = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=True)  # 👈 Новое поле
    images = db.relationship('ProductImage', backref='product', lazy=True)
    reviews = db.relationship('Review', backref='product', lazy=True)
    purchases = db.relationship('Purchase', lazy=True, cascade="all, delete-orphan")


class ProductImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)

    product = db.relationship('Product')
    user = db.relationship('User', backref='cart_items')

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)

    product = db.relationship('Product')


# --- Helpers ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Load user on each request ---
@app.before_request
def load_user():
    g.user = None
    if 'user_id' in session:
        g.user = User.query.get(session['user_id'])

# --- Authentication Routes ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        uname = request.form['username']
        pwd = request.form['password']
        if not uname or not pwd:
            flash('Please fill in all fields.', 'danger')
        elif User.query.filter_by(username=uname).first():
            flash('Username is taken.', 'danger')
        else:
            user = User(username=uname, password_hash=generate_password_hash(pwd))
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html', body_class='no-sidebar')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form['username']
        pwd = request.form['password']
        user = User.query.filter_by(username=uname).first()
        if user and check_password_hash(user.password_hash, pwd):
            session.clear()
            session['user_id'] = user.id
            flash('Logged in successfully.', 'success')
            return redirect(url_for('index'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html', body_class='no-sidebar')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# --- Serve uploaded images ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Main Site Routes ---
from sqlalchemy import or_, and_
@app.route('/')
def index():
    query = Product.query
    search_query = request.args.get('search_query')
    if search_query:
        query = query.filter(Product.name.ilike(f"%{search_query}%"))

    categories = Product.query.with_entities(Product.category).distinct().all()
    all_categories = sorted({cat[0] for cat in categories if cat[0]})

    selected_categories = request.args.getlist('category')
    if selected_categories:
        query = query.filter(Product.category.in_(selected_categories))

    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)

    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    products = query.all()
    return render_template('index.html', products=products, categories=all_categories)


@app.route('/product/<int:pid>')
def product_detail(pid):
    p = Product.query.get_or_404(pid)
    return render_template('product_detail.html', product=p, body_class='no-sidebar')


@app.route('/buy/<int:pid>', methods=['POST'])
def buy(pid):
    if not g.user:
        return redirect(url_for('login'))
    product = Product.query.get_or_404(pid)
    purchase = Purchase(user_id=g.user.id, product_id=product.id)
    order = Order(user_id=g.user.id, product_id=product.id, status='In progress')
    db.session.add_all([purchase, order])
    db.session.commit()
    flash(f'You bought: {product.name}', 'success')
    return redirect(url_for('product_detail', pid=pid))

@app.route('/favorite/<int:pid>', methods=['POST'])
def toggle_favorite(pid):
    if not g.user:
        return redirect(url_for('login'))
    product = Product.query.get_or_404(pid)
    if product in g.user.favorites:
        g.user.favorites.remove(product)
        db.session.commit()
        flash('Removed from favorites.', 'info')
    else:
        g.user.favorites.append(product)
        db.session.commit()
        flash('Added to favorites!', 'success')
    return redirect(request.referrer or url_for('index'))


@app.route('/favorites')
def favorites_page():
    if not g.user:
        return redirect(url_for('login'))
    return render_template('favorites.html', products=g.user.favorites, body_class='no-sidebar')

@app.route('/cart')
def cart():
    if not g.user:
        return redirect(url_for('login'))
    cart_items = CartItem.query.filter_by(user_id=g.user.id).all()
    return render_template('cart.html', cart_items=cart_items, body_class='no-sidebar')


@app.route('/cart/add/<int:pid>', methods=['POST'])
def add_to_cart(pid):
    if not g.user:
        return redirect(url_for('login'))
    existing = CartItem.query.filter_by(user_id=g.user.id, product_id=pid).first()
    if existing:
        existing.quantity += 1
    else:
        cart_item = CartItem(user_id=g.user.id, product_id=pid)
        db.session.add(cart_item)
    db.session.commit()
    update_cart_total()
    flash('Product added to cart!', 'success')
    return redirect(url_for('index'))

@app.route('/cart/remove/<int:item_id>', methods=['POST'])
def remove_from_cart(item_id):
    item = CartItem.query.get_or_404(item_id)
    if g.user.id != item.user_id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('cart'))
    db.session.delete(item)
    db.session.commit()
    update_cart_total()
    flash('Item removed from cart.', 'info')
    return redirect(url_for('cart'))

@app.route('/profile/orders')
def orders():
    if not g.user:
        return redirect(url_for('login'))
    orders = Order.query.filter_by(user_id=g.user.id).order_by(Order.date.desc()).all()
    return render_template('profile/orders.html', orders=orders, body_class='no-sidebar')

@app.route('/profile/info', methods=['GET', 'POST'])
def profile_info():
    if not g.user:
        return redirect(url_for('login'))
    if request.method == 'POST':
        g.user.name = request.form.get('name')
        g.user.email = request.form.get('email')
        g.user.birthdate = request.form.get('birthdate')
        g.user.address = request.form.get('address')
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile_info'))
    return render_template('profile/personalInfo.html')

@app.route('/profile/orders/clear', methods=['POST'])
def clear_orders():
    if not g.user:
        return redirect(url_for('login'))
    Order.query.filter_by(user_id=g.user.id).delete()
    db.session.commit()
    flash('Order history cleared.', 'info')
    return redirect(url_for('orders'))

@app.route('/profile/purchases')
def all_purchases():
    if not g.user:
        return redirect(url_for('login'))
    purchases = Purchase.query.filter_by(user_id=g.user.id).all()
    return render_template('profile/allPurchases.html', purchases=purchases, body_class='no-sidebar')

@app.route('/profile/purchases/delete/<int:purchase_id>', methods=['POST'])
def delete_purchase(purchase_id):
    if not g.user:
        return redirect(url_for('login'))
    purchase = Purchase.query.get_or_404(purchase_id)
    if purchase.user_id != g.user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('profile'))
    db.session.delete(purchase)
    db.session.commit()
    flash('Purchase removed from history.', 'info')
    return redirect(url_for('all_purchases'))


@app.route('/product/<int:pid>/review', methods=['POST'])
def review(pid):
    if not g.user:
        return redirect(url_for('login'))
    r = int(request.form['rating'])
    c = request.form['comment']
    review = Review(user_id=g.user.id, product_id=pid, rating=r, comment=c)
    db.session.add(review)
    db.session.commit()
    flash('Thanks for your review!', 'success')
    return redirect(url_for('product_detail', pid=pid))

# --- Admin CRUD Routes ---
@app.route('/admin/products')
def admin_products():
    if not (g.user and g.user.is_admin):
        return redirect(url_for('login'))
    products = Product.query.all()
    return render_template('admin_products.html', products=products, body_class='no-sidebar')

@app.route('/admin/product/new', methods=['GET', 'POST'])
def admin_product_new():
    if not (g.user and g.user.is_admin):
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        desc = request.form['desc']
        specs = request.form['specs']
        price = float(request.form['price'])
        files = request.files.getlist('images')

        product = Product(name=name, category=category, description=desc, specs=specs, price=price)
        db.session.add(product)
        db.session.commit()

        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                img = ProductImage(product_id=product.id, filename=filename)
                db.session.add(img)

        db.session.commit()
        flash('Product added successfully!', 'success')
        return redirect(url_for('admin_products'))

    return render_template('admin_product_form.html', action='new', product=None, body_class='no-sidebar')


@app.route('/admin/product/edit/<int:pid>', methods=['GET', 'POST'])
def admin_product_edit(pid):
    if not (g.user and g.user.is_admin):
        return redirect(url_for('login'))

    product = Product.query.get_or_404(pid)

    if request.method == 'POST':
        product.name = request.form['name']
        product.description = request.form['desc']
        product.specs = request.form['specs']
        product.price = float(request.form['price'])

        # ✅ ДОБАВИ ЭТУ СТРОКУ — ОБНОВЛЕНИЕ КАТЕГОРИИ
        product.category = request.form.get('category')

        files = request.files.getlist('images')
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                img = ProductImage(product_id=product.id, filename=filename)
                db.session.add(img)

        db.session.commit()
        flash('Product updated successfully!', 'success')
        return redirect(url_for('admin_products'))

    return render_template('admin_product_form.html', action='edit', product=product, body_class='no-sidebar')

@app.route('/admin/product/delete/<int:pid>', methods=['POST'])
def admin_product_delete(pid):
    if not (g.user and g.user.is_admin):
        return redirect(url_for('login'))

    product = Product.query.get_or_404(pid)
    # Удаляем изображения с диска
    for img in product.images:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], img.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        db.session.delete(img)  # Удаляем и из базы данных
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully!', 'success')
    return redirect(url_for('admin_products'))


@app.route('/profile')
def profile():
    if not g.user:
        return redirect(url_for('login'))

    purchases = Purchase.query.filter_by(user_id=g.user.id).all()
    return render_template('profile.html', purchases=purchases, body_class='no-sidebar')

@app.template_filter('format_price')
def format_price(value):
    try:
        return f"{value:,.0f}".replace(",", " ")
    except:
        return value


def update_cart_total():
    if not g.user:
        session['cart_total'] = 0.0
        return

    cart_items = CartItem.query.filter_by(user_id=g.user.id).all()
    total = sum(item.product.price * item.quantity for item in cart_items if item.product)
    session['cart_total'] = round(total, 2)



# --- Initialize Database & Admin Account ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Создание базы данных
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', password_hash=generate_password_hash('admin'), is_admin=True)
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True)
