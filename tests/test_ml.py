import numpy as np

from app import ml


def test_features_and_matrix_alignment(df):
    X = ml.build_matrix(df)
    assert {"balance_salary_ratio", "gender_encoded", "country_France"} <= set(X.columns)
    assert not X.isnull().any().any()
    # one row with an unseen order still aligns to the training columns
    X2 = ml.build_matrix(df.head(1), list(X.columns))
    assert list(X2.columns) == list(X.columns)


def test_compute_ks_perfect_and_random():
    assert ml.compute_ks([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert ml.compute_ks([0, 0], [0.1, 0.2]) == 0.0


def test_train_and_predict(df):
    prep = ml.prepare_training_data(df)
    model, params = ml.train_logistic_regression(prep["X_train"], prep["y_train"])
    m = ml.evaluate_model(model, prep["X_test"], prep["y_test"])
    assert 0.5 < m["auc"] <= 1 and np.array(m["confusion_matrix"]).sum() == len(prep["y_test"])
    out = ml.predict_frame(model, prep["scaler"], prep["feature_names"], df.head(5).drop(columns="churn"))
    assert out["risk_level"].isin(["Low", "Medium", "High"]).all()
