import os
import json
import requests
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime, timezone

app = Flask(__name__)

# Database Config - uses env var or defaults to a sqlite db for dev fallback
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///whatsapp_sales_v2.db')
# If using postgresql:// instead of postgresql+psycopg2://, SQLAlchemy might complain, but SQLAlchemy 1.4+ handles it or requires postgresql://
if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Models ---
class Business(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    whatsapp_number_id = db.Column(db.String(50), nullable=False, unique=True)
    access_token = db.Column(db.String(255), nullable=False)
    verify_token = db.Column(db.String(100), nullable=False)
    
    salesmen = db.relationship('Salesman', backref='business', lazy=True, cascade="all, delete-orphan")
    state = db.relationship('State', backref='business', uselist=False, cascade="all, delete-orphan")

    def __init__(self, name: str, whatsapp_number_id: str, access_token: str, verify_token: str, **kwargs):
        super().__init__(**kwargs)
        self.name = name
        self.whatsapp_number_id = whatsapp_number_id
        self.access_token = access_token
        self.verify_token = verify_token
        
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "whatsapp_number_id": self.whatsapp_number_id,
            "verify_token": self.verify_token,
            "salesmen_count": len(self.salesmen)
        }

class Salesman(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    def __init__(self, business_id: int, name: str, phone_number: str, is_active: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.business_id = business_id
        self.name = name
        self.phone_number = phone_number
        self.is_active = is_active

    def to_dict(self):
        return {
            "id": self.id,
            "business_id": self.business_id,
            "name": self.name,
            "phone_number": self.phone_number,
            "is_active": self.is_active
        }

class State(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False, unique=True)
    last_assigned_salesman_id = db.Column(db.Integer, nullable=True)

    def __init__(self, business_id: int, last_assigned_salesman_id: int | None = None, **kwargs):
        super().__init__(**kwargs)
        self.business_id = business_id
        self.last_assigned_salesman_id = last_assigned_salesman_id

class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    salesman_id = db.Column(db.Integer, db.ForeignKey('salesman.id'), nullable=False)
    salesman_phone = db.Column(db.String(20), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    customer_name = db.Column(db.String(100))
    status = db.Column(db.String(20), default='Pending')
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    age = db.Column(db.Integer)
    gender = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __init__(self, business_id: int, salesman_id: int, salesman_phone: str, customer_phone: str, customer_name: str | None = None, status: str = 'Pending', **kwargs):
        super().__init__(**kwargs)
        self.business_id = business_id
        self.salesman_id = salesman_id
        self.salesman_phone = salesman_phone
        self.customer_phone = customer_phone
        self.customer_name = customer_name
        self.status = status

    def to_dict(self):
        return {
            "id": self.id,
            "business_id": self.business_id,
            "salesman_phone": self.salesman_phone,
            "customer_phone": self.customer_phone,
            "customer_name": self.customer_name,
            "status": self.status,
            "city": self.city,
            "state": self.state,
            "age": self.age,
            "gender": self.gender,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

# Helper function to send WhatsApp message
def send_whatsapp_message(business, to_number, text_body):
    url = f"https://graph.facebook.com/v21.0/{business.whatsapp_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {business.access_token}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {
            "body": text_body
        }
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"Message sent to {to_number}: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending message to {to_number}: {e}")
        if e.response is not None:
            print(f"Response: {e.response.text}")
        return False

# --- Webhook Endpoint ---
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # Meta Webhook Verification
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode and token:
            if mode == 'subscribe':
                # Find the business with this verify_token
                business = Business.query.filter_by(verify_token=token).first()
                if business:
                    print(f"WEBHOOK_VERIFIED for {business.name}")
                    return challenge, 200
                else:
                    print(f"Verification token mismatch for token {token}")
                    return "Verification token mismatch", 403
        return "Hello Webhook", 200

    elif request.method == 'POST':
        # Parse incoming messages
        body = request.get_json()
        
        if body and body.get('object'):
            try:
                # Safely extract the message info
                entry = body.get('entry', [{}])[0]
                changes = entry.get('changes', [{}])[0]
                value = changes.get('value', {})
                
                # Meta includes metadata about the recipient number
                metadata = value.get('metadata', {})
                phone_number_id = metadata.get('phone_number_id')
                
                messages = value.get('messages', [{}])
                contacts = value.get('contacts', [{}])
                
                if messages and isinstance(messages, list) and phone_number_id:
                    # Find the corresponding business
                    business = Business.query.filter_by(whatsapp_number_id=phone_number_id).first()
                    
                    if not business:
                        print(f"Received message for unknown business with Phone ID: {phone_number_id}")
                        return "EVENT_RECEIVED", 200
                        
                    message = messages[0]
                    sender_phone = message.get('from')
                    sender_name = contacts[0].get('profile', {}).get('name', 'Unknown') if contacts else 'Unknown'
                    
                    if message.get('type') == 'text':
                        text_body = message.get('text', {}).get('body')
                        
                        # Check if sender is a registered salesman for this business
                        salesman = Salesman.query.filter_by(phone_number=sender_phone, business_id=business.id).first()
                        
                        lines = text_body.strip().split('\n')
                        status_line = lines[0].strip().lower()
                        
                        if salesman and status_line in ['done', 'rejected', 'partial']:
                            # It's a Salesman update message
                            print(f"Salesman {salesman.name} reporting status: {status_line.title()}")
                            # Parse other fields
                            customer_phone = None
                            name = None
                            city = None
                            state_val = None
                            age = None
                            gender = None
                            
                            for line in lines[1:]:
                                line_lower = line.lower()
                                if line_lower.startswith('customer phone:'):
                                    customer_phone = line.split(':', 1)[1].strip()
                                elif line_lower.startswith('name:'):
                                    name = line.split(':', 1)[1].strip()
                                elif line_lower.startswith('city:'):
                                    city = line.split(':', 1)[1].strip()
                                elif line_lower.startswith('state:'):
                                    state_val = line.split(':', 1)[1].strip()
                                elif line_lower.startswith('age:'):
                                    try:
                                        age = int(line.split(':', 1)[1].strip())
                                    except ValueError:
                                        pass
                                elif line_lower.startswith('gender:'):
                                    gender = line.split(':', 1)[1].strip()
                                    
                            if customer_phone:
                                # Look up the lead
                                lead = Lead.query.filter_by(
                                    customer_phone=customer_phone,
                                    salesman_phone=sender_phone,
                                    business_id=business.id,
                                    status='Pending'
                                ).first()
                                
                                if lead:
                                    lead.status = status_line.title()
                                    if name: lead.customer_name = name
                                    if city: lead.city = city
                                    if state_val: lead.state = state_val
                                    if age is not None: lead.age = age
                                    if gender: lead.gender = gender
                                    db.session.commit()
                                    print(f"Lead updated successfully for {customer_phone}.")
                                    send_whatsapp_message(business, sender_phone, f"✅ *Lead Updated*\nStatus marked as {status_line.title()} for {customer_phone}.")
                                else:
                                    print(f"ALERT: Salesman {salesman.name} attempted to update unassigned/unknown lead {customer_phone}.")
                                    send_whatsapp_message(business, sender_phone, f"⚠️ *Error*\nNo pending lead found for {customer_phone} assigned to you.")
                            else:
                                print("Failed to parse customer phone from salesman update.")
                                warning_msg = "⚠️ *Missing Customer Phone*\nPlease include 'Customer Phone: [number]' in your update."
                                send_whatsapp_message(business, sender_phone, warning_msg)
                        
                        else:
                            # New Lead Received from a Customer
                            print(f"\n=====================================")
                            print(f"New Lead Received for Business: {business.name}!")
                            print(f"Sender Phone: {sender_phone}")
                            print(f"Sender Name: {sender_name}")
                            print(f"Message Text: {text_body}")
                            
                            # --- Scoped Round Robin Logic ---
                            active_salesmen = Salesman.query.filter_by(business_id=business.id, is_active=True).order_by(Salesman.id).all()
                            
                            if not active_salesmen:
                                print(f"No active salesmen available for {business.name} to receive the lead.")
                            else:
                                state = State.query.filter_by(business_id=business.id).first()
                                if not state:
                                    state = State(business_id=business.id, last_assigned_salesman_id=None)
                                    db.session.add(state)
                                    db.session.commit()
                                
                                last_id = state.last_assigned_salesman_id
                                next_salesman = None
                                
                                # Find the salesman who comes after the last_assigned_salesman_id
                                if last_id is not None:
                                    for salesman in active_salesmen:
                                        if salesman.id > last_id:
                                            next_salesman = salesman
                                            break
                                            
                                # If no one found (e.g. last_id was the highest, or last_id is None)
                                if next_salesman is None:
                                    next_salesman = active_salesmen[0]
                                
                                print(f"Assigning lead to Salesman: {next_salesman.name} ({next_salesman.phone_number})")
                                
                                # Update State
                                state.last_assigned_salesman_id = next_salesman.id
                                
                                # Create Lead record
                                new_lead = Lead(
                                    business_id=business.id,
                                    salesman_id=next_salesman.id,
                                    salesman_phone=next_salesman.phone_number,
                                    customer_phone=sender_phone,
                                    customer_name=sender_name,
                                    status='Pending'
                                )
                                db.session.add(new_lead)
                                db.session.commit()
                                
                                # Forward message to salesman
                                forward_text = f"🚨 *New Lead Alert for {business.name}* 🚨\n\n*Name*: {sender_name}\n*Phone*: {sender_phone}\n*Message*: {text_body}\n\nPlease contact them ASAP!"
                                send_whatsapp_message(business, next_salesman.phone_number, forward_text)
                                
                                print(f"=====================================\n")
            except Exception as e:
                print(f"Error parsing message: {e}")
                
            # Return 200 OK to Meta to acknowledge receipt of the event
            return "EVENT_RECEIVED", 200
        else:
            return "NOT FOUND", 404

# --- Frontend Routes ---
@app.route('/', methods=['GET'])
def index():
    return render_template('dashboard.html')

# --- API Endpoints for Dashboard ---

# Businesses
@app.route('/api/businesses', methods=['GET'])
def get_businesses():
    businesses = Business.query.order_by(Business.id).all()
    return jsonify([b.to_dict() for b in businesses])

@app.route('/api/businesses', methods=['POST'])
def add_business():
    data = request.get_json()
    if not data or not data.get('name') or not data.get('whatsapp_number_id') or not data.get('access_token') or not data.get('verify_token'):
        return jsonify({"error": "Missing required business fields"}), 400
        
    if Business.query.filter_by(whatsapp_number_id=data['whatsapp_number_id']).first():
        return jsonify({"error": "Business with this WhatsApp Number ID already exists"}), 400
        
    new_business = Business(
        name=data['name'],
        whatsapp_number_id=data['whatsapp_number_id'],
        access_token=data['access_token'],
        verify_token=data['verify_token']
    )
    db.session.add(new_business)
    db.session.commit()
    
    # Initialize State for the business
    state = State(business_id=new_business.id, last_assigned_salesman_id=None)
    db.session.add(state)
    db.session.commit()
    
    return jsonify(new_business.to_dict()), 201

@app.route('/api/businesses/<int:id>', methods=['DELETE'])
def delete_business(id):
    business = Business.query.get_or_404(id)
    db.session.delete(business)
    db.session.commit()
    return jsonify({"message": "Business deleted successfully"})

# Salesmen (scoped to business)
@app.route('/api/businesses/<int:business_id>/salesmen', methods=['GET'])
def get_salesmen(business_id):
    business = Business.query.get_or_404(business_id)
    return jsonify([s.to_dict() for s in business.salesmen])

@app.route('/api/businesses/<int:business_id>/salesmen', methods=['POST'])
def add_salesman(business_id):
    business = Business.query.get_or_404(business_id)
    
    # Check if we already have 10 salesmen for this business
    count = Salesman.query.filter_by(business_id=business_id).count()
    if count >= 10:
        return jsonify({"error": "Maximum of 10 salesmen allowed per business."}), 400
        
    data = request.get_json()
    if not data or not data.get('name') or not data.get('phone_number'):
        return jsonify({"error": "Missing name or phone_number"}), 400
        
    # Check if phone number already exists globally
    if Salesman.query.filter_by(phone_number=data['phone_number']).first():
        return jsonify({"error": "Phone number already registered to a salesman."}), 400
        
    new_salesman = Salesman(
        business_id=business_id,
        name=data['name'],
        phone_number=data['phone_number'],
        is_active=data.get('is_active', True)
    )
    db.session.add(new_salesman)
    db.session.commit()
    
    return jsonify(new_salesman.to_dict()), 201

@app.route('/api/salesmen/<int:id>', methods=['PUT'])
def update_salesman(id):
    salesman = Salesman.query.get_or_404(id)
    data = request.get_json()
    
    if 'name' in data:
        salesman.name = data['name']
    if 'phone_number' in data:
        salesman.phone_number = data['phone_number']
    if 'is_active' in data:
        salesman.is_active = data['is_active']
        
    db.session.commit()
    return jsonify(salesman.to_dict())

@app.route('/api/salesmen/<int:id>', methods=['DELETE'])
def delete_salesman(id):
    salesman = Salesman.query.get_or_404(id)
    db.session.delete(salesman)
    db.session.commit()
    return jsonify({"message": "Salesman deleted successfully"})

# --- Analytics APIs ---
@app.route('/api/analytics/status-count', methods=['GET'])
def get_status_count():
    business_id = request.args.get('business_id', type=int)
    query = db.session.query(Lead.status, func.count(Lead.id)).group_by(Lead.status)
    if business_id:
        query = query.filter(Lead.business_id == business_id)
    results = query.all()
    return jsonify({status: count for status, count in results})

@app.route('/api/analytics/salesman-performance', methods=['GET'])
def get_salesman_performance():
    business_id = request.args.get('business_id', type=int)
    
    # Total leads assigned
    total_query = db.session.query(Lead.salesman_phone, func.count(Lead.id)).group_by(Lead.salesman_phone)
    # Converted leads (Done)
    converted_query = db.session.query(Lead.salesman_phone, func.count(Lead.id)).filter(Lead.status == 'Done').group_by(Lead.salesman_phone)
    
    if business_id:
        total_query = total_query.filter(Lead.business_id == business_id)
        converted_query = converted_query.filter(Lead.business_id == business_id)
        
    totals = {phone: count for phone, count in total_query.all()}
    converted = {phone: count for phone, count in converted_query.all()}
    
    performance = []
    for phone, total in totals.items():
        salesman = Salesman.query.filter_by(phone_number=phone).first()
        name = salesman.name if salesman else "Unknown"
        performance.append({
            "salesman_name": name,
            "salesman_phone": phone,
            "total_assigned": total,
            "converted": converted.get(phone, 0)
        })
    return jsonify(performance)

@app.route('/api/analytics/demographics', methods=['GET'])
def get_demographics():
    business_id = request.args.get('business_id', type=int)
    
    base_query = db.session.query(Lead).filter(Lead.status == 'Done')
    if business_id:
        base_query = base_query.filter(Lead.business_id == business_id)
        
    leads = base_query.all()
    
    states = {}
    cities = {}
    genders = {}
    ages = {"0-18": 0, "19-30": 0, "31-45": 0, "46-60": 0, "60+": 0}
    
    for lead in leads:
        if lead.state:
            states[lead.state] = states.get(lead.state, 0) + 1
        if lead.city:
            cities[lead.city] = cities.get(lead.city, 0) + 1
        if lead.gender:
            genders[lead.gender] = genders.get(lead.gender, 0) + 1
        if lead.age:
            if lead.age <= 18: ages["0-18"] += 1
            elif lead.age <= 30: ages["19-30"] += 1
            elif lead.age <= 45: ages["31-45"] += 1
            elif lead.age <= 60: ages["46-60"] += 1
            else: ages["60+"] += 1
            
    return jsonify({
        "states": states,
        "cities": cities,
        "genders": genders,
        "ages": ages
    })

@app.route('/api/analytics/hourly-trends', methods=['GET'])
def get_hourly_trends():
    business_id = request.args.get('business_id', type=int)
    
    # Filtering only for resolved leads, e.g., Done, Rejected, Partial
    # Assuming updated_at represents resolution time
    base_query = db.session.query(Lead).filter(Lead.status.in_(['Done', 'Rejected', 'Partial']))
    if business_id:
        base_query = base_query.filter(Lead.business_id == business_id)
        
    leads = base_query.all()
    
    hourly_counts = {str(i).zfill(2): 0 for i in range(24)}
    
    for lead in leads:
        if lead.updated_at:
            hour = lead.updated_at.strftime("%H")
            hourly_counts[hour] += 1
            
    return jsonify(hourly_counts)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(port=5000, debug=True)
