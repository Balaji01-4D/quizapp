# How to Play manual page
import os
import csv
from io import StringIO
from functools import wraps
from flask import Flask, render_template, request, jsonify, Response, redirect, url_for
from flask_cors import CORS
import json
from pathlib import Path
from dotenv import load_dotenv
from peewee import IntegrityError

# Peewee ORM imports
from models import db, Participant, Result, Answer

load_dotenv()

app = Flask(__name__, static_folder="frontend/static", template_folder="frontend/templates")
CORS(app)

# === Database Connection Management ===
@app.before_request
def before_request():
    """Connect to the database before each request."""
    if db.is_closed():
        db.connect()

@app.after_request
def after_request(response):
    """Close the database connection after each request."""
    if not db.is_closed():
        db.close()
    return response

QUESTIONS_FILE = Path(__file__).parent / "questions.json"

# === Admin Basic Auth ===
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

def _unauthorized():
    return Response("Authentication required", 401, {"WWW-Authenticate": 'Basic realm="Admin"'})

def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not (ADMIN_USERNAME and ADMIN_PASSWORD):
            return Response("Admin credentials not configured", status=500)
        auth = request.authorization
        if not auth or not (auth.username == ADMIN_USERNAME and auth.password == ADMIN_PASSWORD):
            return _unauthorized()
        return fn(*args, **kwargs)
    return wrapper

# === Routes ===
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/how-to-play.html")
def how_to_play():
    return render_template("how-to-play.html")

@app.route("/register", methods=["POST"]) 
def register():
    try:
        data = request.get_json()
        name = data.get("name", "").strip()
        regno = data.get("regno", "").strip()
        college = data.get("college", "").strip()
        department = data.get("department", "").strip()
        year_raw = str(data.get("year", "")).strip()

        if not (name and regno and college and department and year_raw):
            return jsonify({"success": False, "message": "Missing fields"}), 400

        try:
            year = int(year_raw)
        except ValueError:
            return jsonify({"success": False, "message": "Year must be a number"}), 400

        # Enforce unique regno: reject duplicates and prevent updates to existing users
        existing = Participant.get_or_none(Participant.regno == regno)
        if existing:
            return jsonify({"success": False, "message": "Registration already exists for this regno"}), 409

        try:
            p = Participant.create(
                name=name,
                regno=regno,
                college=college,
                dept=department,
                year=year,
            )
        except IntegrityError:
            return jsonify({"success": False, "message": "Registration already exists for this regno"}), 409

        # Ensure a Result row exists for this participant (one-to-one)
        Result.get_or_create(participant=p, defaults={
            "correct": 0,
            "points": 0,
            "avg_time": 0.0,
        })

        return jsonify({"success": True, "message": "Registration successful", "name": p.name, "regno": p.regno})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

import random

@app.route("/questions")
def get_questions():
    if QUESTIONS_FILE.exists():
        with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
            qs = json.load(f)
        # Split into set a (first 15) and set b (last 15)
        set_a = qs[:15]
        set_b = qs[15:]
        chosen_set = random.choice([set_a, set_b])
        # Re-assign ids based on the selected questions' original indices in qs
        safe = []
        for i, q in enumerate(chosen_set):
            # The id should be the index in the full qs list
            idx = qs.index(q)
            safe.append({"id": idx, "question": q["question"], "options": q["options"]})
        return jsonify(safe)
    return jsonify([])

@app.route("/submit-quiz", methods=["POST"]) 
def submit_quiz():
    payload = request.get_json()
    if not payload:
        return jsonify({"success": False, "message": "No data"}), 400

    name = payload.get("name", "").strip()
    regno = payload.get("regno", "").strip()
    answers = payload.get("answers", [])

    if not regno:
        return jsonify({"success": False, "message": "Missing regno"}), 400

    
    try:
        p = Participant.get(Participant.regno == regno)
    except Participant.DoesNotExist:
        return jsonify({"success": False, "message": "Please register first"}), 400

    # Do not allow changing participant details during submission

    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        questions = json.load(f)

    correct = 0
    total_time = 0
    time_counts = 0

    for i, ans in enumerate(answers):
        # Get qId, fallback to i if not present or invalid
        qid = ans.get("qId", i)
        try:
            qid = int(qid)
        except (ValueError, TypeError):
            continue  # skip invalid qid
        if not (0 <= qid < len(questions)):
            continue  # skip out-of-range qid
        selected = ans.get("selected", None)
        try:
            selected = int(selected)
        except (ValueError, TypeError):
            continue  # skip invalid selected
        time_sec = ans.get("time_sec", None)
        if isinstance(time_sec, (int, float)):
            total_time += time_sec
            time_counts += 1
        # Compare answer index
        correct_answer = questions[qid].get("answer")
        if isinstance(correct_answer, int) and selected == correct_answer:
            correct += 1

    points = correct * 2
    avg_time = (total_time / time_counts) if time_counts else 0

    # Ensure result row exists, then update aggregates
    r, _ = Result.get_or_create(participant=p, defaults={
        "correct": correct,
        "points": points,
        "avg_time": avg_time,
    })
    r.correct = correct
    r.points = points
    r.avg_time = avg_time
    r.save()

    # Save answers (one attempt policy: clear previous)
    Answer.delete().where(Answer.result == r).execute()
    to_insert = []
    for ans in answers:
        to_insert.append({
            Answer.result: r.id,
            Answer.question_id: ans.get("qId"),
            Answer.answer: ans.get("selected"),
            Answer.time_taken: ans.get("time_sec"),
        })
    if to_insert:
        Answer.insert_many(to_insert).execute()

    return jsonify({"success": True, "redirect": "/leaderboard"})

# Leaderboard HTML page endpoint
@app.route("/result")
def leaderboard_page():
    try:
        rows = (
            Result
            .select(Result, Participant)
            .join(Participant)
            .order_by(Result.points.desc(), Result.avg_time.asc())
        )
        leaderboard_data = [
            {
                "name": r.participant.name,
                "regno": r.participant.regno,
                "correct": r.correct,
                "points": r.points,
                "avg_time": round(float(r.avg_time), 2) if r.avg_time is not None else ""
            }
            for r in rows
        ]
        return render_template("leaderboard_page.html", board=leaderboard_data)
    except Exception as e:
        return f"Error loading leaderboard: {e}", 500
@app.route("/leaderboard")
def leaderboard():
    # ORM query for all results joined with Participant
    rows = (
        Result
        .select(Result, Participant)
        .join(Participant)
        .order_by(Result.points.desc(), Result.avg_time.asc())
    )
    leaderboard_data = [
        {
            "name": r.participant.name,
            "regno": r.participant.regno,
            "correct": r.correct,
            "points": r.points,
            "avg_time": round(float(r.avg_time), 2) if r.avg_time is not None else ""
        }
        for r in rows
    ]
    # return render_template("leaderboard.html", board=leaderboard_data)
    return redirect(url_for('index'))  # Redirect to main page or update as needed

# === Admin Dashboard ===
@app.route("/admin")
@require_admin
def admin_dashboard():
    # Top 10 for quick view
    rows = (
        Result
        .select(Result, Participant)
        .join(Participant)
        .order_by(Result.points.desc(), Result.avg_time.asc())
        .limit(10)
    )
    top = [
        {
            "rank": i+1,
            "name": r.participant.name,
            "regno": r.participant.regno,
            "correct": r.correct,
            "points": r.points,
            "avg_time": round(float(r.avg_time), 2) if r.avg_time is not None else None,
        }
        for i, r in enumerate(rows)
    ]
    return render_template("admin.html", top=top)

@app.route("/admin/api/top")
@require_admin
def admin_api_top():
    rows = (
        Result
        .select(Result, Participant)
        .join(Participant)
        .order_by(Result.points.desc(), Result.avg_time.asc())
        .limit(10)
    )
    data = []
    for i, r in enumerate(rows):
        avg = None
        if r.avg_time is not None:
            try:
                avg = round(float(r.avg_time), 2)
            except Exception:
                avg = None
        data.append({
            "rank": i+1,
            "name": r.participant.name,
            "regno": r.participant.regno,
            "correct": r.correct,
            "points": r.points,
            "avg_time": avg,
        })
    return jsonify(data)

@app.route("/admin/api/delete-participant", methods=["POST"])
@require_admin
def admin_api_delete_participant():
    payload = request.get_json(silent=True) or {}
    regno = (payload.get("regno") or "").strip()
    if not regno:
        return jsonify({"success": False, "message": "regno required"}), 400
    # Try to find and delete
    p = Participant.get_or_none(Participant.regno == regno)
    if not p:
        return jsonify({"success": False, "message": "Participant not found"}), 404
    try:
        p.delete_instance(recursive=True)  # cascade delete result and answers
        return jsonify({"success": True, "message": f"Deleted {regno}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/admin/api/add-question", methods=["POST"])
@require_admin
def admin_api_add_question():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    options = data.get("options") or []
    answer = data.get("answer")
    # Basic validation
    if not question:
        return jsonify({"success": False, "message": "question required"}), 400
    if not isinstance(options, list) or len(options) < 2:
        return jsonify({"success": False, "message": "options must be a list with at least 2 items"}), 400
    if not isinstance(answer, int) or not (0 <= answer < len(options)):
        return jsonify({"success": False, "message": "answer must be a valid index"}), 400
    try:
        # Read existing
        questions = []
        if QUESTIONS_FILE.exists():
            with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
                try:
                    questions = json.load(f) or []
                except Exception:
                    questions = []
        questions.append({"question": question, "options": options, "answer": answer})
        with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)
        return jsonify({"success": True, "message": "Question added", "count": len(questions)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/admin/api/export-leaderboard")
@require_admin
def admin_api_export_leaderboard():
    # Export all leaderboard rows as CSV
    rows = (
        Result
        .select(Result, Participant)
        .join(Participant)
        .order_by(Result.points.desc(), Result.avg_time.asc())
    )
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["rank", "name", "regno", "correct", "points", "avg_time"])
    for i, r in enumerate(rows):
        avg = ""
        if r.avg_time is not None:
            try:
                avg = round(float(r.avg_time), 2)
            except Exception:
                avg = ""
        writer.writerow([i+1, r.participant.name, r.participant.regno, r.correct, r.points, avg])
    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=leaderboard.csv"}
    )

# JSON API for leaderboard, used by the SPA
@app.route("/api/leaderboard")
def leaderboard_api():
    try:
        rows = (
            Result
            .select(Result, Participant)
            .join(Participant)
            .order_by(Result.points.desc(), Result.avg_time.asc())
        )
        data = []
        for r in rows:
            avg = None
            if r.avg_time is not None:
                try:
                    avg = round(float(r.avg_time), 2)
                except Exception:
                    avg = None
            data.append({
                "name": r.participant.name,
                "regno": r.participant.regno,
                "correct": r.correct,
                "points": r.points,
                "avg_time": avg,
            })
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
