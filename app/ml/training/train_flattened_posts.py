import json
import joblib
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.svm import SVC
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, f1_score
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).resolve().parent.parent

# Переконайтесь, що назва файлу збігається з тією, яку ви згенерували на попередньому кроці
DATA_PATH = BASE_DIR / "data" / "flattened_annotated_scraped_data.json" 
EMBEDDINGS_PATH = BASE_DIR / "data" / "embeddings_cache.npy"
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

def main():
    print(f"Loading annotated data from: {DATA_PATH}")
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    
    print(f"Loading cached embeddings from: {EMBEDDINGS_PATH}")
    if not EMBEDDINGS_PATH.exists():
        print("❌ Кеш ембедингів не знайдено! Перераховуємо...")
        X_full = []
    else:
        X_full = np.load(EMBEDDINGS_PATH)
    
    # КРИТИЧНА ПЕРЕВІРКА: чи співпадає кількість текстів і кількість збережених векторів
    if len(X_full) != len(df):
        print(f"⚠️ Увага: Розбіжність розмірностей! Векторів: {len(X_full)}, Рядків у DF: {len(df)}")
        print("Це нормально, оскільки ми змінили логіку розбиття текстів (flattening).")
        print("Перераховуємо ембединги для ідеального збігу...")
        
        encoder = SentenceTransformer(MODEL_NAME)
        X_full = encoder.encode(df['text'].tolist(), show_progress_bar=True, batch_size=32)
        np.save(EMBEDDINGS_PATH, X_full)
        print("✅ Нові ембединги збережено у кеш.")
        
    y_full = df['event_type'].values
    
    # Відфільтровуємо порожні мітки (на випадок, якщо щось пропустили)
    valid_indices = [i for i, label in enumerate(y_full) if str(label).strip() != ""]
    
    X = X_full[valid_indices]
    y = y_full[valid_indices]
    
    print(f"\nЗнайдено {len(y)} розмічених прикладів (з {len(y_full)} загальних).")
    print("\nРозподіл класів:")
    print(pd.Series(y).value_counts())

    if len(np.unique(y)) < 2:
        print("❌ Помилка: Для тренування SVM потрібно щонайменше 2 різних класи.")
        return

    print("\nКодування міток (Label Encoding)...")
    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(y)

    # Стратифікований поділ на тренувальну та тестову вибірки
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded,
        test_size=0.2,
        random_state=42,
        stratify=y_encoded
    )

    print(f"Train size: {len(X_train)}; Test size: {len(X_test)}")

    print("\nТренування SVM (RBF kernel)...")
    model = SVC(**SVM_PARAMS)
    model.fit(X_train, y_train)

    print("Оцінка моделі...")
    y_pred = model.predict(X_test)

    f1 = f1_score(y_test, y_pred, average='macro')
    print(f"\nF1-macro на тестовій вибірці: {f1:.4f}")
    print("Classification Report:")
    print(classification_report(y_test, y_pred, target_names=label_encoder.classes_, zero_division=0))

    # Збереження моделі
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    model_data = {
        "model": model,
        "label_encoder": label_encoder,
        "encoder_name": MODEL_NAME,
        "svm_params": SVM_PARAMS,
        "f1_macro": float(f1)
    }

    joblib.dump(model_data, MODEL_PATH)
    print(f"\n✅ Модель успішно збережено: {MODEL_PATH}")

if __name__ == "__main__":
    main()