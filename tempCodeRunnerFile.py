@app.route('/emergency_list')
@login_required
def emergency_list():
    # CHANGED 80 -> 70 so all High Risk patients show up here
    cases = Prediction.query.filter(Prediction.probability > 70).order_by(Prediction.date.desc()).all()
    return render_template('emergency_list.html', cases=cases)