from flask import Flask, render_template, request, redirect, url_for, flash, session, g, Blueprint
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_
from datetime import datetime
import functools
import os

db = SQLAlchemy()

# ================= MODELS =================

class User(db.Model):
    __tablename__ = 'users'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False) 
    role = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='active')
    wallet_balance = db.Column(db.Float, default=0.0)
    is_online = db.Column(db.Boolean, default=False)
    current_area_id = db.Column(db.Integer, db.ForeignKey('areas.id'), nullable=True)
    
    orders_placed = db.relationship('Order', foreign_keys='Order.customer_id', backref='customer', lazy=True)
    orders_delivered = db.relationship('Order', foreign_keys='Order.partner_id', backref='partner', lazy=True)

    def set_password(self, password):
        self.password_hash = password

    def check_password(self, password):
        return self.password_hash == password

    @property
    def is_authenticated(self):
        return True

class Area(db.Model):
    __tablename__ = 'areas'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class Charge(db.Model):
    __tablename__ = 'charges'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    from_area_id = db.Column(db.Integer, db.ForeignKey('areas.id'), nullable=False)
    to_area_id = db.Column(db.Integer, db.ForeignKey('areas.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)

    from_area = db.relationship('Area', foreign_keys=[from_area_id])
    to_area = db.relationship('Area', foreign_keys=[to_area_id])

class Order(db.Model):
    __tablename__ = 'orders'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    partner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    pickup_area_id = db.Column(db.Integer, db.ForeignKey('areas.id'), nullable=False)
    drop_area_id = db.Column(db.Integer, db.ForeignKey('areas.id'), nullable=False)
    pickup_area = db.relationship('Area', foreign_keys=[pickup_area_id])
    drop_area = db.relationship('Area', foreign_keys=[drop_area_id])
    pickup_address = db.Column(db.String(200), nullable=False)
    drop_address = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='pending')
    amount = db.Column(db.Float, nullable=False)
    commission = db.Column(db.Float, default=0.0)
    rating = db.Column(db.Integer, nullable=True)
    rating_comment = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Setting(db.Model):
    __tablename__ = 'settings'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200), nullable=False)

# ================= ROUTES =================

# --- ADMIN ---
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('admin.login'))
        return view(**kwargs)
    return wrapped_view

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username, role='admin').first()
        if user and user.check_password(password):
            # session.clear()
            session.permanent = True
            session['admin_id'] = user.id
            return redirect(url_for('admin.dashboard'))
        flash('Invalid credentials/role', 'error')
    return render_template('login.html', role='admin')

@admin_bp.route('/dashboard')
@admin_login_required
def dashboard():
    if g.user.role != 'admin': return redirect(url_for('auth_logout'))
    areas = Area.query.all()
    charges = Charge.query.all()
    pending_partners = User.query.filter_by(role='partner', status='pending').all()
    active_partners = User.query.filter_by(role='partner', status='active').all()
    commission_setting = Setting.query.filter_by(key='commission_percentage').first()
    current_commission = commission_setting.value if commission_setting else "10.0"
    for partner in active_partners:
        avg_rating = db.session.query(func.avg(Order.rating)).filter(Order.partner_id == partner.id).scalar()
        partner.rating_avg = avg_rating
    total_earnings = db.session.query(func.sum(Order.commission)).filter(Order.status == 'completed').scalar() or 0.0
    total_orders = Order.query.count()
    return render_template('admin_dashboard.html', areas=areas, charges=charges, pending_partners=pending_partners, active_partners=active_partners, total_earnings=total_earnings, current_commission=current_commission, total_orders=total_orders)

@admin_bp.route('/set_commission', methods=['POST'])
@admin_login_required
def set_commission():
    if g.user.role != 'admin': return redirect(url_for('admin.login'))
    percentage = request.form.get('percentage')
    if percentage:
        setting = Setting.query.filter_by(key='commission_percentage').first()
        if setting: setting.value = percentage
        else:
            setting = Setting(key='commission_percentage', value=percentage)
            db.session.add(setting)
        db.session.commit()
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/add_area', methods=['POST'])
@admin_login_required
def add_area():
    if g.user.role != 'admin': return redirect(url_for('admin.login'))
    name = request.form.get('name')
    if name:
        if not Area.query.filter_by(name=name).first():
            db.session.add(Area(name=name))
            db.session.commit()
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/set_charge', methods=['POST'])
@admin_login_required
def set_charge():
    if g.user.role != 'admin': return redirect(url_for('admin.login'))
    from_id = request.form.get('from_area_id')
    to_id = request.form.get('to_area_id')
    amount = request.form.get('amount')
    if from_id and to_id and amount:
        charge = Charge.query.filter_by(from_area_id=from_id, to_area_id=to_id).first()
        if charge: charge.amount = float(amount)
        else: db.session.add(Charge(from_area_id=from_id, to_area_id=to_id, amount=float(amount)))
        db.session.commit()
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/approve_partner/<int:partner_id>')
@admin_login_required
def approve_partner(partner_id):
    if g.user.role != 'admin': return redirect(url_for('admin.login'))
    partner = User.query.get(partner_id)
    if partner and partner.role == 'partner':
        partner.status = 'active'
        db.session.commit()
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/remove_partner/<int:partner_id>')
@admin_login_required
def remove_partner(partner_id):
    if g.user.role != 'admin': return redirect(url_for('admin.login'))
    partner = User.query.get(partner_id)
    if partner and partner.role == 'partner':
        db.session.delete(partner)
        db.session.commit()
    return redirect(url_for('admin.dashboard'))

# --- PARTNER ---
partner_bp = Blueprint('partner', __name__, url_prefix='/partner')

def partner_login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('partner.login'))
        return view(**kwargs)
    return wrapped_view

@partner_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not User.query.filter_by(username=username).first():
            user = User(username=username, role='partner', status='pending')
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            return redirect(url_for('partner.login'))
    return render_template('register.html', role='partner')

@partner_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username, role='partner').first()
        if user and user.check_password(password):
            if user.status == 'active':
                # session.clear()
                session.permanent = True
                session['partner_id'] = user.id
                return redirect(url_for('partner.dashboard'))
    return render_template('login.html', role='partner')

@partner_bp.route('/dashboard')
@partner_login_required
def dashboard():
    if g.user.role != 'partner': return redirect(url_for('partner.login'))
    areas = Area.query.all()
    my_orders = Order.query.filter_by(partner_id=g.user.id).filter(Order.status.in_(['accepted', 'picked_up', 'arrived'])).all()
    has_active_order = len(my_orders) > 0
    current_area_name = None
    available_orders = []
    if g.user.current_area_id:
        area = Area.query.get(g.user.current_area_id)
        if area: current_area_name = area.name
        if g.user.is_online and not has_active_order: # Only show available if no active order? Or show but disable? Let's hide for simplicity or filter logic here.
             available_orders = Order.query.filter_by(pickup_area_id=g.user.current_area_id, status='pending').all()
    return render_template('partner_dashboard.html', areas=areas, available_orders=available_orders, my_orders=my_orders, current_area_name=current_area_name, has_active_order=has_active_order)

@partner_bp.route('/toggle_status')
@partner_login_required
def toggle_status():
    if g.user.role != 'partner': return redirect(url_for('partner.login'))
    g.user.is_online = not g.user.is_online
    db.session.commit()
    return redirect(url_for('partner.dashboard'))

@partner_bp.route('/set_area', methods=['POST'])
@partner_login_required
def set_area():
    if g.user.role != 'partner': return redirect(url_for('partner.login'))
    area_id = request.form.get('area_id')
    if area_id:
        g.user.current_area_id = int(area_id)
        db.session.commit()
    return redirect(url_for('partner.dashboard'))

@partner_bp.route('/accept_order/<int:order_id>')
@partner_login_required
def accept_order(order_id):
    if g.user.role != 'partner': return redirect(url_for('partner.login'))
    
    # Check if partner already has an active order
    active_order = Order.query.filter_by(partner_id=g.user.id).filter(Order.status.in_(['accepted', 'picked_up', 'arrived'])).first()
    if active_order:
        flash('You already have an active order. Please complete it first.', 'error')
        return redirect(url_for('partner.dashboard'))

    order = Order.query.get(order_id)
    if order and order.status == 'pending':
        order.partner_id = g.user.id
        order.status = 'accepted'
        db.session.commit()
    return redirect(url_for('partner.dashboard'))

@partner_bp.route('/update_status/<int:order_id>/<status>')
@partner_login_required
def update_status(order_id, status):
    if g.user.role != 'partner': return redirect(url_for('partner.login'))
    order = Order.query.get(order_id)
    if order and order.partner_id == g.user.id:
        if status in ['picked_up', 'arrived', 'completed', 'declined']:
             if status == 'declined':
                 # Partner cancels/declines after accepting -> Reset to pending
                 order.status = 'pending'
                 order.partner_id = None
             else:
                 order.status = status
                 if status == 'completed':
                     # Credit Partner Wallet: Amount - Commission
                     earning = order.amount - order.commission
                     partner = User.query.get(g.user.id)
                     partner.wallet_balance += earning
             db.session.commit()
    return redirect(url_for('partner.dashboard'))

# --- CUSTOMER ---
customer_bp = Blueprint('customer', __name__, url_prefix='/customer')

def customer_login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('customer.login'))
        return view(**kwargs)
    return wrapped_view

@customer_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not User.query.filter_by(username=username).first():
            user = User(username=username, role='customer', status='active')
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            return redirect(url_for('customer.login'))
    return render_template('register.html', role='customer')

@customer_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username, role='customer').first()
        if user and user.check_password(password):
            # session.clear()
            session.permanent = True
            session['customer_id'] = user.id
            return redirect(url_for('customer.dashboard'))
    return render_template('login.html', role='customer')

@customer_bp.route('/dashboard')
@customer_login_required
def dashboard():
    if g.user.role != 'customer': return redirect(url_for('customer.login'))
    areas = Area.query.all()
    active_orders = Order.query.filter(Order.customer_id == g.user.id, Order.status.in_(['pending', 'accepted', 'picked_up', 'arrived'])).all()
    completed_orders = Order.query.filter(Order.customer_id == g.user.id, Order.status == 'completed').all()
    return render_template('customer_dashboard.html', areas=areas, active_orders=active_orders, completed_orders=completed_orders)

@customer_bp.route('/create_order', methods=['POST'])
@customer_login_required
def create_order():
    if g.user.role != 'customer': return redirect(url_for('customer.login'))
    pickup_area_id = request.form.get('pickup_area_id')
    pickup_address = request.form.get('pickup_address')
    drop_area_id = request.form.get('drop_area_id')
    drop_address = request.form.get('drop_address')
    if pickup_area_id and drop_area_id:
        charge = Charge.query.filter_by(from_area_id=pickup_area_id, to_area_id=drop_area_id).first()
        if charge:
            amount = charge.amount
            commission_setting = Setting.query.filter_by(key='commission_percentage').first()
            commission_rate = float(commission_setting.value) if commission_setting else 10.0
            commission = amount * (commission_rate / 100.0)
            order = Order(customer_id=g.user.id, pickup_area_id=pickup_area_id, drop_area_id=drop_area_id, pickup_address=pickup_address, drop_address=drop_address, amount=amount, commission=commission, status='pending')
            db.session.add(order)
            db.session.commit()
            flash('Order placed successfully!', 'success')
        else:
            flash('Delivery not available between these areas.', 'error')
    else:
        flash('Please fill all fields.', 'error')
    return redirect(url_for('customer.dashboard'))

@customer_bp.route('/rate_order/<int:order_id>', methods=['POST'])
@customer_login_required
def rate_order(order_id):
    if g.user.role != 'customer': return redirect(url_for('customer.login'))
    order = Order.query.get(order_id)
    if order and order.customer_id == g.user.id and order.status == 'completed':
        rating = request.form.get('rating')
        if rating and rating.isdigit():
            order.rating = int(rating)
            order.rating_comment = request.form.get('comment') # Optional comment
            db.session.commit()
            flash('Thank you for rating!', 'success')
    return redirect(url_for('customer.dashboard'))

# ================= APP FACTORY =================

def create_app(test_config=None):
    app = Flask(__name__)
    if test_config is None:
        app.config.from_mapping(
            SECRET_KEY=os.environ.get('SECRET_KEY') or 'dev_secret_key',
            SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(app.instance_path, 'delivery.db'),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        try:
            os.makedirs(app.instance_path)
        except OSError:
            pass

    # Config for Session Persistence
    from datetime import timedelta
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    
    if test_config:
        app.config.from_mapping(test_config)

    db.init_app(app)

    @app.before_request
    def load_logged_in_user():
        g.user = None
        if request.path.startswith('/admin'):
            user_id = session.get('admin_id')
            if user_id: g.user = User.query.get(user_id)
        elif request.path.startswith('/partner'):
            user_id = session.get('partner_id')
            if user_id: g.user = User.query.get(user_id)
        elif request.path.startswith('/customer'):
            user_id = session.get('customer_id')
            if user_id: g.user = User.query.get(user_id)

    @app.context_processor
    def inject_user():
        return dict(current_user=g.user)

    app.register_blueprint(admin_bp)
    app.register_blueprint(partner_bp)
    app.register_blueprint(customer_bp)

    @app.route('/logout')
    def auth_logout():
        session.clear()
        return redirect(url_for('index'))

    @app.route('/')
    def index():
        return render_template('landing.html')

    with app.app_context():
        db.create_all()
        # Seed
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', role='admin', status='active')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Default admin created: admin/admin123")
        
        # Seed Partner
        if not User.query.filter_by(username='partner').first():
            partner = User(username='partner', role='partner', status='active')
            partner.set_password('partner123')
            db.session.add(partner)
            db.session.commit()
            print("Default partner created: partner/partner123")

        # Seed Customer
        if not User.query.filter_by(username='customer').first():
            customer = User(username='customer', role='customer', status='active')
            customer.set_password('customer123')
            db.session.add(customer)
            db.session.commit()
            print("Default customer created: customer/customer123")

        # Seed Areas
        area_a = Area.query.filter_by(name='Area A').first()
        if not area_a:
            area_a = Area(name='Area A')
            db.session.add(area_a)
            db.session.commit()
            print("Default Area A created")

        area_b = Area.query.filter_by(name='Area B').first()
        if not area_b:
            area_b = Area(name='Area B')
            db.session.add(area_b)
            db.session.commit()
            print("Default Area B created")
            
        # Seed Charges
        charges_data = [
            (area_a.id, area_b.id, 50.0),
            (area_b.id, area_a.id, 50.0),
            (area_a.id, area_a.id, 30.0),
            (area_b.id, area_b.id, 30.0),
        ]
        
        for from_id, to_id, amount in charges_data:
            charge = Charge.query.filter_by(from_area_id=from_id, to_area_id=to_id).first()
            if not charge:
                db.session.add(Charge(from_area_id=from_id, to_area_id=to_id, amount=amount))
                db.session.commit()
                print(f"Default Charge {from_id} -> {to_id} (${amount}) created")

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0')