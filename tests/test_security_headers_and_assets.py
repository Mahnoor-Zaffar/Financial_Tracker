def test_response_includes_content_security_policy(client):
    response = client.get("/")

    assert response.status_code == 200
    csp = response.headers.get("Content-Security-Policy")
    assert csp is not None
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_production_configuration_includes_hsts(app):
    app.config.update(DEBUG=False, TESTING=False, SESSION_COOKIE_SECURE=True)

    response = app.test_client().get("/")

    assert response.status_code == 200
    assert response.headers.get("Strict-Transport-Security") == "max-age=31536000; includeSubDomains"


def test_affected_templates_render_with_self_hosted_assets(app, client, login, make_user, seed_finance):
    user_id = make_user("csp-assets@example.com")
    seed_finance(user_id)
    assert login("csp-assets@example.com").status_code == 302

    dashboard_response = client.get("/dashboard")
    analytics_response = client.get("/analytics/")
    transaction_response = client.get("/transactions/new")

    assert dashboard_response.status_code == 200
    assert analytics_response.status_code == 200
    assert transaction_response.status_code == 200

    dashboard_html = dashboard_response.get_data(as_text=True)
    analytics_html = analytics_response.get_data(as_text=True)
    transaction_html = transaction_response.get_data(as_text=True)

    for html in (dashboard_html, analytics_html, transaction_html):
        assert "https://fonts.googleapis.com" not in html
        assert "https://fonts.gstatic.com" not in html
        assert "https://cdn.jsdelivr.net" not in html
        assert 'type="application/json"' not in html
        assert "/static/js/theme-init.js" in html
        assert "/static/js/app.js" in html

    assert "/static/js/charts.js" in dashboard_html
    assert "/static/js/charts.js" in analytics_html
    assert "data-chart-payload=" in dashboard_html
    assert "data-chart-payload=" in analytics_html
    assert "data-category-options=" in transaction_html
