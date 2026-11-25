from datetime import date, datetime, timedelta
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Prompts live in the database (see the Prompt model) so they can be edited
# from the UI. These are the seed values for new rows and the fallback for
# contexts where there's no database available.
DEFAULT_PROMPTS: dict[str, tuple[str, str]] = {
    "daily_summary": (
        "Daily summary - system message",
        """You are a helpful assistant that processes daily journal entries.
Analyze the entry and provide:
1. A brief 1-2 sentence summary of what the person did that day
2. A comma-separated list of 3-8 relevant keywords/tags for searching

Format your response as:
SUMMARY: <summary text>
KEYWORDS: <keyword1>, <keyword2>, <keyword3>, ...""",
    ),
    "daily_summary_user": (
        "Daily summary - user message",
        """Process this daily log:

{content}""",
    ),
    "weekly_summary": (
        "Weekly summary - system message",
        """You are a helpful assistant that creates weekly summaries from daily journal entries.
Analyze the week's entries and provide:

1. A brief 2-3 sentence overall summary of the week
2. Key themes or focus areas for the week (comma-separated list)
3. Major accomplishments or completed tasks (bullet points, one per line)
4. Notable highlights or interesting moments (bullet points, one per line)
5. Any ticket numbers, IDs, references, or identifiers mentioned (e.g., #123, ABC-456, PR-789, etc.) - comma-separated list

Be concise but informative. Look for patterns across the week.

Format your response exactly as:
SUMMARY: <overall summary text>
THEMES: <theme1>, <theme2>, ...
ACCOMPLISHMENTS:
- <accomplishment 1>
- <accomplishment 2>
HIGHLIGHTS:
- <highlight 1>
- <highlight 2>
REFERENCES: <reference1>, <reference2>, ... (or "None" if no identifiers found)""",
    ),
    "weekly_summary_user": (
        "Weekly summary - user message",
        """Create a weekly summary from these daily entries:

{logs}""",
    ),
    "weekly_log_entry": (
        "Weekly summary - one day's entry",
        """Date: {date}
Summary: {summary}
Content: {content}""",
    ),
}

# Placeholders each prompt can use, shown as a hint in the editor.
PROMPT_PLACEHOLDERS: dict[str, list[str]] = {
    "daily_summary_user": ["content"],
    "weekly_summary_user": ["logs"],
    "weekly_log_entry": ["date", "summary", "content"],
}


def render_prompt(template: str, **values: str) -> str:
    """Fill {placeholders} in a prompt template.

    Plain replacement rather than str.format so extra braces in a prompt stay
    literal instead of raising.
    """
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


class Prompt(db.Model):
    __tablename__ = "prompts"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    label = db.Column(db.String(128), nullable=False, default="")
    content = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "label": self.label,
            "content": self.content,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @property
    def default_text(self) -> str:
        return DEFAULT_PROMPTS.get(self.key, ("", ""))[1]

    @property
    def is_default(self) -> bool:
        return self.content.strip() == self.default_text.strip()

    @classmethod
    def get_or_create(cls, key: str) -> "Prompt":
        prompt = cls.query.filter_by(key=key).first()
        if prompt is None:
            label, text = DEFAULT_PROMPTS.get(key, (key, ""))
            prompt = cls(key=key, label=label, content=text)
            db.session.add(prompt)
            db.session.commit()
        return prompt

    @classmethod
    def all_prompts(cls) -> list["Prompt"]:
        """All editable prompts, seeded with defaults when missing."""
        cls.ensure_defaults()
        # Display in DEFAULT_PROMPTS order, which groups system/user prompts,
        # so it stays stable even for rows added by an earlier version.
        order = list(DEFAULT_PROMPTS)
        return sorted(
            cls.query.filter(cls.key.in_(order)).all(),
            key=lambda p: order.index(p.key),
        )

    @classmethod
    def get_text(cls, key: str) -> str:
        """Current text for a prompt, falling back to the built-in default."""
        default = DEFAULT_PROMPTS.get(key, ("", ""))[1]
        try:
            prompt = cls.query.filter_by(key=key).first()
        except Exception:
            return default
        if prompt is None or not prompt.content.strip():
            return default
        return prompt.content

    @classmethod
    def ensure_defaults(cls) -> None:
        """Create rows for any prompt keys that don't exist yet.

        Existing rows are never overwritten, including ones the user cleared,
        but labels are refreshed so renames to the built-in labels show up.
        """
        changed = False
        for key, (label, text) in DEFAULT_PROMPTS.items():
            prompt = cls.query.filter_by(key=key).first()
            if prompt is None:
                db.session.add(cls(key=key, label=label, content=text))
                changed = True
            elif prompt.label != label:
                prompt.label = label
                changed = True
        if changed:
            db.session.commit()

    @classmethod
    def reset_to_default(cls, key: str) -> "Prompt":
        prompt = cls.get_or_create(key)
        prompt.content = DEFAULT_PROMPTS.get(key, ("", ""))[1]
        db.session.commit()
        return prompt


class DailyLog(db.Model):
    __tablename__ = "daily_logs"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False, index=True)
    content = db.Column(db.Text, nullable=False, default="")
    summary = db.Column(db.Text, nullable=False, default="")
    keywords = db.Column(db.Text, nullable=False, default="")
    summary_error = db.Column(db.Text, nullable=False, default="")
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
            "summary_error": self.summary_error,
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
    summary_error = db.Column(db.Text, nullable=False, default="")
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
            "summary_error": self.summary_error,
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
