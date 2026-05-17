import os
import json
import joblib
import re
from pathlib import Path
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, f1_score


BASE_DIR = Path(__file__).resolve().parent.parent

DATA_PATH = BASE_DIR / "data" / "flattened_annotated_scraped_data.json"
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "is_actionable_classifier.pkl"

MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"
SVM_PARAMS = {
    "kernel": "rbf",
    "C": 5.0,
    "gamma": "scale",
    "probability": True,
    "random_state": 42
}

CONFIDENCE_THRESHOLD = 0.40

NOISE_PATTERNS = [
    r"читайте\s+тут", r"дізнайтесь\s+(тут|за посиланням|більше)",
    r"детальніше\s*(→|тут|за посиланням|:)", r"більше\s+інформації",
    r"повний\s+список", r"(?<!\S)https?://\S+\s*$",
    r"за\s+(цей|минулий|перший|другий|третій|четвертий)\s+(рік|квартал|місяць)",
    r"з\s+початку\s+року", r"(?:км|кілометр)\s+доріг", r"тендер",
    r"план\s+розвитку", r"до\s+20\d\d\s+року", r"топ-\d+",
    r"рейтинг", r"опитування", r"голосування",
    r"відбій\s+повітряної\s+тривоги", r"відбій повітряної", r"тривога\s+відбій",
    r"акція", r"знижка", r"донат", r"збір", r"волонтери",
    r"статистика", r"підсумки", r"за результатами", r"за підсумками",
    r"зменшил(?:ася|ося|ись)", r"збільшил(?:ася|ося|ись)",
    r"порівняно з", r"відремонтовано", r"замінено", r"виконано",
]

NOISE_RE = re.compile("|".join(NOISE_PATTERNS), flags=re.IGNORECASE | re.UNICODE)


def rule_based_filter(text: str) -> bool:
    return not bool(NOISE_RE.search(text))


def load_data() -> tuple[list[str], list[bool]]:
    print(f"Loading data from: {DATA_PATH}")
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    df = pd.DataFrame(data)
    df = df[df['event_type'] != 'шум'].reset_index(drop=True)
    
    texts = df['text'].tolist()
    labels = df['is_actionable'] = df['event_type'].apply(lambda x: False if str(x).strip() == "шум" else True).tolist()
    
    print(f"Data for binary classification: {len(texts)} records")
    print(f"is_actionable=True: {sum(labels)}")
    print(f"is_actionable=False: {len(labels) - sum(labels)}")
    
    return texts, labels

def main():
    texts, labels = load_data()

    print(f"\nLoading embedding model: {MODEL_NAME}")
    encoder = SentenceTransformer(MODEL_NAME)

    print("Computing embeddings...")
    X = encoder.encode(texts, show_progress_bar=True, batch_size=32)
    y = np.array([1 if label else 0 for label in labels])

    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.2,
        random_state=12,
        stratify=y
    )

    print(f"Train size: {len(X_train)}; Test size: {len(X_test)}")

    print("\nTraining SVM (RBF)...")
    model = SVC(**SVM_PARAMS)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    f1 = f1_score(y_test, y_pred, average='binary')

    print(f"\nF1-score (positive class): {f1:.4f}")
    print(classification_report(y_test, y_pred, target_names=["noise (False)", "event (True)"], zero_division=0))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    model_data = {
        "model": model,
        "encoder_name": MODEL_NAME,
        "svm_params": SVM_PARAMS,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "f1_score": float(f1),
        "noise_patterns": NOISE_PATTERNS 
    }

    joblib.dump(model_data, MODEL_PATH)
    print(f"\nBinary model successfully saved: {MODEL_PATH}")

if __name__ == "__main__":
    main()