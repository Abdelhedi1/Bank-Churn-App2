import io
import time


def _upload(client, csv_bytes):
    return client.post("/api/data/upload", data={"file": (io.BytesIO(csv_bytes), "d.csv")},
                       content_type="multipart/form-data")


def test_pages_render(client):
    for path in ["/", "/data", "/features", "/training", "/prediction"]:
        assert client.get(path).status_code == 200


def test_requires_data_first(client):
    assert client.get("/api/data/summary").status_code == 409
    assert client.post("/api/features").status_code == 409
    assert client.post("/api/predict", json={}).status_code == 409


def test_rejects_bad_upload(client):
    r = client.post("/api/data/upload", data={"file": (io.BytesIO(b"a,b\n1,2\n"), "x.csv")},
                    content_type="multipart/form-data")
    assert r.status_code == 400


def test_sample_missing_is_404(client):
    assert client.post("/api/data/sample").status_code == 404


def test_full_flow(client, csv_bytes):
    assert _upload(client, csv_bytes).status_code == 200
    s = client.get("/api/data/summary").get_json()
    assert s["rows"] == 600 and 0 < s["churn_rate"] < 1
    assert client.post("/api/features").get_json()["n_features"] > 10

    assert client.post("/api/train", json={"models": ["lr"], "smote": True}).status_code == 200
    for _ in range(120):
        r = client.get("/api/train/results").get_json()
        if r["job"]["status"] != "running":
            break
        time.sleep(0.5)
    assert r["job"]["status"] == "done", r["job"]
    assert r["best_model"] == "Logistic Regression"

    p = client.post("/api/predict", json={
        "credit_score": 650, "age": 38, "gender": "Male", "country": "France", "tenure": 5,
        "balance": 75000, "products_number": 2, "credit_card": 1, "active_member": 1,
        "estimated_salary": 100000}).get_json()
    assert 0 <= p["probability"] <= 1 and p["risk_level"] in {"Low", "Medium", "High"}

    b = client.post("/api/predict/batch", data={"file": (io.BytesIO(csv_bytes), "b.csv")},
                    content_type="multipart/form-data").get_json()
    assert b["count"] == 600 and "churn_probability" in b["columns"]
    dl = client.get("/api/predict/batch/download")
    assert dl.mimetype == "text/csv" and dl.data.count(b"\n") == 601
