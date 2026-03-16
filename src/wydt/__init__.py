import os
import logging
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from .models import db, DailyLog, WeeklySummary
from .llm import generate_summary_and_keywords, generate_weekly_summary
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
        today = date.today()
        year, week, _ = today.isocalendar()
        return {
            "today": today.isoformat(),
            "current_year": year,
            "current_week": week,
        }

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

    @app.route("/weekly/<int:year>/<int:week_number>")
    @require_auth
    def weekly_summary(year, week_number):
        # Validate week number
        if week_number < 1 or week_number > 53:
            return "Invalid week number", 400

        # Get or create the weekly summary
        summary = WeeklySummary.get_or_create(year, week_number)

        # Get daily logs for this week
        logs = (
            DailyLog.query.filter(
                DailyLog.date >= summary.start_date, DailyLog.date <= summary.end_date
            )
            .order_by(DailyLog.date.asc())
            .all()
        )

        # Get recent weeks for the dropdown
        recent_weeks = _get_recent_weeks()

        return render_template(
            "weekly.html",
            summary=summary,
            logs=logs,
            recent_weeks=recent_weeks,
            prev_week=_get_adjacent_week(year, week_number, -1),
            next_week=_get_adjacent_week(year, week_number, 1),
        )

    @app.route("/api/weekly/<int:year>/<int:week_number>/regenerate", methods=["POST"])
    @require_auth
    def api_regenerate_weekly_summary(year, week_number):
        # Validate week number
        if week_number < 1 or week_number > 53:
            return jsonify({"error": "Invalid week number"}), 400

        # Get or create the weekly summary
        weekly_summary = WeeklySummary.get_or_create(year, week_number)

        # Get daily logs for this week
        logs = (
            DailyLog.query.filter(
                DailyLog.date >= weekly_summary.start_date,
                DailyLog.date <= weekly_summary.end_date,
            )
            .order_by(DailyLog.date.asc())
            .all()
        )

        # Only generate if we have logs with content
        logs_with_content = [log for log in logs if log.content.strip()]

        if logs_with_content:
            logs_data = [
                {
                    "date": log.date.isoformat(),
                    "content": log.content,
                    "summary": log.summary,
                    "keywords": log.keywords,
                }
                for log in logs_with_content
            ]

            result = generate_weekly_summary(logs_data)

            weekly_summary.summary = result["summary"]
            weekly_summary.themes = result["themes"]
            weekly_summary.accomplishments = result["accomplishments"]
            weekly_summary.highlights = result["highlights"]
            weekly_summary.references = result["references"]
            weekly_summary.updated_at = datetime.utcnow()
            db.session.commit()

        if request.headers.get("HX-Request"):
            return render_template(
                "weekly_summary_partial.html",
                summary=weekly_summary,
                logs=logs,
            )

        return jsonify(weekly_summary.to_dict())

    @app.route("/api/weeks/recent")
    @require_auth
    def api_recent_weeks():
        """Get list of recent weeks with entries for the dropdown."""
        weeks = _get_recent_weeks()
        return jsonify(weeks)

    def _get_recent_weeks():
        """Get recent weeks (with entries or recent dates) for the dropdown."""
        weeks = []
        today = date.today()

        # Get weeks that have entries
        logs_with_weeks = (
            db.session.query(
                db.func.strftime("%Y", DailyLog.date).label("year"),
                db.func.strftime("%W", DailyLog.date).label("week"),
            )
            .distinct()
            .order_by(
                db.func.strftime("%Y", DailyLog.date).desc(),
                db.func.strftime("%W", DailyLog.date).desc(),
            )
            .limit(12)
            .all()
        )

        seen = set()
        for year_str, week_str in logs_with_weeks:
            year = int(year_str)
            # SQLite's %W gives 0-53, but Python's isocalendar uses 1-53
            week = int(week_str) + 1 if week_str else 1
            key = (year, week)
            if key not in seen:
                seen.add(key)
                try:
                    start = date.fromisocalendar(year, week, 1)
                    end = start + timedelta(days=6)
                    weeks.append(
                        {
                            "year": year,
                            "week_number": week,
                            "label": f"Week {week}, {year} ({start.strftime('%b %d')} - {end.strftime('%b %d')})",
                        }
                    )
                except ValueError:
                    pass

        # Add current week if not already included
        current_year, current_week, _ = today.isocalendar()
        if (current_year, current_week) not in seen:
            start = date.fromisocalendar(current_year, current_week, 1)
            end = start + timedelta(days=6)
            weeks.insert(
                0,
                {
                    "year": current_year,
                    "week_number": current_week,
                    "label": f"Week {current_week}, {current_year} ({start.strftime('%b %d')} - {end.strftime('%b %d')}) [Current]",
                },
            )

        return weeks

    def _get_adjacent_week(year, week_number, direction):
        """Get the previous or next week."""
        try:
            current_date = date.fromisocalendar(year, week_number, 1)
            new_date = current_date + timedelta(weeks=direction)
            new_year, new_week, _ = new_date.isocalendar()
            return {"year": new_year, "week_number": new_week}
        except ValueError:
            return None

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
