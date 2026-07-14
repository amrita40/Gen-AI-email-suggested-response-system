

import json
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "support_emails_dataset.jsonl")

def load_dataset(path=DATA_PATH):
    records = []
    with open(path) as f:
        for line in f:
            records.append(json.loads(line))
    return records


class IntentDetector:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=2, stop_words="english")
        self.clf = LinearSVC()
        self.trained = False

    def fit(self, records):
        X_text = [r["customer_email"] for r in records]
        y = [r["category"] for r in records]
        X_train, X_test, y_train, y_test = train_test_split(
            X_text, y, test_size=0.2, random_state=42, stratify=y
        )
        Xtr = self.vectorizer.fit_transform(X_train)
        Xte = self.vectorizer.transform(X_test)
        self.clf.fit(Xtr, y_train)
        preds = self.clf.predict(Xte)
        acc = accuracy_score(y_test, preds)
        report = classification_report(y_test, preds, zero_division=0)
        self.trained = True
        return {"accuracy": acc, "report": report, "n_train": len(X_train), "n_test": len(X_test)}

    def predict(self, email_text):
        if not self.trained:
            raise RuntimeError("Call .fit() before predicting.")
        vec = self.vectorizer.transform([email_text])
        return self.clf.predict(vec)[0]

    def predict_confidence(self, email_text):
        """Rough confidence proxy: margin from the decision function, squashed to 0-1."""
        vec = self.vectorizer.transform([email_text])
        scores = self.clf.decision_function(vec)[0]
        top = scores.max()
        second = sorted(scores)[-2] if len(scores) > 1 else 0
        margin = top - second
        conf = 1 / (1 + pow(2.718281828, -margin))  # logistic squash
        return round(float(conf), 3)


if __name__ == "__main__":
    records = load_dataset()
    detector = IntentDetector()
    metrics = detector.fit(records)
    print(f"Trained on {metrics['n_train']} / tested on {metrics['n_test']} emails")
    print(f"Held-out accuracy: {metrics['accuracy']:.3f}\n")
    print(metrics["report"])

    sample = records[0]
    pred = detector.predict(sample["customer_email"])
    conf = detector.predict_confidence(sample["customer_email"])
    print(f"Sample check -> true: {sample['category']} | predicted: {pred} | confidence: {conf}")
