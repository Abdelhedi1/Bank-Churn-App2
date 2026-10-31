import numpy as np

from app import ml


def test_features_and_matrix_alignment(df):
    X = ml.build_matrix(df)
    assert {"balance_salary_ratio", "gender_encoded", "country_France"} <= set(X.columns)
    assert not X.isnull().any().any()
    X2 = ml.build_matrix(df.head(1), list(X.columns))
    assert list(X2.columns) == list(X.columns)


def test_compute_ks_perfect_and_random():
    assert ml.compute_ks([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert ml.compute_ks([0, 0], [0.1, 0.2]) == 0.0


def test_train_and_predict(df):
    prep = ml.prepare_training_data(df)
    model, _ = ml.train_logistic_regression(prep["X_train"], prep["y_train"])
    m = ml.evaluate_model(model, prep["X_test"], prep["y_test"])
    assert 0.5 < m["auc"] <= 1 and np.array(m["confusion_matrix"]).sum() == len(prep["y_test"])


def test_reduced_columns_work(df):
    small = df[["credit_score", "country", "products_number", "credit_card",
                "active_member", "estimated_salary", "churn"]]
    assert ml.missing_columns(small) == []
    X = ml.build_matrix(small)
    assert "balance_salary_ratio" not in X.columns and "activity_score" in X.columns
    assert ml.prepare_training_data(small)["input_columns"] == [
        "credit_score", "country", "products_number", "credit_card", "active_member", "estimated_salary"]


def test_explanations_and_importance(df):
    prep = ml.prepare_training_data(df)
    model, _ = ml.train_logistic_regression(prep["X_train"], prep["y_train"])
    raw = df.drop(columns=["customer_id", "churn"]).head(3)
    out = ml.explain_frame(model, prep["scaler"], prep["feature_names"], raw, top_n=3)
    assert len(out) == 3 and all(len(f) == 3 for f in out)
    assert {"label", "value", "impact", "direction"} <= set(out[0][0])
    imp = ml.feature_importance(model, prep["feature_names"])
    assert abs(sum(i["share"] for i in imp) - 1) < 0.01
