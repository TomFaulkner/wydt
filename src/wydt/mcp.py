import json
import os
import sys
import hashlib
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wydt.models import db, DailyLog
from wydt import create_app


def _get_password_hash():
    password = os.getenv("WYDT_PASSWORD")
    if not password:
        return None
    return hashlib.sha256(password.encode()).hexdigest()


def _verify_password(password: str) -> bool:
    stored_hash = _get_password_hash()
    if not stored_hash:
        return True
    return hashlib.sha256(password.encode()).hexdigest() == stored_hash


_authenticated = False


def _auto_auth():
    global _authenticated
    password = os.getenv("WYDT_PASSWORD")
    if password and _verify_password(password):
        _authenticated = True


_auto_auth()


def get_app():
    app = create_app()
    return app


def handle_request(request_json):
    global _authenticated
    method = request_json.get("method")
    params = request_json.get("params", {})

    if method == "initialize":
        server_info = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "wydt", "version": "1.0.0"},
        }
        if _get_password_hash():
            server_info["capabilities"]["tools"] = {}
        return server_info

    if method == "auth/authorize":
        password = params.get("password", "")
        if _verify_password(password):
            global _authenticated
            _authenticated = True
            return {"authorized": True}
        return {"authorized": False, "error": "Invalid password"}

    if method == "auth/validate":
        if _authenticated:
            return {"valid": True}
        return {"valid": False}

    def check_auth():
        if _get_password_hash() is None:
            return True
        return _authenticated

    if not check_auth():
        return {"error": "Authentication required"}

    if method == "tools/list":
        return {
            "tools": [
                {
                    "name": "get_logs",
                    "description": "Get daily journal logs, optionally filtered by keyword or date",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "q": {"type": "string", "description": "Keyword search"},
                            "date": {
                                "type": "string",
                                "description": "Filter by date (YYYY-MM-DD)",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max results (default 10)",
                            },
                        },
                    },
                },
                {
                    "name": "get_log",
                    "description": "Get a specific day's journal entry",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date (YYYY-MM-DD)",
                            }
                        },
                        "required": ["date"],
                    },
                },
                {
                    "name": "create_log",
                    "description": "Create or update a journal entry",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date (YYYY-MM-DD), defaults to today",
                            },
                            "content": {
                                "type": "string",
                                "description": "Journal content",
                            },
                        },
                        "required": ["content"],
                    },
                },
                {
                    "name": "search_logs",
                    "description": "Search journal entries by keyword",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search keyword",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max results (default 10)",
                            },
                        },
                        "required": ["query"],
                    },
                },
            ]
        }

    if method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        app = get_app()
        with app.app_context():
            if tool_name == "get_logs":
                q = tool_args.get("q", "")
                filter_date = tool_args.get("date")
                limit = tool_args.get("limit", 10)

                query = DailyLog.query
                if q:
                    query = query.filter(
                        (DailyLog.content.ilike(f"%{q}%"))
                        | (DailyLog.summary.ilike(f"%{q}%"))
                        | (DailyLog.keywords.ilike(f"%{q}%"))
                    )
                if filter_date:
                    try:
                        filter_date_obj = datetime.strptime(
                            filter_date, "%Y-%m-%d"
                        ).date()
                        query = query.filter_by(date=filter_date_obj)
                    except ValueError:
                        pass

                logs = query.order_by(DailyLog.date.desc()).limit(limit).all()
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                [log.to_dict() for log in logs], indent=2
                            ),
                        }
                    ]
                }

            if tool_name == "get_log":
                log_date = tool_args.get("date")
                if not log_date:
                    return {
                        "content": [{"type": "text", "text": "Error: date required"}]
                    }
                try:
                    log_date_obj = datetime.strptime(log_date, "%Y-%m-%d").date()
                except ValueError:
                    return {
                        "content": [
                            {"type": "text", "text": "Error: invalid date format"}
                        ]
                    }

                log = DailyLog.query.filter_by(date=log_date_obj).first()
                if log is None:
                    return {
                        "content": [
                            {"type": "text", "text": "No entry found for that date"}
                        ]
                    }
                return {
                    "content": [
                        {"type": "text", "text": json.dumps(log.to_dict(), indent=2)}
                    ]
                }

            if tool_name == "create_log" or tool_name == "search_logs":
                content = tool_args.get("content", "")
                query_str = tool_args.get("query", "")

                if tool_name == "search_logs":
                    content = f"Search results for: {query_str}"
                    q = query_str
                else:
                    q = None

                log_date = tool_args.get("date")
                if not log_date:
                    log_date_obj = date.today()
                else:
                    try:
                        log_date_obj = datetime.strptime(log_date, "%Y-%m-%d").date()
                    except ValueError:
                        return {
                            "content": [
                                {"type": "text", "text": "Error: invalid date format"}
                            ]
                        }

                log = DailyLog.get_or_create(log_date_obj)
                log.content = content
                log.updated_at = datetime.utcnow()
                db.session.commit()

                return {
                    "content": [
                        {"type": "text", "text": json.dumps(log.to_dict(), indent=2)}
                    ]
                }

    return {"error": "Unknown method"}


def main():
    for line in sys.stdin:
        try:
            request_json = json.loads(line.strip())
            response = handle_request(request_json)
            print(json.dumps(response), flush=True)
        except Exception as e:
            print(json.dumps({"error": str(e)}), flush=True)


if __name__ == "__main__":
    main()
