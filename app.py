import os
from flask import Flask, render_template, request, jsonify
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

QUESTIONS_FILE = Path(__file__).parent / "questions.json"

# === Routes ===
@app.route("/")
def index():
    return render_template("index.html")

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

@app.route("/questions")
def get_questions():
    if QUESTIONS_FILE.exists():
        with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
            qs = json.load(f)
        safe = [{"id": i, "question": q["question"], "options": q["options"]} for i, q in enumerate(qs)]
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

    # Participant must be registered
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
        qid = ans.get("qId", i)
        selected = ans.get("selected", None)
        time_sec = ans.get("time_sec", None)
        if time_sec is not None:
            total_time += time_sec
            time_counts += 1
        if selected is not None and isinstance(qid, int) and 0 <= qid < len(questions):
            if selected == questions[qid].get("answer"):
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
    return render_template("leaderboard.html", board=leaderboard_data)

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
