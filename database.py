from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

# 1. Staff/Doctor Login
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), default='Doctor')

# 2. Patient Master Record
class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    sex = db.Column(db.String(10), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    predictions = db.relationship('Prediction', backref='patient', cascade="all, delete-orphan", lazy=True)
    appointments = db.relationship('Appointment', backref='patient', cascade="all, delete-orphan", lazy=True)
    prescriptions = db.relationship('Prescription', backref='patient', cascade="all, delete-orphan", lazy=True)

# 3. AI Prediction History
class Prediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Medical Data
    cp = db.Column(db.Integer)
    trestbps = db.Column(db.Integer)
    chol = db.Column(db.Integer)
    thalach = db.Column(db.Integer)
    oldpeak = db.Column(db.Float)
    
    # AI Results
    risk_level = db.Column(db.String(50))
    probability = db.Column(db.Float)
    notes = db.Column(db.Text) 

# 4. Appointment System
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    doctor_name = db.Column(db.String(100), default="Dr. Admin")
    date_time = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), default='Scheduled') 

# 5. Advanced Prescription System
class Prescription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    doctor_name = db.Column(db.String(100), default="Dr. Admin")  
    instructions = db.Column(db.Text) 
    date_prescribed = db.Column(db.DateTime, default=datetime.utcnow)
    medicine_name = db.Column(db.String(100), nullable=False)
    dosage = db.Column(db.String(50))      
    frequency = db.Column(db.String(50))   
    duration = db.Column(db.String(50))    
    status = db.Column(db.String(20), default='Active')

# 6. Critical Care Unit (New Table)
class CriticalCareStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prediction_id = db.Column(db.Integer, db.ForeignKey('prediction.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    
    # Workflow Fields
    condition_type = db.Column(db.String(100), default="Assessment Pending")
    treatment_status = db.Column(db.String(50), default="Not Started")
    ongoing_process = db.Column(db.String(200), default="Awaiting Doctor Review")
    doctor_notes = db.Column(db.Text, default="")
    assigned_doctor = db.Column(db.String(50))
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    patient = db.relationship('Patient', backref='critical_status')
    prediction = db.relationship('Prediction', backref=db.backref('care_status', uselist=False))