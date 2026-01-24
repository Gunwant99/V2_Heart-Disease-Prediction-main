# Create a new file: train_model.py
import pandas as pd
import numpy as np
import pickle
import os
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score

# 1. Load Data
# Ensure 'Data/heart.csv' exists. If not, download from Kaggle or your repo.
if not os.path.exists('Notebook_Experiments/Data/heart.csv'):
    print("❌ Error: Data/heart.csv not found.")
    exit()

df = pd.read_csv('Notebook_Experiments/Data/heart.csv')

# 2. Fix Categorical / Clean Data
# Check if dataset uses text or numbers. We assume standard UCI numbers.
# If dataset has duplicates, remove them
df = df.drop_duplicates()

# 3. Define EXACT Feature Order (Crucial for "High Risk" fix)
feature_order = ['age', 'sex', 'cp', 'trestbps', 'chol', 'fbs', 'restecg', 'thalach', 'exang', 'oldpeak', 'slope', 'ca', 'thal']
X = df[feature_order]
y = df['target']

# 4. Split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 5. SCALING (The missing link in your previous high-risk issue)
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# 6. Train Random Forest
model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
model.fit(X_train_scaled, y_train)

# 7. Evaluate
y_pred = model.predict(X_test_scaled)
acc = accuracy_score(y_test, y_pred)
print(f"✅ Model Trained. Accuracy: {acc*100:.2f}%")

# 8. Save Artifacts
os.makedirs('Artifacts', exist_ok=True)
pickle.dump(model, open('Artifacts/Model.pkl', 'wb'))
pickle.dump(scaler, open('Artifacts/preprocessor.pkl', 'wb'))
print("✅ Brain (Model) and Translator (Scaler) saved to Artifacts/")