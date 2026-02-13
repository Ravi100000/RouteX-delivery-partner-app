from delivery_app.app import create_app, db, Order, User

app = create_app()

with app.app_context():
    print(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    orders = Order.query.all()
    print(f"Total Orders: {len(orders)}")
    
    completed_orders = Order.query.filter_by(status='completed').all()
    print(f"Completed Orders: {len(completed_orders)}")
    
    for order in completed_orders:
        print(f"Order ID: {order.id}, Status: {order.status}, Amount: {order.amount}, Commission: {order.commission}")
        
    # Check total earnings query manually
    from sqlalchemy import func
    total_earnings = db.session.query(func.sum(Order.commission)).filter(Order.status == 'completed').scalar() or 0.0
    print(f"Calculated Total Earnings: {total_earnings}")
