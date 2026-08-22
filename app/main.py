from fastapi import (
    FastAPI,
    Depends,
    Form,
    WebSocket,
    WebSocketDisconnect
)

from fastapi.responses import FileResponse

from sqlalchemy.orm import Session

from pydantic import BaseModel

from pathlib import Path

import secrets
import string

from .database import engine, Base, get_db
from . import models


app = FastAPI(
    title="LiveConnect"
)


Base.metadata.create_all(
    bind=engine
)


# ============================================================
# FRONTEND FILE LOCATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PROJECT_DIR = BASE_DIR.parent


def get_frontend_file(filename: str):

    possible_paths = [

        # Frontend inside app folder
        BASE_DIR / "frontend" / filename,

        # Frontend beside app folder
        PROJECT_DIR / "frontend" / filename

    ]


    for file_path in possible_paths:

        if file_path.exists():

            return file_path


    raise FileNotFoundError(
        f"Frontend file not found: {filename}"
    )


# ============================================================
# WEBSOCKET CONNECTION MANAGER
# ============================================================

class ConnectionManager:

    def __init__(self):

        self.connections = {}


    async def connect(
        self,
        websocket: WebSocket,
        webinar_id: int
    ):

        await websocket.accept()


        if webinar_id not in self.connections:

            self.connections[webinar_id] = []


        if websocket not in self.connections[webinar_id]:

            self.connections[webinar_id].append(
                websocket
            )


        print(
            "WEBSOCKET CONNECTED:",
            webinar_id,
            "CONNECTIONS:",
            len(
                self.connections.get(
                    webinar_id,
                    []
                )
            )
        )


    def disconnect(
        self,
        websocket: WebSocket,
        webinar_id: int
    ):

        if webinar_id in self.connections:

            if websocket in self.connections[webinar_id]:

                self.connections[webinar_id].remove(
                    websocket
                )


            if not self.connections[webinar_id]:

                del self.connections[webinar_id]


        print(
            "WEBSOCKET DISCONNECTED:",
            webinar_id,
            "CONNECTIONS:",
            len(
                self.connections.get(
                    webinar_id,
                    []
                )
            )
        )


    async def broadcast(
        self,
        webinar_id: int,
        message: dict
    ):

        if webinar_id not in self.connections:

            print(
                "NO CONNECTIONS FOR WEBINAR:",
                webinar_id
            )

            return


        print(
            "BROADCASTING TO:",
            webinar_id,
            "CONNECTIONS:",
            len(
                self.connections[webinar_id]
            )
        )


        for websocket in list(
            self.connections[webinar_id]
        ):

            try:

                await websocket.send_json(
                    message
                )

            except Exception:

                self.disconnect(
                    websocket,
                    webinar_id
                )


manager = ConnectionManager()


# ============================================================
# HOME
# ============================================================

@app.get("/")
def home():

    return {
        "message": "LiveConnect is running!"
    }


# ============================================================
# WEBSOCKET
# ============================================================

@app.websocket(
    "/ws/{webinar_id}"
)
async def websocket_endpoint(
    websocket: WebSocket,
    webinar_id: int
):

    await manager.connect(
        websocket,
        webinar_id
    )


    try:

        while True:

            await websocket.receive_text()


    except WebSocketDisconnect:

        manager.disconnect(
            websocket,
            webinar_id
        )


# ============================================================
# GENERATE JOIN CODE
# ============================================================

def generate_join_code():

    characters = (
        string.ascii_uppercase
        + string.digits
    )


    return "".join(
        secrets.choice(characters)
        for _ in range(6)
    )


# ============================================================
# CREATE WEBINAR
# ============================================================

@app.post(
    "/webinars"
)
def create_webinar(

    title: str = Form(...),

    host_name: str = Form(...),

    db: Session = Depends(get_db)

):

    join_code = generate_join_code()


    webinar = models.Webinar(

        title=title,

        host_name=host_name,

        join_code=join_code

    )


    db.add(
        webinar
    )


    db.commit()


    db.refresh(
        webinar
    )


    return {

        "message":
            "Webinar created successfully!",

        "webinar_id":
            webinar.id,

        "title":
            webinar.title,

        "host_name":
            webinar.host_name,

        "join_code":
            webinar.join_code,

        "status":
            webinar.status

    }


# ============================================================
# JOIN WEBINAR
# ============================================================

@app.post(
    "/webinars/join"
)
async def join_webinar(

    name: str = Form(...),

    join_code: str = Form(...),

    db: Session = Depends(get_db)

):

    name = name.strip()

    join_code = join_code.strip().upper()


    webinar = (

        db.query(
            models.Webinar
        )

        .filter(
            models.Webinar.join_code
            == join_code
        )

        .first()

    )


    if not webinar:

        return {

            "success":
                False,

            "message":
                "Invalid webinar code."

        }


    # --------------------------------------------------------
    # CHECK EXISTING PARTICIPANT
    # --------------------------------------------------------

    existing_participant = (

        db.query(
            models.Participant
        )

        .filter(

            models.Participant.name
            == name,

            models.Participant.webinar_id
            == webinar.id

        )

        .first()

    )


    # ========================================================
    # EXISTING PARTICIPANT
    # ========================================================

    if existing_participant:

        participant_count = (

            db.query(
                models.Participant
            )

            .filter(

                models.Participant.webinar_id
                == webinar.id

            )

            .count()

        )


        print(
            "PARTICIPANT ALREADY EXISTS:",
            webinar.id,
            existing_participant.name,
            participant_count
        )


        # IMPORTANT:
        # Broadcast the participant name even when the
        # participant already exists in the database.

        await manager.broadcast(

            webinar.id,

            {

                "type":
                    "participant_joined",

                "participant_id":
                    existing_participant.id,

                "participant_name":
                    existing_participant.name,

                "participant_count":
                    participant_count

            }

        )


        return {

            "success":
                True,

            "message":
                "Already joined this webinar.",

            "participant_id":
                existing_participant.id,

            "participant_name":
                existing_participant.name,

            "webinar_id":
                webinar.id,

            "webinar_title":
                webinar.title,

            "join_code":
                webinar.join_code,

            "participant_count":
                participant_count,

            "already_joined":
                True

        }


    # ========================================================
    # NEW PARTICIPANT
    # ========================================================

    participant = models.Participant(

        name=name,

        webinar_id=webinar.id

    )


    db.add(
        participant
    )


    db.commit()


    db.refresh(
        participant
    )


    participant_count = (

        db.query(
            models.Participant
        )

        .filter(

            models.Participant.webinar_id
            == webinar.id

        )

        .count()

    )


    print(
        "BROADCASTING PARTICIPANT JOIN:",
        webinar.id,
        participant.name,
        participant_count,
        len(
            manager.connections.get(
                webinar.id,
                []
            )
        )
    )


    await manager.broadcast(

        webinar.id,

        {

            "type":
                "participant_joined",

            "participant_id":
                participant.id,

            "participant_name":
                participant.name,

            "participant_count":
                participant_count

        }

    )


    return {

        "success":
            True,

        "message":
            "Successfully joined the webinar!",

        "participant_id":
            participant.id,

        "participant_name":
            participant.name,

        "webinar_id":
            webinar.id,

        "webinar_title":
            webinar.title,

        "join_code":
            webinar.join_code,

        "participant_count":
            participant_count,

        "already_joined":
            False

    }


# ============================================================
# SEND REACTION
# ============================================================

@app.post(
    "/webinars/{webinar_id}/react"
)
async def send_reaction(

    webinar_id: int,

    participant_id: int,

    reaction: str,

    db: Session = Depends(get_db)

):

    participant = (

        db.query(
            models.Participant
        )

        .filter(

            models.Participant.id
            == participant_id,

            models.Participant.webinar_id
            == webinar_id

        )

        .first()

    )


    if not participant:

        return {

            "success":
                False,

            "message":
                "Participant not found in this webinar."

        }


    allowed_reactions = [

        "👍",
        "👏",
        "❤️",
        "🔥"

    ]


    if reaction not in allowed_reactions:

        return {

            "success":
                False,

            "message":
                "Invalid reaction."

        }


    new_reaction = models.Reaction(

        participant_id=
            participant_id,

        webinar_id=
            webinar_id,

        reaction=
            reaction

    )


    db.add(
        new_reaction
    )


    db.commit()


    db.refresh(
        new_reaction
    )


    await manager.broadcast(

        webinar_id,

        {

            "type":
                "reaction",

            "reaction":
                reaction,

            "participant_id":
                participant_id,

            "participant_name":
                participant.name

        }

    )


    return {

        "success":
            True,

        "message":
            "Reaction recorded!",

        "reaction":
            reaction

    }


# ============================================================
# SEND CHAT MESSAGE
# ============================================================

@app.post(
    "/webinars/{webinar_id}/chat"
)
async def send_chat_message(

    webinar_id: int,

    participant_id: int,

    message: str,

    db: Session = Depends(get_db)

):

    participant = (

        db.query(
            models.Participant
        )

        .filter(

            models.Participant.id
            == participant_id,

            models.Participant.webinar_id
            == webinar_id

        )

        .first()

    )


    if not participant:

        return {

            "success":
                False,

            "message":
                "Participant not found in this webinar."

        }


    message = message.strip()


    if not message:

        return {

            "success":
                False,

            "message":
                "Message cannot be empty."

        }


    new_message = models.Message(

        webinar_id=
            webinar_id,

        participant_id=
            participant_id,

        participant_name=
            participant.name,

        message=
            message

    )


    db.add(
        new_message
    )


    db.commit()


    db.refresh(
        new_message
    )


    await manager.broadcast(

        webinar_id,

        {

            "type":
                "chat_message",

            "participant_name":
                participant.name,

            "message":
                message

        }

    )


    return {

        "success":
            True,

        "message":
            "Chat message sent!"

    }


# ============================================================
# HOST PAGE
# ============================================================

@app.get(
    "/host"
)
def host_page():

    html_file = get_frontend_file(
        "host.html"
    )


    print(
        "HOST HTML:",
        html_file
    )


    return FileResponse(
        str(html_file),
        media_type="text/html"
    )


# ============================================================
# PARTICIPANT PAGE
# ============================================================

@app.get(
    "/participant"
)
def participant_page():

    html_file = get_frontend_file(
        "participant.html"
    )


    print(
        "PARTICIPANT HTML:",
        html_file
    )


    return FileResponse(
        str(html_file),
        media_type="text/html"
    )


# ============================================================
# POLL SCHEMA
# ============================================================

class PollCreate(BaseModel):

    question: str

    options: list[str]


# ============================================================
# CREATE POLL
# ============================================================

@app.post(
    "/webinars/{webinar_id}/polls"
)
async def create_poll(

    webinar_id: int,

    poll: PollCreate,

    db: Session = Depends(get_db)

):

    webinar = (

        db.query(
            models.Webinar
        )

        .filter(
            models.Webinar.id
            == webinar_id
        )

        .first()

    )


    if not webinar:

        return {

            "success":
                False,

            "message":
                "Webinar not found."

        }


    new_poll = models.Poll(

        webinar_id=
            webinar_id,

        question=
            poll.question

    )


    db.add(
        new_poll
    )


    db.commit()


    db.refresh(
        new_poll
    )


    created_options = []


    for option in poll.options:

        new_option = models.PollOption(

            poll_id=
                new_poll.id,

            option_text=
                option

        )


        db.add(
            new_option
        )


        db.commit()


        db.refresh(
            new_option
        )


        created_options.append(

            {

                "id":
                    new_option.id,

                "option_text":
                    new_option.option_text

            }

        )


    await manager.broadcast(

        webinar_id,

        {

            "type":
                "poll_created",

            "poll_id":
                new_poll.id,

            "question":
                new_poll.question,

            "options":
                created_options

        }

    )


    return {

        "success":
            True,

        "message":
            "Poll created successfully!",

        "poll_id":
            new_poll.id,

        "question":
            new_poll.question,

        "options":
            created_options

    }


# ============================================================
# VOTE IN POLL
# ============================================================

@app.post(
    "/polls/{poll_id}/vote"
)
async def vote_poll(

    poll_id: int,

    option_id: int,

    participant_id: int,

    db: Session = Depends(get_db)

):

    poll = (

        db.query(
            models.Poll
        )

        .filter(
            models.Poll.id
            == poll_id
        )

        .first()

    )


    if not poll:

        return {

            "success":
                False,

            "message":
                "Poll not found."

        }


    participant = (

        db.query(
            models.Participant
        )

        .filter(

            models.Participant.id
            == participant_id,

            models.Participant.webinar_id
            == poll.webinar_id

        )

        .first()

    )


    if not participant:

        return {

            "success":
                False,

            "message":
                "Participant not found."

        }


    option = (

        db.query(
            models.PollOption
        )

        .filter(

            models.PollOption.id
            == option_id,

            models.PollOption.poll_id
            == poll_id

        )

        .first()

    )


    if not option:

        return {

            "success":
                False,

            "message":
                "Poll option not found."

        }


    existing_vote = (

        db.query(
            models.PollVote
        )

        .filter(

            models.PollVote.poll_id
            == poll_id,

            models.PollVote.participant_id
            == participant_id

        )

        .first()

    )


    if existing_vote:

        return {

            "success":
                False,

            "message":
                "You have already voted."

        }


    vote = models.PollVote(

        poll_id=
            poll_id,

        option_id=
            option_id,

        participant_id=
            participant_id

    )


    db.add(
        vote
    )


    db.commit()


    vote_count = (

        db.query(
            models.PollVote
        )

        .filter(

            models.PollVote.poll_id
            == poll_id,

            models.PollVote.option_id
            == option_id

        )

        .count()

    )


    await manager.broadcast(

        poll.webinar_id,

        {

            "type":
                "poll_vote",

            "poll_id":
                poll_id,

            "option_id":
                option_id,

            "vote_count":
                vote_count,

            "participant_name":
                participant.name

        }

    )


    return {

        "success":
            True,

        "message":
            "Vote recorded!",

        "poll_id":
            poll_id,

        "option_id":
            option_id,

        "vote_count":
            vote_count

    }


# ============================================================
# ASK QUESTION
# ============================================================

@app.post(
    "/webinars/{webinar_id}/questions"
)
async def ask_question(

    webinar_id: int,

    participant_id: int,

    question: str,

    db: Session = Depends(get_db)

):

    participant = (

        db.query(
            models.Participant
        )

        .filter(

            models.Participant.id
            == participant_id,

            models.Participant.webinar_id
            == webinar_id

        )

        .first()

    )


    if not participant:

        return {

            "success":
                False,

            "message":
                "Participant not found."

        }


    question = question.strip()


    if not question:

        return {

            "success":
                False,

            "message":
                "Question cannot be empty."

        }


    new_question = models.Question(

        webinar_id=
            webinar_id,

        participant_id=
            participant_id,

        participant_name=
            participant.name,

        question=
            question

    )


    db.add(
        new_question
    )


    db.commit()


    db.refresh(
        new_question
    )


    await manager.broadcast(

        webinar_id,

        {

            "type":
                "question",

            "question_id":
                new_question.id,

            "participant_name":
                participant.name,

            "question":
                question

        }

    )


    return {

        "success":
            True,

        "message":
            "Question submitted!",

        "question_id":
            new_question.id

    }


# ============================================================
# ANSWER QUESTION
# ============================================================

@app.post(
    "/questions/{question_id}/answer"
)
async def answer_question(

    question_id: int,

    db: Session = Depends(get_db)

):

    question = (

        db.query(
            models.Question
        )

        .filter(
            models.Question.id
            == question_id
        )

        .first()

    )


    if not question:

        return {

            "success":
                False,

            "message":
                "Question not found."

        }


    question.is_answered = 1


    db.commit()


    await manager.broadcast(

        question.webinar_id,

        {

            "type":
                "question_answered",

            "question_id":
                question_id

        }

    )


    return {

        "success":
            True,

        "message":
            "Question marked as answered!",

        "question_id":
            question_id

    }


# ============================================================
# ANALYTICS
# ============================================================

@app.get(
    "/webinars/{webinar_id}/analytics"
)
def get_webinar_analytics(

    webinar_id: int,

    db: Session = Depends(get_db)

):

    participant_count = (

        db.query(
            models.Participant
        )

        .filter(
            models.Participant.webinar_id
            == webinar_id
        )

        .count()

    )


    message_count = (

        db.query(
            models.Message
        )

        .filter(
            models.Message.webinar_id
            == webinar_id
        )

        .count()

    )


    question_count = (

        db.query(
            models.Question
        )

        .filter(
            models.Question.webinar_id
            == webinar_id
        )

        .count()

    )


    poll_response_count = (

        db.query(
            models.PollVote
        )

        .join(

            models.Poll,

            models.PollVote.poll_id
            == models.Poll.id

        )

        .filter(

            models.Poll.webinar_id
            == webinar_id

        )

        .count()

    )


    reaction_count = (

        db.query(
            models.Reaction
        )

        .filter(

            models.Reaction.webinar_id
            == webinar_id

        )

        .count()

    )


    return {

        "webinar_id":
            webinar_id,

        "participants":
            participant_count,

        "peak_participants":
            participant_count,

        "messages":
            message_count,

        "questions":
            question_count,

        "poll_responses":
            poll_response_count,

        "reactions":
            reaction_count

    }


# ============================================================
# POLL RESULTS
# ============================================================

@app.get(
    "/webinars/{webinar_id}/poll-results"
)
def get_poll_results(

    webinar_id: int,

    db: Session = Depends(get_db)

):

    polls = (

        db.query(
            models.Poll
        )

        .filter(
            models.Poll.webinar_id
            == webinar_id
        )

        .all()

    )


    poll_results = []


    for poll in polls:


        options = (

            db.query(
                models.PollOption
            )

            .filter(

                models.PollOption.poll_id
                == poll.id

            )

            .all()

        )


        option_results = []


        for option in options:


            vote_count = (

                db.query(
                    models.PollVote
                )

                .filter(

                    models.PollVote.poll_id
                    == poll.id,

                    models.PollVote.option_id
                    == option.id

                )

                .count()

            )


            option_results.append(

                {

                    "id":
                        option.id,

                    "option":
                        option.option_text,

                    "votes":
                        vote_count

                }

            )


        poll_results.append(

            {

                "poll_id":
                    poll.id,

                "question":
                    poll.question,

                "options":
                    option_results

            }

        )


    return {

        "webinar_id":
            webinar_id,

        "polls":
            poll_results

    }


# ============================================================
# ANALYTICS PAGE
# ============================================================

@app.get(
    "/analytics"
)
def analytics_page():

    html_file = get_frontend_file(
        "analytics.html"
    )


    print(
        "ANALYTICS HTML:",
        html_file
    )


    return FileResponse(
        str(html_file),
        media_type="text/html"
    )
