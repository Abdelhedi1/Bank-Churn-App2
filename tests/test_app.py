import io
import json
from datetime import UTC

from app import db, scoring
from tests.conftest import PASSWORD, client_for, make_df


# ---------------------------------------------------------- login & access (REQ-11)
def test_pages_need_login(fresh_app):
    c = fresh_app.test_client()
    for path in ["/", "/prediction", "/insights", "/analytics", "/retention", "/data", "/admin"]:
        assert c.get(path).status_code == 302
    assert c.get("/api/dashboard").status_code == 401


def test_login_rejects_wrong_password(fresh_app):
    c = fresh_app.test_client()
    with c.session_transaction() as s:
        s["csrf"] = "tok"
    r = c.post("/login", data={"username": "admin", "password": "nope", "csrf_token": "tok"})
    assert r.status_code == 200 and b"Wrong username or password" in r.data


def test_login_does_not_redirect_off_site(fresh_app):
    c = fresh_app.test_client()
    with c.session_transaction() as s:
        s["csrf"] = "tok"
    r = c.post("/login?next=//evil.example", data={"username": "admin", "password": PASSWORD, "csrf_token": "tok"})
    assert r.status_code == 302 and "evil" not in r.headers["Location"]


def test_csrf_token_required(env):
    c = client_for(env, "admin")
    assert c.post("/api/admin/settings", json={"alert_threshold": 50}).status_code == 400
    assert c.post("/api/admin/settings", json={"alert_threshold": 50}, headers=c.h).status_code == 200


def test_every_page_renders_for_admin(env):
    c = client_for(env, "admin")
    for path in ["/", "/prediction", "/insights", "/analytics", "/retention", "/data", "/admin"]:
        assert c.get(path).status_code == 200, path


def test_role_gating(env):
    rm, ex, ret = client_for(env, "rm_france"), client_for(env, "executive"), client_for(env, "retention")
    assert rm.get("/data").status_code == 403
    assert rm.post("/api/admin/score", headers=rm.h).status_code == 403
    assert ex.get("/insights").status_code == 403 and ex.get("/api/customers").status_code == 403
    assert ex.get("/api/dashboard").status_code == 200
    assert ret.get("/admin").status_code == 403
    assert ret.get("/api/export/high-risk.csv").status_code == 200
    assert rm.get("/api/export/high-risk.csv").status_code == 403


# ------------------------------------------------ scoring, scope, masking (REQ-01, 14, 15)
def test_dashboard_numbers_are_consistent(env):
    d = client_for(env, "admin").get("/api/dashboard").get_json()
    assert d["kpis"]["total"] == 900 and d["scored"]
    assert sum(d["tiers"].values()) == d["kpis"]["active"]
    assert 0 < d["kpis"]["historical_churn_rate"] < 100
    assert abs(d["kpis"]["historical_churn_rate"] + d["kpis"]["retention_rate"] - 100) < 0.11


def test_relationship_manager_only_sees_own_branch(env):
    rm = client_for(env, "rm_france")
    items = rm.get("/api/customers?per_page=100").get_json()["items"]
    assert items and {i["country"] for i in items} == {"France"}
    other = client_for(env, "rm_spain").get("/api/customers?per_page=1").get_json()["items"][0]["id"]
    assert rm.get(f"/api/customers/{other}").status_code == 404
    assert rm.get("/api/dashboard").get_json()["kpis"]["total"] < 900


def test_customer_references_are_masked(env):
    body = client_for(env, "retention").get("/api/customers?per_page=50").get_data(as_text=True)
    assert "10000" not in body.replace("C-****", "")  # no raw 8-digit ids from the synthetic data
    assert "C-****" in body
    assert db.mask_ref("15634602") == "C-****4602"


def test_viewing_customers_is_audited(env):
    rm = client_for(env, "rm_germany")
    cid = rm.get("/api/customers?per_page=3").get_json()["items"][0]["id"]
    rm.get(f"/api/customers/{cid}")
    log = client_for(env, "admin").get("/api/admin/audit?limit=200").get_json()["items"]
    mine = [a for a in log if a["user"] == "rm_germany"]
    assert {"view_customer_list", "view_customer"} <= {a["action"] for a in mine}
    assert all(a["customer"] is None or a["customer"].startswith("C-****") for a in log)


def test_each_customer_has_three_factors_and_suggestions(env):
    c = client_for(env, "retention")
    cid = c.get("/api/customers?tier=High&per_page=1").get_json()["items"][0]["id"]
    d = c.get(f"/api/customers/{cid}").get_json()
    assert len(d["factors"]) == 3 and d["actions"] and d["tier"] == "High"


# ------------------------------------------------------------ alerts & actions (REQ-03, 07, 20)
def test_alerts_follow_threshold_and_assignment(env):
    admin = client_for(env, "admin")
    assert admin.post("/api/admin/settings", json={"alert_threshold": 0}, headers=admin.h).status_code == 400
    admin.post("/api/admin/settings", json={"alert_threshold": 30}, headers=admin.h)
    r = admin.post("/api/admin/score", headers=admin.h).get_json()
    assert r["high_risk"] > 0
    rm = client_for(env, "rm_france")
    alerts = rm.get("/api/alerts").get_json()["items"]
    assert alerts and all(a["rm"] == "RM France" for a in alerts)
    assert rm.post(f"/api/alerts/{alerts[0]['id']}/ack", headers=rm.h).status_code == 200
    assert rm.get("/api/alerts?status=new").get_json()["items"] != alerts


def test_retention_actions_are_logged_not_executed(env):
    rm = client_for(env, "rm_france")
    cid = rm.get("/api/customers?per_page=1").get_json()["items"][0]["id"]
    r = rm.post("/api/retention/actions", json={"customer_id": cid, "type": "Phone call", "notes": "x"}, headers=rm.h)
    assert r.status_code == 201
    assert rm.post("/api/retention/actions", json={"customer_id": cid, "type": "Send offer now"}, headers=rm.h).status_code == 400
    aid = rm.get("/api/retention/actions").get_json()["items"][0]["id"]
    assert rm.patch(f"/api/retention/actions/{aid}", json={"status": "done"}, headers=rm.h).status_code == 200
    spain_cid = client_for(env, "rm_spain").get("/api/customers?per_page=1").get_json()["items"][0]["id"]
    assert rm.post("/api/retention/actions", json={"customer_id": spain_cid, "type": "Email"}, headers=rm.h).status_code == 404
    ex = client_for(env, "executive")
    assert ex.post("/api/retention/actions", json={"customer_id": cid, "type": "Email"}, headers=ex.h).status_code == 403


# ------------------------------------------------------------ export & reports (REQ-08, 09)
def test_export_high_risk_segment(env):
    c = client_for(env, "retention")
    r = c.get("/api/export/high-risk.csv?tier=High")
    lines = r.get_data(as_text=True).strip().splitlines()
    assert r.mimetype == "text/csv" and lines[0].startswith("customer_id,country,products")
    log = client_for(env, "admin").get("/api/admin/audit?action=export_segment").get_json()["items"]
    assert log


def test_monthly_report(env):
    c = client_for(env, "executive")
    month = db.now()[:7]
    r = c.get(f"/api/reports/monthly?month={month}").get_json()
    assert r["snapshot"]["scored"] > 0 and r["activity"]["scoring_runs"] >= 1
    assert c.get("/api/reports/monthly?month=2026-13").status_code == 400
    assert c.get(f"/api/reports/monthly.csv?month={month}").get_data(as_text=True).startswith("section,metric,value")
    assert client_for(env, "rm_france").get("/api/reports/monthly").status_code == 403


# ----------------------------------------------------------------- predict, admin, ingest
def test_adhoc_prediction_and_validation(env):
    c = client_for(env, "executive")
    ok = {"credit_score": 650, "country": "France", "products_number": 2, "credit_card": 1, "active_member": 1,
          "estimated_salary": 90000, "age": 52, "gender": "Male", "tenure": 3, "balance": 60000}
    r = c.post("/api/predict", json=ok, headers=c.h).get_json()
    assert 0 <= r["probability"] <= 100 and r["tier"] in {"Low", "Medium", "High"} and len(r["factors"]) == 3
    assert c.post("/api/predict", json={**ok, "age": -5}, headers=c.h).status_code == 400
    assert c.post("/api/predict", json={**ok, "age": "abc"}, headers=c.h).status_code == 400


def test_batch_scoring_masks_ids_on_screen_but_not_in_file(env):
    c = client_for(env, "retention")
    csv = make_df(40, seed=3).drop(columns="churn").to_csv(index=False).encode()
    r = c.post("/api/predict/batch", data={"file": (io.BytesIO(csv), "b.csv")}, headers=c.h,
               content_type="multipart/form-data").get_json()
    assert r["count"] == 40 and all(str(row["customer_id"]).startswith("C-****") for row in r["rows"])
    assert "10000" in c.get("/api/predict/batch/download").get_data(as_text=True)


def test_user_management(env):
    a = client_for(env, "admin")
    bad = a.post("/api/admin/users", json={"username": "x", "name": "X", "role": "rm", "password": "short"}, headers=a.h)
    assert bad.status_code == 400
    good = a.post("/api/admin/users", json={"username": "rm_new", "name": "New RM", "role": "rm",
                                            "branch": "Italy", "password": "a-long-password"}, headers=a.h)
    assert good.status_code == 201
    assert a.post("/api/admin/users", json={"username": "rm_new", "name": "N", "role": "rm",
                                            "password": "a-long-password"}, headers=a.h).status_code == 409


def test_ingest_validates_and_accepts_reduced_files(fresh_app):
    a = client_for(fresh_app, "admin")
    def up(csv):
        return a.post("/api/data/upload", data={"file": (io.BytesIO(csv), "d.csv")},
                      headers=a.h, content_type="multipart/form-data")
    assert up(b"a,b\n1,2\n").status_code == 400
    small = make_df(50)[["credit_score", "country", "products_number", "credit_card", "active_member",
                         "estimated_salary"]]
    r = up(small.to_csv(index=False).encode())
    assert r.status_code == 200 and r.get_json()["rows"] == 50
    assert a.get("/api/data/summary").get_json()["rows"] == 50
    assert a.post("/api/features", headers=a.h).status_code == 409  # no churn labels to learn from


def test_weekly_schedule_logic(env):
    from datetime import datetime, timedelta
    conn = db.connect(env.config["DB_PATH"])
    assert not scoring.is_due(conn)
    assert scoring.is_due(conn, datetime.now(UTC) + timedelta(days=8))
    conn.close()


def test_bundled_sample_dataset_loads(tmp_path):

    from app import create_app
    app = create_app({"TESTING": True, "DB_PATH": tmp_path / "s.db", "MODELS_DIR": tmp_path / "m"})
    c = client_for(app, "admin")
    r = c.post("/api/data/sample", headers=c.h)
    assert r.status_code == 200 and r.get_json()["rows"] == 8000
    assert json.loads(c.get("/api/data/summary").data)["churn_rate"] > 0.19
