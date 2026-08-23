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


from .database import (
    engine,
    Base,
    get_db
)

from . import models


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="LiveConnect"
)


Base.metadata.create_all(
    bind=engine
)


# ============================================================
# FRONTEND PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PROJECT_DIR = BASE_DIR.parent


def get_frontend_file(
    filename: str
):

    possible_paths = [

        BASE_DIR / "frontend" / filename,

        PROJECT_DIR / "frontend" / filename

    ]


    for path in possible_paths:

        if path.exists():

            return path


    raise FileNotFoundError(
        f"Frontend file not found: {filename}"
    )


# ============================================================
# CONNECTION MANAGER
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
            f"WEBSOCKET CONNECTED: {webinar_id} "
            f"CONNECTIONS: "
            f"{len(self.connections[webinar_id])}"
        )


    def disconnect(
        self,
        websocket: WebSocket,
        webinar_id: int
    ):

        if webinar_id not in self.connections:

            return


        if websocket in self.connections[webinar_id]:

            self.connections[webinar_id].remove(
                websocket
            )


        if not self.connections[webinar_id]:

            del self.connections[webinar_id]


        print(
            f"WEBSOCKET DISCONNECTED: {webinar_id} "
            f"CONNECTIONS: "
            f"{len(self.connections.get(webinar_id, []))}"
        )


    async def broadcast(
        self,
        webinar_id: int,
        message: dict
    ):

        if webinar_id not in self.connections:

            return


        dead_connections = []


        for websocket in list(
            self.connections[webinar_id]
        ):

            try:

                await websocket.send_json(
                    message
                )

            except Exception:

                dead_connections.append(
                    websocket
                )


        for websocket in dead_connections:

            self.disconnect(
                websocket,
                webinar_id
            )


    async def send_to(
        self,
        websocket: WebSocket,
        message: dict
    ):

        try:

            await websocket.send_json(
                message
            )

        except Exception as error:

            print(
                "WEBSOCKET SEND ERROR:",
                error
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

            data = await websocket.receive_json()

            message_type = data.get(
                "type"
            )

            # =================================================
            # WEBRTC / REAL-TIME SIGNALING
            # =================================================

            if message_type == "webrtc_ready":

                role = data.get("role")

                # -------------------------------------------------
                # PARTICIPANT READY
                # -------------------------------------------------
                # When a participant's WebSocket is actually ready,
                # send that participant the current roster. Then
                # announce the ready participant to everyone.
                #
                # This is deliberately done here rather than only
                # in /webinars/join because /join happens before the
                # participant's WebSocket is connected.
                # -------------------------------------------------

                if role == "participant":

                    participant_id = data.get(
                        "participant_id"
                    )

                    db = next(
                        get_db()
                    )

                    try:

                        participant = (
                            db.query(
                                models.Participant
                            )
                            .filter(
                                models.Participant.id
                                ==
                                participant_id,

                                models.Participant.webinar_id
                                ==
                                webinar_id
                            )
                            .first()
                        )

                        if participant:

                            existing_participants = (
                                db.query(
                                    models.Participant
                                )
                                .filter(
                                    models.Participant.webinar_id
                                    ==
                                    webinar_id,

                                    models.Participant.id
                                    !=
                                    participant_id
                                )
                                .all()
                            )

                            await manager.send_to(
                                websocket,
                                {
                                    "type":
                                        "participant_roster",

                                    "participants":
                                        [
                                            {
                                                "participant_id":
                                                    item.id,

                                                "participant_name":
                                                    item.name
                                            }

                                            for item
                                            in existing_participants
                                        ]
                                }
                            )

                            await manager.broadcast(
                                webinar_id,
                                {
                                    "type":
                                        "participant_ready",

                                    "role":
                                        "participant",

                                    "participant_id":
                                        participant.id,

                                    "participant_name":
                                        participant.name
                                }
                            )

                    finally:

                        db.close()

                continue

            # -------------------------------------------------
            # ALL WEBRTC SIGNALING
            # -------------------------------------------------
            #
            # We broadcast signaling messages to the room.
            # Each browser filters messages using the target IDs.
            #
            # This allows:
            #
            # HOST <-> PARTICIPANT
            #
            # and
            #
            # PARTICIPANT <-> PARTICIPANT
            #
            # simultaneously.
            # -------------------------------------------------

            if message_type in [

                "webrtc_offer",

                "webrtc_answer",

                "webrtc_ice"

            ]:

                await manager.broadcast(
                    webinar_id,
                    data
                )

                continue

            # -------------------------------------------------
            # HOST CHAT THROUGH WEBSOCKET
            # -------------------------------------------------

            if message_type == "chat_message":

                await manager.broadcast(
                    webinar_id,
                    data
                )

                continue

    except WebSocketDisconnect:

        manager.disconnect(
            websocket,
            webinar_id
        )

    except Exception as error:

        print(
            "WEBSOCKET ERROR:",
            error
        )

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
        +
        string.digits
    )


    return "".join(

        secrets.choice(
            characters
        )

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

        "success": True,

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
            ==
            join_code

        )

        .first()

    )


    if not webinar:

        return {

            "success": False,

            "message":
                "Invalid webinar code."

        }


    if getattr(
        webinar,
        "status",
        "live"
    ) != "live":

        return {

            "success": False,

            "message":
                "This webinar has ended."

        }


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
            ==
            webinar.id

        )

        .count()

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

        "success": True,

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
            participant_count

    }


# ============================================================
# REACTION
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
            ==
            participant_id,

            models.Participant.webinar_id
            ==
            webinar_id

        )

        .first()

    )


    if not participant:

        return {

            "success": False,

            "message":
                "Participant not found."

        }


    allowed_reactions = [

        "👍",

        "👏",

        "❤️",

        "🔥"

    ]


    if reaction not in allowed_reactions:

        return {

            "success": False,

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

        "success": True,

        "message":
            "Reaction recorded."

    }


# ============================================================
# CHAT
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
            ==
            participant_id,

            models.Participant.webinar_id
            ==
            webinar_id

        )

        .first()

    )


    if not participant:

        return {

            "success": False,

            "message":
                "Participant not found."

        }


    message = message.strip()


    if not message:

        return {

            "success": False,

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

        "success": True,

        "message":
            "Chat message sent."

    }


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
            ==
            webinar_id
        )

        .first()

    )


    if not webinar:

        return {

            "success": False,

            "message":
                "Webinar not found."

        }


    question = poll.question.strip()


    options = [

        option.strip()

        for option in poll.options

        if option.strip()

    ]


    if not question:

        return {

            "success": False,

            "message":
                "Poll question is required."

        }


    if len(options) < 2:

        return {

            "success": False,

            "message":
                "At least two options are required."

        }


    new_poll = models.Poll(

        webinar_id=
            webinar_id,

        question=
            question

    )


    db.add(
        new_poll
    )


    db.commit()


    db.refresh(
        new_poll
    )


    created_options = []


    for option_text in options:

        new_option = models.PollOption(

            poll_id=
                new_poll.id,

            option_text=
                option_text

        )


        db.add(
            new_option
        )


        db.commit()


        db.refresh(
            new_option
        )


        created_options.append({

            "id":
                new_option.id,

            "option_text":
                new_option.option_text

        })


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

        "success": True,

        "poll_id":
            new_poll.id,

        "question":
            new_poll.question,

        "options":
            created_options

    }


# ============================================================
# VOTE
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
            ==
            poll_id
        )

        .first()

    )


    if not poll:

        return {

            "success": False,

            "message":
                "Poll not found."

        }


    participant = (

        db.query(
            models.Participant
        )

        .filter(

            models.Participant.id
            ==
            participant_id,

            models.Participant.webinar_id
            ==
            poll.webinar_id

        )

        .first()

    )


    if not participant:

        return {

            "success": False,

            "message":
                "Participant not found."

        }


    option = (

        db.query(
            models.PollOption
        )

        .filter(

            models.PollOption.id
            ==
            option_id,

            models.PollOption.poll_id
            ==
            poll_id

        )

        .first()

    )


    if not option:

        return {

            "success": False,

            "message":
                "Invalid poll option."

        }


    existing_vote = (

        db.query(
            models.PollVote
        )

        .filter(

            models.PollVote.poll_id
            ==
            poll_id,

            models.PollVote.participant_id
            ==
            participant_id

        )

        .first()

    )


    if existing_vote:

        return {

            "success": False,

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
            ==
            poll_id,

            models.PollVote.option_id
            ==
            option_id

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

        "success": True,

        "message":
            "Vote recorded.",

        "vote_count":
            vote_count

    }


# ============================================================
# QUESTION
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
            ==
            participant_id,

            models.Participant.webinar_id
            ==
            webinar_id

        )

        .first()

    )


    if not participant:

        return {

            "success": False,

            "message":
                "Participant not found."

        }


    question = question.strip()


    if not question:

        return {

            "success": False,

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

        "success": True,

        "message":
            "Question submitted.",

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
            ==
            question_id

        )

        .first()

    )


    if not question:

        return {

            "success": False,

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

        "success": True,

        "message":
            "Question marked as answered."

    }


# ============================================================
# POLL RESULTS
# ============================================================

@app.get(
    "/webinars/{webinar_id}/poll-results"
)
def poll_results(

    webinar_id: int,

    db: Session = Depends(get_db)

):

    polls = (

        db.query(
            models.Poll
        )

        .filter(

            models.Poll.webinar_id
            ==
            webinar_id

        )

        .all()

    )


    results = []


    for poll in polls:

        options = (

            db.query(
                models.PollOption
            )

            .filter(

                models.PollOption.poll_id
                ==
                poll.id

            )

            .all()

        )


        option_results = []


        for option in options:

            votes = (

                db.query(
                    models.PollVote
                )

                .filter(

                    models.PollVote.poll_id
                    ==
                    poll.id,

                    models.PollVote.option_id
                    ==
                    option.id

                )

                .count()

            )


            option_results.append({

                "id":
                    option.id,

                "option":
                    option.option_text,

                "votes":
                    votes

            })


        results.append({

            "poll_id":
                poll.id,

            "question":
                poll.question,

            "options":
                option_results

        })


    return {

        "polls":
            results

    }


# ============================================================
# ANALYTICS
# ============================================================

@app.get(
    "/webinars/{webinar_id}/analytics"
)
def analytics(

    webinar_id: int,

    db: Session = Depends(get_db)

):

    participants = (

        db.query(
            models.Participant
        )

        .filter(
            models.Participant.webinar_id
            ==
            webinar_id
        )

        .count()

    )


    messages = (

        db.query(
            models.Message
        )

        .filter(
            models.Message.webinar_id
            ==
            webinar_id
        )

        .count()

    )


    questions = (

        db.query(
            models.Question
        )

        .filter(
            models.Question.webinar_id
            ==
            webinar_id
        )

        .count()

    )


    reactions = (

        db.query(
            models.Reaction
        )

        .filter(
            models.Reaction.webinar_id
            ==
            webinar_id
        )

        .count()

    )


    poll_votes = (

        db.query(
            models.PollVote
        )

        .join(
            models.Poll,
            models.PollVote.poll_id
            ==
            models.Poll.id
        )

        .filter(
            models.Poll.webinar_id
            ==
            webinar_id
        )

        .count()

    )


    return {

        "webinar_id":
            webinar_id,

        "participants":
            participants,

        "peak_participants":
            participants,

        "messages":
            messages,

        "questions":
            questions,

        "reactions":
            reactions,

        "poll_responses":
            poll_votes

    }


# ============================================================
# END WEBINAR
# ============================================================

@app.post(
    "/webinars/{webinar_id}/end"
)
def end_webinar(

    webinar_id: int,

    db: Session = Depends(get_db)

):

    webinar = (

        db.query(
            models.Webinar
        )

        .filter(
            models.Webinar.id
            ==
            webinar_id
        )

        .first()

    )


    if not webinar:

        return {

            "success": False,

            "message":
                "Webinar not found."

        }


    webinar.status = "ended"


    db.commit()


    return {

        "success": True,

        "message":
            "Webinar ended."

    }


# ============================================================
# HOST PAGE
# ============================================================

@app.get(
    "/host"
)
def host_page():

    return FileResponse(

        str(
            get_frontend_file(
                "host.html"
            )
        ),

        media_type="text/html"

    )


# ============================================================
# PARTICIPANT PAGE
# ============================================================

@app.get(
    "/participant"
)
def participant_page():

    return FileResponse(

        str(
            get_frontend_file(
                "participant.html"
            )
        ),

        media_type="text/html"

    )


# ============================================================
# ANALYTICS PAGE
# ============================================================

@app.get(
    "/analytics"
)
def analytics_page():

    return FileResponse(

        str(
            get_frontend_file(
                "analytics.html"
            )
        ),

        media_type="text/html"

    )