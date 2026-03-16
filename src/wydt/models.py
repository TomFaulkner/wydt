from datetime import date, datetime, timedelta
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class DailyLog(db.Model):
    __tablename__ = "daily_logs"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False, index=True)
    content = db.Column(db.Text, nullable=False, default="")
    summary = db.Column(db.Text, nullable=False, default="")
    keywords = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "content": self.content,
            "summary": self.summary,
            "keywords": self.keywords,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def get_or_create(cls, log_date: date) -> "DailyLog":
        log = cls.query.filter_by(date=log_date).first()
        if log is None:
            log = cls(date=log_date)
            db.session.add(log)
            db.session.commit()
        return log


class WeeklySummary(db.Model):
    __tablename__ = "weekly_summaries"

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    summary = db.Column(db.Text, nullable=False, default="")
    themes = db.Column(db.Text, nullable=False, default="")
    accomplishments = db.Column(db.Text, nullable=False, default="")
    highlights = db.Column(db.Text, nullable=False, default="")
    references = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (db.UniqueConstraint("year", "week_number", name="uix_year_week"),)

    def to_dict(self):
        return {
            "id": self.id,
            "year": self.year,
            "week_number": self.week_number,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "summary": self.summary,
            "themes": self.themes,
            "accomplishments": self.accomplishments,
            "highlights": self.highlights,
            "references": self.references,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def get_or_create(cls, year: int, week_number: int) -> "WeeklySummary":
        summary = cls.query.filter_by(year=year, week_number=week_number).first()
        if summary is None:
            # Calculate start (Monday) and end (Sunday) dates for this ISO week
            start_date = date.fromisocalendar(year, week_number, 1)
            end_date = start_date + timedelta(days=6)
            summary = cls(
                year=year,
                week_number=week_number,
                start_date=start_date,
                end_date=end_date,
            )
            db.session.add(summary)
            db.session.commit()
        return summary

    @classmethod
    def get_for_date(cls, log_date: date) -> "WeeklySummary":
        """Get or create the weekly summary for a given date."""
        year, week_number, _ = log_date.isocalendar()
        return cls.get_or_create(year, week_number)
