import os
import re
import string
import joblib

from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

CONFIANCA_MINIMA = 0.4

_STOPWORDS = set("""
a ao as até com como da das de do dos e em entre é essa esse esta este eu
já lhe lhes lo los mas me meu minha mais muito na nas não nos o os ou para
pela pelas pelo pelos por que se sem ser seu sua suas também te teu tua
um uma uns umas vai você vocês
the and for are but not you all can her was one our out day get has him
his how its just know let man new now old see two way who boy did its let
put say she too use
""".split())


def _limpar(texto: str) -> str:
    texto = texto.lower()
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"http\S+", " ", texto)
    texto = texto.translate(str.maketrans("", "", string.punctuation + "«»""''"))
    tokens = [t for t in texto.split() if t not in _STOPWORDS and len(t) > 2]
    return " ".join(tokens)


def _caminho_modelo(user_id: int, alvo: str) -> str:
    return os.path.join(MODELS_DIR, f"email_{alvo}_{user_id}.pkl")


def treinar(registros: list[dict], user_id: int) -> dict:
    resultado = {}
    for alvo in ("subcategoria", "sla"):
        dados = [(r, r[alvo]) for r in registros if r.get(alvo) and r[alvo] != "Não classificado"]
        if len(dados) < 5:
            resultado[alvo] = {"status": "insuficiente", "amostras": len(dados)}
            continue

        textos = [_limpar(f"{r['assunto']} {r.get('corpo', '')}") for r, _ in dados]
        labels = [label for _, label in dados]
        classes_unicas = list(set(labels))

        stratify = labels if len(classes_unicas) > 1 and min(labels.count(c) for c in classes_unicas) > 1 else None
        X_train, X_test, y_train, y_test = train_test_split(
            textos, labels, test_size=0.2, random_state=42, stratify=stratify
        )

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=10000, sublinear_tf=True)),
            ("clf", LogisticRegression(max_iter=500, class_weight="balanced")),
        ])
        pipeline.fit(X_train, y_train)

        y_pred = pipeline.predict(X_test)
        report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
        joblib.dump(pipeline, _caminho_modelo(user_id, alvo))

        resultado[alvo] = {
            "status": "ok",
            "amostras_treino": len(X_train),
            "amostras_teste": len(X_test),
            "acuracia": round(report.get("accuracy", 0), 4),
            "classes": classes_unicas,
        }

    return resultado


def classificar_ml(assunto: str, corpo: str, user_id: int) -> dict:
    texto = _limpar(f"{assunto} {corpo or ''}")
    resultado = {"subcategoria": None, "sla": None, "confianca_subcategoria": None, "confianca_sla": None}

    for alvo in ("subcategoria", "sla"):
        caminho = _caminho_modelo(user_id, alvo)
        if not os.path.exists(caminho):
            continue
        pipeline = joblib.load(caminho)
        proba = pipeline.predict_proba([texto])[0]
        idx_max = proba.argmax()
        confianca = float(proba[idx_max])
        if confianca >= CONFIANCA_MINIMA:
            resultado[alvo] = pipeline.classes_[idx_max]
            resultado[f"confianca_{alvo}"] = round(confianca, 3)

    return resultado


def modelo_existe(user_id: int) -> dict:
    return {
        "subcategoria": os.path.exists(_caminho_modelo(user_id, "subcategoria")),
        "sla": os.path.exists(_caminho_modelo(user_id, "sla")),
    }
