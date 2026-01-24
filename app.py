import random
import csv
from io import StringIO
from flask import make_response
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
import pickle
from datetime import datetime, timedelta
from sqlalchemy import func
from database import db, User, Patient, Prediction, Appointment, Prescription, CriticalCareStatus

app = Flask(__name__)
app.config['SECRET_KEY'] = 'medcore-hackathon-winner'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'

db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        pw = bcrypt.generate_password_hash('admin').decode('utf-8')
        db.session.add(User(username='admin', password=pw, role='Admin'))
        db.session.commit()

# --- HELPER: GET ACTIVE CRITICAL COUNT ---
def get_active_critical_count():
    """Calculates unique patients with Risk > 70% who are NOT stable."""
    candidates = Prediction.query.filter(Prediction.probability > 70).all()
    unique_active = set()
    for p in candidates:
        # If marked stable, ignore
        if p.care_status and p.care_status.treatment_status == "Discharged / Stable":
            continue
        unique_active.add(p.patient_id)
    return len(unique_active)

# --- CONTEXT PROCESSOR (SIDEBAR BADGE) ---
@app.context_processor
def inject_counts():
    if current_user.is_authenticated:
        return dict(
            appt_count=Appointment.query.filter_by(status='Scheduled').count(),
            emergency_count=get_active_critical_count() # Matches Dashboard Logic
        )
    return dict(appt_count=0, emergency_count=0)

def validate_medical_inputs(data):
    errors = []
    try:
        age = int(data.get('age', 0))
        if age < 1 or age > 120: errors.append(f"Age {age} is invalid.")
    except: errors.append("Age must be a number.")
    
    try:
        bp = int(data.get('trestbps', 0))
        if bp < 50 or bp > 250: errors.append(f"BP {bp} is impossible.")
    except: errors.append("BP must be a number.")

    try:
        chol = int(data.get('chol', 0))
        if chol < 80 or chol > 600: errors.append(f"Cholesterol {chol} is invalid.")
    except: errors.append("Cholesterol must be a number.")

    try:
        hr = int(data.get('thalach', 0))
        if hr < 60 or hr > 220: errors.append(f"Heart Rate {hr} is invalid.")
    except: errors.append("Heart Rate must be a number.")
    
    return errors

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and bcrypt.check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid Credentials', 'danger')
    
    # --- RESTORED QUOTE ENGINE ---
    quotes = [
        {"text": "Medicine cures diseases, but only doctors can cure patients.", "author": "C.G. Jung"},
        {"text": "Wherever the art of Medicine is loved, there is also a love of Humanity.", "author": "Hippocrates"},
        {"text": "The good physician treats the disease; the great physician treats the patient who has the disease.", "author": "William Osler"},
        {"text": "Observation, Reason, Human Understanding, Courage; these make the physician.", "author": "Martin H. Fischer"},
        {"text": "To cure sometimes, to relieve often, to comfort always.", "author": "Edward Livingston Trudeau"},
        {"text": "Diagnosis is not the end, but the beginning of practice.", "author": "Martin H. Fischer"}
    ]
    daily_quote = random.choice(quotes)
    
    return render_template('login.html', quote=daily_quote)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    stats = {
        'patients': Patient.query.count(),
        # FIX: Now uses the EXACT same logic as the sidebar badge
        'high_risk': get_active_critical_count(), 
        'appointments': Appointment.query.filter_by(status='Scheduled').count(),
        'emergencies': get_active_critical_count()
    }
    
    recent_patients = Patient.query.order_by(Patient.created_at.desc()).limit(5).all()
    today_appointments = Appointment.query.filter(Appointment.date_time >= datetime.utcnow().date()).order_by(Appointment.date_time.asc()).limit(20).all() 
    return render_template('dashboard.html', stats=stats, patients=recent_patients, appointments=today_appointments)

@app.route('/patients')
@login_required
def patient_list():
    search = request.args.get('search')
    patients = Patient.query.filter(Patient.name.contains(search)).all() if search else Patient.query.all()
    return render_template('patient_list.html', patients=patients)

@app.route('/patients/new', methods=['GET', 'POST'])
@login_required
def new_patient():
    if request.method == 'POST':
        p = Patient(name=request.form.get('name'), age=int(request.form.get('age')), sex=request.form.get('sex'), phone=request.form.get('phone'), address=request.form.get('address'))
        db.session.add(p)
        db.session.commit()
        return redirect(url_for('patient_profile', id=p.id))
    return render_template('patient_form.html')

@app.route('/patient/<int:id>')
@login_required
def patient_profile(id):
    patient = Patient.query.get_or_404(id)
    dates = [p.date.strftime('%Y-%m-%d') for p in patient.predictions]
    risks = [p.probability for p in patient.predictions]
    return render_template('patient_profile.html', p=patient, trend_dates=dates, trend_risks=risks)

@app.route('/patient/<int:id>/delete', methods=['POST'])
@login_required
def delete_patient(id):
    p = Patient.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for('patient_list'))

@app.route('/report/<int:pred_id>/delete', methods=['POST'])
@login_required
def delete_report(pred_id):
    pred = Prediction.query.get_or_404(pred_id)
    patient_id = pred.patient_id
    db.session.delete(pred)
    db.session.commit()
    flash('Report deleted successfully.', 'success')
    return redirect(url_for('patient_profile', id=patient_id))

# --- AI PREDICTION (WITH SAFETY OVERRIDE) ---
@app.route('/patient/<int:id>/predict', methods=['GET', 'POST'])
@login_required
def predict_checkup(id):
    patient = Patient.query.get_or_404(id)
    if request.method == 'POST':
        validation_errors = validate_medical_inputs(request.form)
        if validation_errors:
            for err in validation_errors: flash(err, 'danger')
            return render_template('predict_form.html', p=patient, form_data=request.form)

        try:
            features = [int(request.form['age']), 1 if request.form['sex']=='Male' else 0, int(request.form['cp']), 
                        int(request.form['trestbps']), int(request.form['chol']), int(request.form['fbs']), 
                        int(request.form['restecg']), int(request.form['thalach']), int(request.form['exang']), 
                        float(request.form['oldpeak']), int(request.form['slope']), int(request.form['ca']), int(request.form['thal'])]
            
            model = pickle.load(open('Artifacts/Model.pkl', 'rb'))
            scaler = pickle.load(open('Artifacts/preprocessor.pkl', 'rb'))
            final_data = scaler.transform([features])
            prob = model.predict_proba(final_data)[0][1] * 100
        except: prob = 0

        # --- CLINICAL FAILSAFE ---
        if features[3] >= 160 or features[4] >= 280 or features[9] >= 2.5:
            prob = max(prob, 76.0) # Force High Risk
        
        if features[3] > 180: 
            prob = max(prob, 91.0) # Force Critical

        final_prob = min(max(prob, 0), 99.9)
        
        if final_prob >= 90: risk = "CRITICAL WARNING"
        elif final_prob >= 75: risk = "High Risk"
        elif final_prob >= 60: risk = "Moderate Risk"
        else: risk = "Low Risk"

        pred = Prediction(patient_id=patient.id, cp=features[2], trestbps=features[3], chol=features[4], thalach=features[7], oldpeak=features[9], risk_level=risk, probability=round(final_prob, 1))
        db.session.add(pred)
        db.session.commit()
        return redirect(url_for('view_report', pred_id=pred.id))
    return render_template('predict_form.html', p=patient, form_data={})

@app.route('/report/<int:pred_id>')
@login_required
def view_report(pred_id):
    pred = Prediction.query.get_or_404(pred_id)
    p = Patient.query.get(pred.patient_id)
    notes = ["Vitals analyzed."]
    if pred.trestbps > 130: notes.append("Hypertension detected.")
    if pred.chol > 240: notes.append("High Cholesterol.")
    if pred.probability > 75: notes.append("Patient requires immediate attention.")
    return render_template('report.html', report=pred, p=p, advice=notes)

# --- EMERGENCY LIST (DEDUPLICATED) ---
@app.route('/emergency_list')
@login_required
def emergency_list():
    all_cases = Prediction.query.filter(Prediction.probability > 70).order_by(Prediction.date.desc()).all()
    active_cases = []
    seen_patient_ids = set()
    for case in all_cases:
        if case.patient_id in seen_patient_ids: continue
        if case.care_status and case.care_status.treatment_status == "Discharged / Stable": continue
        seen_patient_ids.add(case.patient_id)
        active_cases.append(case)
    return render_template('emergency_list.html', cases=active_cases)

# --- CRITICAL CARE (DEDUPLICATED) ---
@app.route('/critical_care')
@login_required
def critical_care():
    all_cases = Prediction.query.filter(Prediction.probability > 70).order_by(Prediction.date.desc()).all()
    active_cases = []
    seen_patient_ids = set()
    for case in all_cases:
        if case.patient_id in seen_patient_ids: continue
        if case.care_status and case.care_status.treatment_status == "Discharged / Stable": continue
        seen_patient_ids.add(case.patient_id)
        active_cases.append(case)
    return render_template('critical_care.html', cases=active_cases)

@app.route('/critical_care/update/<int:pred_id>', methods=['POST'])
@login_required
def update_critical_status(pred_id):
    prediction = Prediction.query.get_or_404(pred_id)
    patient_id = prediction.patient_id
    
    status = CriticalCareStatus.query.filter_by(prediction_id=pred_id).first()
    if not status:
        status = CriticalCareStatus(prediction_id=pred_id, patient_id=patient_id)
        db.session.add(status)
    
    status.condition_type = request.form.get('condition_type')
    status.treatment_status = request.form.get('treatment_status')
    status.ongoing_process = request.form.get('ongoing_process')
    status.doctor_notes = request.form.get('doctor_notes')
    status.assigned_doctor = current_user.username
    status.last_updated = datetime.utcnow()
    
    action = request.form.get('action')
    if action == 'mark_stable':
        status.treatment_status = "Discharged / Stable"
        # BATCH CLEANUP: Remove ALL high-risk alerts for this patient
        all_recs = Prediction.query.filter_by(patient_id=patient_id).all()
        for r in all_recs:
            if r.probability > 60:
                r.probability = 10.0
                r.risk_level = "Stabilized"
        flash(f"Patient {prediction.patient.name} marked as Stable. All alerts cleared.", "success")
        
    elif action == 'escalate':
        status.treatment_status = "ICU Monitoring"
        status.condition_type = "Critical Deterioration"
        prediction.probability = 95.0
        prediction.risk_level = "CRITICAL WARNING"
        flash("Escalated to ICU!", "danger")
    
    db.session.commit()
    return redirect(url_for('critical_care'))

@app.route('/shift_handover')
@login_required
def shift_handover():
    active_cases = CriticalCareStatus.query.filter(CriticalCareStatus.treatment_status != 'Discharged / Stable').all()
    return render_template('shift_handover.html', cases=active_cases, time=datetime.now())

# --- ANALYTICS (FIXED) ---
@app.route('/analytics')
@login_required
def analytics():
    active_critical_count = get_active_critical_count()

    stats = {
        'total_p': Patient.query.count(),
        'crit_count': active_critical_count,
        'active_appts': Appointment.query.filter_by(status='Scheduled').count(),
        'pending': active_critical_count 
    }

    high_risk_count = Prediction.query.filter(Prediction.probability > 75).count()
    mod_risk_count = Prediction.query.filter((Prediction.probability >= 60) & (Prediction.probability <= 75)).count()
    low_risk_count = Prediction.query.filter(Prediction.probability < 60).count()
    
    high_bp = Prediction.query.filter(Prediction.trestbps > 140).count()
    high_chol = Prediction.query.filter(Prediction.chol > 240).count()
    angina = Prediction.query.filter(Prediction.cp == 0).count()

    appt_completed = Appointment.query.filter_by(status='Completed').count()
    appt_cancelled = Appointment.query.filter_by(status='Cancelled').count()
    appt_scheduled = Appointment.query.filter_by(status='Scheduled').count()

    trend_labels = []
    trend_data = []
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=6)
    for i in range(7):
        current_day = start_date + timedelta(days=i)
        count = Prediction.query.filter(func.date(Prediction.date) == current_day).count()
        trend_labels.append(current_day.strftime('%b %d'))
        trend_data.append(count)

    return render_template('analytics.html', 
        stats=stats,
        risk={'high': high_risk_count, 'mod': mod_risk_count, 'low': low_risk_count},
        factors={'bp': high_bp, 'chol': high_chol, 'angina': angina},
        appts={'done': appt_completed, 'cancel': appt_cancelled, 'open': appt_scheduled},
        trend={'labels': trend_labels, 'data': trend_data}
    )

@app.route('/appointments')
@login_required
def appointments():
    appts = Appointment.query.order_by(Appointment.date_time.desc()).all()
    patients = Patient.query.all()
    return render_template('appointments.html', appointments=appts, patients=patients)

@app.route('/appointment/create', methods=['POST'])
@login_required
def create_appointment():
    dt = datetime.strptime(request.form.get('date'), '%Y-%m-%dT%H:%M')
    db.session.add(Appointment(patient_id=request.form.get('patient_id'), date_time=dt, reason=request.form.get('reason')))
    db.session.commit()
    return redirect(url_for('appointments'))

@app.route('/appointment/<int:id>/status/<string:new_status>')
@login_required
def update_appointment_status(id, new_status):
    appt = Appointment.query.get_or_404(id)
    appt.status = new_status
    db.session.commit()
    return redirect(url_for('appointments'))

@app.route('/appointment/<int:id>/delete', methods=['POST'])
@login_required
def delete_appointment(id):
    appt = Appointment.query.get_or_404(id)
    db.session.delete(appt)
    db.session.commit()
    return redirect(url_for('appointments'))

@app.route('/prescriptions')
@login_required
def prescriptions():
    meds = Prescription.query.order_by(Prescription.status.asc(), Prescription.date_prescribed.desc()).all()
    patients = Patient.query.all()
    return render_template('prescriptions.html', prescriptions=meds, patients=patients)

@app.route('/prescription/create', methods=['POST'])
@login_required
def create_prescription():
    db.session.add(Prescription(patient_id=request.form.get('patient_id'), medicine_name=request.form.get('med_name'), dosage=request.form.get('dosage'), frequency=request.form.get('frequency'), duration=request.form.get('duration'), instructions=request.form.get('instructions')))
    db.session.commit()
    return redirect(url_for('prescriptions'))

@app.route('/prescription/<int:id>/status/<string:new_status>')
@login_required
def update_prescription_status(id, new_status):
    rx = Prescription.query.get_or_404(id)
    rx.status = new_status
    db.session.commit()
    return redirect(url_for('prescriptions'))

@app.route('/prescription/<int:id>/delete', methods=['POST'])
@login_required
def delete_prescription(id):
    rx = Prescription.query.get_or_404(id)
    db.session.delete(rx)
    db.session.commit()
    return redirect(url_for('prescriptions'))

@app.route('/settings')
@login_required
def settings(): return render_template('settings.html')

@app.route('/demo_seed')
@login_required
def demo_mode():
    if not Patient.query.filter_by(name="James Bond").first():
        p = Patient(name="James Bond", age=45, sex="Male", phone="555-007")
        db.session.add(p)
        db.session.commit()
        db.session.add(Prediction(patient_id=p.id, cp=0, trestbps=160, chol=280, thalach=110, oldpeak=2.5, risk_level="High Risk", probability=85.5))
        db.session.commit()
    flash("Demo Data Loaded!", "success")
    return redirect(url_for('dashboard'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        if request.form.get('password'):
            current_user.password = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
            db.session.commit()
            flash('Password Updated', 'success')
    return render_template('profile.html', user=current_user)

@app.route('/export_data')
@login_required
def export_data():
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Name', 'Age', 'Risk'])
    for p in Patient.query.all():
        cw.writerow([p.id, p.name, p.age, "High" if p.predictions and p.predictions[-1].probability > 70 else "Low"])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=patients.csv"
    output.headers["Content-type"] = "text/csv"
    return output

if __name__ == '__main__':
    app.run(debug=True, port=5000)