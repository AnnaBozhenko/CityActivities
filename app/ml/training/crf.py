import os
import json
import joblib
import re
from pathlib import Path
import numpy as np
import pandas as pd
import sklearn_crfsuite
from sklearn.model_selection import train_test_split
from sklearn_crfsuite import metrics

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_PATH = BASE_DIR / "data" / "data_with_tags.json"
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "address_ner_crf.pkl"

STREET_ABBRS = {
    "вул", "вул.", "вулиця", "просп", "просп.", "проспект",
    "пров", "пров.", "провулок", "бул", "бул.", "бульвар",
    "пл", "пл.", "площа", "пр-т", "шосе", "траса"
}

ADDR_TRIGGERS = {
    "парк", "парку", "міст", "мосту", "метро", "район", "районі",
    "зупинка", "зупинці", "вокзал", "вокзалу"
}

ADDR_CONTEXT = STREET_ABBRS | ADDR_TRIGGERS

def word2features(seq: list[tuple[str, str]], i: int) -> dict:
    token = seq[i][0]
    w = token.lower().rstrip(".,")

    features = {
        "bias": 1.0,
        "w.lower": w,
        "w.suffix2": w[-2:] if len(w) >= 2 else w,
        "w.suffix3": w[-3:] if len(w) >= 3 else w,
        "w.prefix3": w[:3] if len(w) >= 3 else w,

        "w.isupper": token.isupper(),
        "w.istitle": token.istitle(),
        "w.isdigit": token.isdigit(),
        "w.isalpha": token.isalpha(),
        "w.has_dash": "–" in token or "-" in token,
        "w.is_street_abbr": w in STREET_ABBRS,
        "w.is_addr_trigger": w in ADDR_TRIGGERS,
        "w.is_house_num": bool(re.match(r"^\d+[а-яa-z]?(/\d+)?$", token)),
        "w.is_house_range": bool(re.match(r"^\d+[–\-]\d+", token)),
        "w.is_punct": not token[0].isalnum() if token else False,
        "w.ukr_street_end": any(w.endswith(suf) for suf in ["ська", "ький", "ька", "ьке", "ього", "ого", "а", "я"]),
    }

    if i > 0:
        pt, _ = seq[i - 1]
        pw = pt.lower().rstrip(".,")
        features.update({
            "-1:w.lower": pw,
            "-1:w.istitle": pt.istitle(),
            "-1:w.is_abbr": pw in STREET_ABBRS,
            "-1:w.is_trigger": pw in ADDR_TRIGGERS,
            "-1:w.is_addr_ctx": pw in ADDR_CONTEXT,
        })
    else:
        features["BOS"] = True

    if i < len(seq) - 1:
        nt, _ = seq[i + 1]
        nw = nt.lower().rstrip(".,")
        features.update({
            "+1:w.lower": nw,
            "+1:w.istitle": nt.istitle(),
            "+1:w.is_house_num": bool(re.match(r"^\d+[а-яa-z]?(/\d+)?$", nt)),
            "+1:w.is_addr_ctx": nw in ADDR_CONTEXT,
        })
    else:
        features["EOS"] = True

    if i > 0:
        features["-1:w+ w"] = pw + "+" + w
    if i < len(seq) - 1:
        features["+1:w+ w"] = w + "+" + nw

    return features


def seq2features(seq):
    return [word2features(seq, i) for i in range(len(seq))]

def seq2labels(seq):
    return [tag for _, tag in seq]


def load_data():
    print(f'Loading data: {DATA_PATH}')
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    df = pd.DataFrame(data)
    sequences = df[df["address"].notnull()]["bio_tags"].tolist()
    print(f'Found sequences: {len(sequences)}')
    return sequences


def main():
    sequences = load_data()

    X = [seq2features(seq) for seq in sequences]
    y = [seq2labels(seq) for seq in sequences]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42)

    print(f"Train sequences: {len(X_train)}; Test sequences: {len(X_test)}")

    print("\nTraining CRF model...")
    crf = sklearn_crfsuite.CRF(
        algorithm='lbfgs',
        c1=0.1,
        c2=0.05,
        max_iterations=200,
        all_possible_transitions=True,
        verbose=False
    )

    crf.fit(X_train, y_train)
    y_pred = crf.predict(X_test)

    print("Classification Report (Token Level):")
    print(metrics.flat_classification_report(
        y_test, y_pred, 
        labels=["B-ADDR", "I-ADDR"], 
        digits=4,
        zero_division=0
    ))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_data = {
        "model": crf,
        "street_abbrs": STREET_ABBRS,
        "addr_triggers": ADDR_TRIGGERS,
    }

    joblib.dump(model_data, MODEL_PATH)
    print(f"NER model successfully saved: {MODEL_PATH}")

if __name__ == "__main__":
    main()