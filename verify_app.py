import unittest
from delivery_app.app import create_app, db, User, Area, Charge, Order, Setting

class DeliveryAppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['WTF_CSRF_ENABLED'] = False # If using WTForms, but we are using raw forms
        self.client = self.app.test_client()
        
        with self.app.app_context():
            db.create_all()
            # Default admin is created by app.py but let's ensure fresh start if logic changes
            # app.py creates it if not exists.
            
    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self, username, password, role_url):
        return self.client.post(role_url, data=dict(
            username=username,
            password=password
        ), follow_redirects=True)

    def test_full_flow(self):
        # 1. Admin Login & Setup
        with self.app.app_context():
            # Admin already created by app start
            pass

        response = self.login('admin', 'admin123', '/admin/login')
        self.assertIn(b'Admin Dashboard', response.data)

        # Create Areas
        self.client.post('/admin/add_area', data={'name': 'Area A'}, follow_redirects=True)
        self.client.post('/admin/add_area', data={'name': 'Area B'}, follow_redirects=True)
        
        with self.app.app_context():
            area_a = Area.query.filter_by(name='Area A').first()
            area_b = Area.query.filter_by(name='Area B').first()
            self.assertIsNotNone(area_a)
            self.assertIsNotNone(area_b)

        # Set Charge A->B
        self.client.post('/admin/set_charge', data={
            'from_area_id': 1, # ID 1
            'to_area_id': 2,   # ID 2
            'amount': 50.0
        }, follow_redirects=True)

        # Set Commission
        self.client.post('/admin/set_commission', data={'percentage': 20.0}, follow_redirects=True)

        # 2. Partner Registration
        self.client.post('/partner/register', data={
            'username': 'partner1',
            'password': 'password'
        }, follow_redirects=True)
        
        # Admin Approve Partner
        with self.app.app_context():
            partner_to_approve = User.query.filter_by(username='partner1').first()
            partner_id = partner_to_approve.id
        
        self.client.get(f'/admin/approve_partner/{partner_id}', follow_redirects=True)
        
        with self.app.app_context():
            partner = User.query.filter_by(username='partner1').first()
            self.assertEqual(partner.status, 'active')

        # 3. Partner Login & Setup
        self.client.get('/logout', follow_redirects=True)
        response = self.login('partner1', 'password', '/partner/login')
        self.assertIn(b'Partner Dashboard', response.data)
        
        # Go Online
        self.client.get('/partner/toggle_status', follow_redirects=True)
        
        # Set Area
        self.client.post('/partner/set_area', data={'area_id': 1}, follow_redirects=True) # Area A

        # 4. Customer Registration & Order
        self.client.get('/logout', follow_redirects=True)
        self.client.post('/customer/register', data={
            'username': 'cust1',
            'password': 'password'
        }, follow_redirects=True)
        self.login('cust1', 'password', '/customer/login')
        
        # Place Order area A -> B
        response = self.client.post('/customer/create_order', data={
            'pickup_area_id': 1,
            'pickup_address': '123 Main St',
            'drop_area_id': 2,
            'drop_address': '456 High St'
        }, follow_redirects=True)
        self.assertIn(b'Order placed successfully', response.data)

        # 5. Partner Accept & Complete
        self.client.get('/logout', follow_redirects=True)
        self.login('partner1', 'password', '/partner/login')
        
        response = self.client.get('/partner/dashboard')
        self.assertIn(b'123 Main St', response.data) # See available order
        
        # Accept (Order ID 1)
        self.client.get('/partner/accept_order/1', follow_redirects=True)
        
        # Update Status
        self.client.get('/partner/update_status/1/picked_up', follow_redirects=True)
        self.client.get('/partner/update_status/1/arrived', follow_redirects=True)
        self.client.get('/partner/update_status/1/completed', follow_redirects=True)

        # 6. Customer Rate
        self.client.get('/logout', follow_redirects=True)
        self.login('cust1', 'password', '/customer/login')
        self.client.post('/customer/rate_order/1', data={'rating': 5}, follow_redirects=True)
        
        # 7. Admin Check Earnings
        self.client.get('/logout', follow_redirects=True)
        self.login('admin', 'admin123', '/admin/login')
        response = self.client.get('/admin/dashboard')
        
        # Expected Commission: 50.0 * 20% = 10.0
        self.assertIn(b'$10.0', response.data)
        print("Test Passed: Full flow verified successfully.")

if __name__ == '__main__':
    unittest.main()
