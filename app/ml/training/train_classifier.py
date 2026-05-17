import os
import json
import joblib
from pathlib import Path
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.svm import SVC
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, f1_score


BASE_DIR = Path(__file__).resolve().parent.parent

DATA_PATH = BASE_DIR / "data" / "scraped_events.json"
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "event_type_classifier.pkl"

MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"
SVM_PARAMS = {
    "kernel": "rbf",
    "C": 5.0,
    "gamma": "scale",
    "probability": True,
    "random_state": 42
}

def load_data() -> pd.DataFrame:
    print(f"Loading data from: {DATA_PATH}")
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    df = pd.DataFrame(data)
    print(f"Data loaded: {df.shape[0]} records")
    print("Class distribution:")
    print(df['event_type'].value_counts())
    return df

def main():
    df = load_data()

    print(f"\nLoading embedding model: {MODEL_NAME}")
    encoder = SentenceTransformer(MODEL_NAME)
    embeddings_file = BASE_DIR / "data" / "embeddings_cache.npy"

    print("Computing embeddings...")
    X = encoder.encode(df['text'].tolist(), show_progress_bar=True, batch_size=32)
    np.save(embeddings_file, X)
    y = df['event_type'].values

    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(y)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded,
        test_size=0.2,
        random_state=42,
        stratify=y_encoded
    )

    print(f"Train size: {len(X_train)}; Test size: {len(X_test)}")

    print("\nTraining SVM (RBF)")
    model = SVC(**SVM_PARAMS)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    f1 = f1_score(y_test, y_pred, average='macro')
    print(f"\nF1-macro on test set: {f1:.4f}")
    print("Classification Report:")
    print(classification_report(y_test, y_pred, target_names=label_encoder.classes_, zero_division=0))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    model_data = {
        "model": model,
        "label_encoder": label_encoder,
        "encoder_name": MODEL_NAME,
        "svm_params": SVM_PARAMS,
        "f1_macro": float(f1)
    }

    joblib.dump(model_data, MODEL_PATH)
    print(f"\nModel successfully saved: {MODEL_PATH}")

if __name__ == "__main__":
    main()