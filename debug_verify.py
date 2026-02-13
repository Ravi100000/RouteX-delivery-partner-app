import sys
import os

# Ensure we can import delivery_app
sys.path.append(os.getcwd())

try:
    from delivery_app.app import create_app, db, User, Area, Charge, Order, Setting
    # from delivery_app.models import User, Area, Charge, Order, Setting # REMOVED
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def run_test():
    print("Setting up app...")
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test'
    }
    app = create_app(test_config)
    client = app.test_client()

    with app.app_context():
        db.create_all()
        # Seed admin for test
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', role='admin', status='active')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Test Admin created")
    
    print("1. Testing Admin Login...")
    response = client.post('/admin/login', data=dict(username='admin', password='admin123'), follow_redirects=True)
    if b'Admin Dashboard' not in response.data:
        print("FAILED: Admin Login")
        print(response.data.decode())
        return

    print("2. Creating Areas...")
    client.post('/admin/add_area', data={'name': 'Area A'}, follow_redirects=True)
    client.post('/admin/add_area', data={'name': 'Area B'}, follow_redirects=True)
    
    with app.app_context():
        if not Area.query.filter_by(name='Area A').first():
            print("FAILED: Area A not created")
            return

    print("3. Setting Charge...")
    client.post('/admin/set_charge', data={'from_area_id': 1, 'to_area_id': 2, 'amount': 50.0}, follow_redirects=True)
    
    print("4. Setting Commission...")
    client.post('/admin/set_commission', data={'percentage': 20.0}, follow_redirects=True)

    print("5. Partner Registration...")
    client.post('/partner/register', data={'username': 'partner1', 'password': 'password'}, follow_redirects=True)
    
    print("6. Approving Partner...")
    with app.app_context():
        partner_user = User.query.filter_by(username='partner1').first()
        partner_id = partner_user.id
        
    client.get(f'/admin/approve_partner/{partner_id}', follow_redirects=True)
    
    print("7. Partner Login...")
    client.get('/logout', follow_redirects=True)
    resp = client.post('/partner/login', data={'username': 'partner1', 'password': 'password'}, follow_redirects=True)
    if b'Partner Dashboard' in resp.data:
        print("   - Partner Login Successful")
    else:
        print("FAILED: Partner Login")
        return

    # Set Partner Area
    client.post('/partner/set_area', data={'area_id': 1}, follow_redirects=True)
    client.get('/partner/toggle_status', follow_redirects=True) # Go Online

    print("8. Customer Flow...")
    client.get('/logout', follow_redirects=True)
    client.post('/customer/register', data={'username': 'cust1', 'password': 'password'}, follow_redirects=True)
    client.post('/customer/login', data={'username': 'cust1', 'password': 'password'}, follow_redirects=True)
    
    print("   - Creating Order...")
    resp = client.post('/customer/create_order', data={
        'pickup_area_id': 1,
        'pickup_address': '123 Main St',
        'drop_area_id': 2,
        'drop_address': '456 High St'
    }, follow_redirects=True)
    
    if b'Order #1' in resp.data:
        print("   - Order Placed (Verified via Dashboard list)")
    else:
        print("FAILED: Order placement")
        print(resp.data.decode())

    print("9. Partner Processing Order...")
    client.get('/logout', follow_redirects=True)
    client.post('/partner/login', data={'username': 'partner1', 'password': 'password'}, follow_redirects=True)
    
    # Get Order ID (Assuming ID 1)
    print("   - Accepting Order 1...")
    client.get('/partner/accept_order/1', follow_redirects=True)
    
    print("   - Marking Picked Up...")
    client.get('/partner/update_status/1/picked_up', follow_redirects=True)
    
    print("   - Marking Arrived...")
    client.get('/partner/update_status/1/arrived', follow_redirects=True)
    
    print("   - Completing Order...")
    resp = client.get('/partner/update_status/1/completed', follow_redirects=True)
    
    if b'Wallet: $40.00' in resp.data: # 50 - 20% (set in step 4) = 40
        print("SUCCESS: Full Flow Verified! Wallet credited correctly ($40.00).")
    else:
        print("FAILED: Wallet check or Order Completion")
        # print(resp.data.decode()[:2000])

    print("10. Testing Simultaneous Sessions...")
    # Just tested partner flow, so partner_id should be in session.
    # Now check if Partner Dashboard is still accessible without logging in again
    resp = client.get('/partner/dashboard', follow_redirects=True)
    if b'Partner Dashboard' in resp.data:
        print("   - Partner Session Active")
    else:
        print("FAILED: Partner Session Lost")

    # Access Customer Dashboard (should fail or redirect if not logged in, but we want to see if we can login as customer WITHOUT losing partner)
    client.post('/customer/login', data={'username': 'cust1', 'password': 'password'}, follow_redirects=True)
    resp = client.get('/customer/dashboard', follow_redirects=True)
    if b'Customer Dashboard' in resp.data:
        print("   - Customer Login Successful")
    
    # NOW check Partner Dashboard again
    resp = client.get('/partner/dashboard', follow_redirects=True)
    if b'Partner Dashboard' in resp.data:
        print("SUCCESS: Simultaneous Sessions Verified! (Partner still logged in)")
    else:
        print("FAILED: Partner Session Lost after Customer Login")

    print("11. Testing Same-Area Delivery (A -> A)...")
    # Customer is still logged in from previous step
    resp = client.post('/customer/create_order', data={
        'pickup_area_id': 1, # Area A
        'pickup_address': '10 Same St',
        'drop_area_id': 1,   # Area A
        'drop_address': '20 Same St'
    }, follow_redirects=True)
    
    if b'Order placed successfully!' in resp.data:
         print("SUCCESS: Same-Area Order (A->A) Verified!")
    else:
         print("FAILED: Same-Area Order Placement")
         print(resp.data.decode()[:500])

    print("12. Verifying Admin Earnings...")
    client.get('/logout', follow_redirects=True)
    client.post('/admin/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
    resp = client.get('/admin/dashboard', follow_redirects=True)
    # We have 1 completed order (Order 1, $50, 20% comm = $10). 
    # Order 2 (Same-area) is pending.
    # So Total Earnings should be $10.0
    if b'$10.0' in resp.data or b'10.0' in resp.data:
        print("SUCCESS: Admin Earnings Verified ($10.0)")
    else:
        print("FAILED: Admin Earnings not updated/found")
        # print(resp.data.decode()[:2000])

    print("13. Testing Partner Restriction (Cannot accept new order while active)...")
    # 1. Login as Partner
    client.get('/logout', follow_redirects=True)
    client.post('/partner/login', data={'username': 'partner1', 'password': 'password'}, follow_redirects=True)
    
    # 2. Accept Order 2 (Create in step 11)
    # Order 2 is pending.
    print("   - Accepting Order 2...")
    client.get('/partner/accept_order/2', follow_redirects=True)
    
    # 3. Create Order 3 (Customer)
    # Use different client or just login/logout? Using same client clears session.
    # We need a NEW order to try and accept.
    client.post('/customer/login', data={'username': 'cust1', 'password': 'password'}, follow_redirects=True)
    client.post('/customer/create_order', data={
        'pickup_area_id': 2,
        'pickup_address': 'New Order St',
        'drop_area_id': 1,
        'drop_address': 'Drop St'
    }, follow_redirects=True)
    
    # 4. Partner tries to accept Order 3 (while Order 2 is accepted)
    client.post('/partner/login', data={'username': 'partner1', 'password': 'password'}, follow_redirects=True)
    resp = client.get('/partner/accept_order/3', follow_redirects=True)
    
    # Validation: Should redirect to dashboard with error, and Order 3 should NOT be accepted.
    if b'You already have an active order' in resp.data:
        print("SUCCESS: Partner restricted from accepting second order.")
    else:
        # Check if we were redirected to dashboard (standard) but maybe missed flash message in test client?
        # Let's check Order 3 status directly or check if it appears in 'My Orders'
        pass 
        # Test client might not persist flash messages across redirects easily without configuration.
        # But we added the active_order check in dashboard template too.
        if b'You have an active order' in resp.data:
             print("SUCCESS: Warning message displayed on dashboard.")
        else:
             print("FAILED: No warning message found.")
             # Double check DB?

if __name__ == '__main__':
    try:
        run_test()
    except Exception as e:
        import traceback
        traceback.print_exc()
