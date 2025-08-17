import os
from dotenv import load_dotenv
from peewee import (
    Model, AutoField, CharField, IntegerField, FloatField, ForeignKeyField
)
from playhouse.db_url import connect

load_dotenv()

# Connect to the database from DB_URL (e.g., postgresql://user:pass@host/dbname)
db = connect(os.getenv("DB_URL"))


class BaseModel(Model):
    class Meta:
        database = db

class Participant(BaseModel):
    id = AutoField()
    name = CharField()
    regno = CharField(index=True, unique=True)
    college = CharField()
    dept = CharField()
    year = IntegerField()



class Result(BaseModel):
    id = AutoField()
    # Link each result to exactly one participant (one-to-one via unique FK)
    participant = ForeignKeyField(Participant, backref="result", unique=True, on_delete="CASCADE")

    correct = IntegerField(default=0)
    points = IntegerField(default=0)
    avg_time = FloatField(default=0.0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class Answer(BaseModel):
    id = AutoField()
    # Store each submitted answer under the participant's result
    result = ForeignKeyField(Result, backref="answers", on_delete="CASCADE")
    question_id = IntegerField()
    answer = IntegerField(null=True)
    time_taken = FloatField(null=True)


# Ensure tables exist on import
try:
    db.connect(reuse_if_open=True)
    # Create in dependency order
    db.create_tables([Participant, Result, Answer], safe=True)
    print("yes done")
except Exception:
    # Avoid crashing on import if migrations/permissions are pending; app can handle later
    pass
