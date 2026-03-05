import os
import logging
from datetime import date, datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from .models import db, DailyLog
from .llm import generate_summary_and_keywords
from .auth import require_auth


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "sqlite:///wydt.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()

    @app.context_processor
    def inject_today():
        return {"today": date.today().isoformat()}

    @app.route("/")
    @require_auth
    def index():
        q = request.args.get("q", "")
        filter_date = request.args.get("date", "")

        query = DailyLog.query

        if q:
            query = query.filter(
                (DailyLog.content.ilike(f"%{q}%"))
                | (DailyLog.summary.ilike(f"%{q}%"))
                | (DailyLog.keywords.ilike(f"%{q}%"))
            )

        if filter_date:
            try:
                filter_date_obj = datetime.strptime(filter_date, "%Y-%m-%d").date()
                query = query.filter_by(date=filter_date_obj)
            except ValueError:
                pass

        logs = query.order_by(DailyLog.date.desc()).limit(50).all()

        if request.headers.get("HX-Request"):
            return render_template(
                "logs_partial.html", logs=logs, q=q, filter_date=filter_date
            )

        return render_template("index.html", logs=logs, q=q, filter_date=filter_date)

    @app.route("/entry/<date_str>", methods=["GET", "POST"])
    @require_auth
    def entry(date_str):
        try:
            log_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return "Invalid date format", 400

        log = DailyLog.get_or_create(log_date)

        if request.method == "POST":
            content = request.form.get("content", "")
            log.content = content
            if content.strip():
                log.summary, log.keywords = generate_summary_and_keywords(content)
            else:
                log.summary = ""
                log.keywords = ""
            log.updated_at = datetime.utcnow()
            db.session.commit()

            if request.headers.get("HX-Request"):
                return render_template("entry.html", log=log)
            return redirect(url_for("index"))

        return render_template("entry.html", log=log)

    @app.route("/api/logs", methods=["GET"])
    @require_auth
    def api_list_logs():
        q = request.args.get("q", "")
        filter_date = request.args.get("date", "")

        query = DailyLog.query

        if q:
            query = query.filter(
                (DailyLog.content.ilike(f"%{q}%"))
                | (DailyLog.summary.ilike(f"%{q}%"))
                | (DailyLog.keywords.ilike(f"%{q}%"))
            )

        if filter_date:
            try:
                filter_date_obj = datetime.strptime(filter_date, "%Y-%m-%d").date()
                query = query.filter_by(date=filter_date_obj)
            except ValueError:
                pass

        logs = query.order_by(DailyLog.date.desc()).limit(100).all()
        return jsonify([log.to_dict() for log in logs])

    @app.route("/api/logs/<date_str>", methods=["GET"])
    @require_auth
    def api_get_log(date_str):
        try:
            log_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid date format"}), 400

        log = DailyLog.query.filter_by(date=log_date).first()
        if log is None:
            return jsonify({"error": "Not found"}), 404
        return jsonify(log.to_dict())

    @app.route("/api/logs", methods=["POST"])
    @require_auth
    def api_create_log():
        data = request.get_json()
        if not data or "content" not in data:
            return jsonify({"error": "content required"}), 400

        log_date = date.today()
        if "date" in data:
            try:
                log_date = datetime.strptime(data["date"], "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"error": "Invalid date format"}), 400

        log = DailyLog.get_or_create(log_date)
        log.content = data["content"]
        if data["content"].strip():
            log.summary, log.keywords = generate_summary_and_keywords(data["content"])
        log.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify(log.to_dict()), 201

    @app.route("/mcp", methods=["POST"])
    def mcp():
        from .mcp import handle_request

        try:
            data = request.get_json()
            response = handle_request(data)
            return jsonify(response)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


def main():
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
