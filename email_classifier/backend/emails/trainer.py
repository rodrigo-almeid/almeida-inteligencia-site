# ML desabilitado temporariamente — scikit-learn/nltk removidos para reduzir uso de memória na VM.
# Para reativar: descomentar requirements.txt, Dockerfile e este arquivo.

# import joblib
# from sklearn.pipeline import Pipeline
# from sklearn.feature_extraction.text import TfidfVectorizer
# from sklearn.linear_model import LogisticRegression
# from sklearn.model_selection import train_test_split
# from sklearn.metrics import classification_report

_MSG = "ML desabilitado. Reative scikit-learn no requirements.txt para usar esta função."


def treinar(registros: list[dict], user_id: int) -> dict:
    return {"status": "desabilitado", "msg": _MSG}


def classificar_ml(assunto: str, corpo: str, user_id: int) -> dict:
    return {"subcategoria": None, "sla": None, "confianca_subcategoria": None, "confianca_sla": None}


def modelo_existe(user_id: int) -> dict:
    return {"subcategoria": False, "sla": False}
