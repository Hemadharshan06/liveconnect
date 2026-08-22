from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime

from .database import Base


class Webinar(Base):
    __tablename__ = "webinars"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    title = Column(
        String,
        nullable=False
    )

    host_name = Column(
        String,
        nullable=False
    )

    join_code = Column(
        String,
        unique=True,
        index=True,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    status = Column(
        String,
        default="live"
    )


class Participant(Base):
    __tablename__ = "participants"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String,
        nullable=False
    )

    webinar_id = Column(
        Integer,
        nullable=False
    )

    joined_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )


class Reaction(Base):
    __tablename__ = "reactions"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    participant_id = Column(
        Integer,
        nullable=False
    )

    webinar_id = Column(
        Integer,
        nullable=False
    )

    reaction = Column(
        String,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )




class Message(Base):
    __tablename__ = "messages"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    webinar_id = Column(
        Integer,
        nullable=False
    )

    participant_id = Column(
        Integer,
        nullable=False
    )

    participant_name = Column(
        String,
        nullable=False
    )

    message = Column(
        String,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )




class Poll(Base):
    __tablename__ = "polls"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    webinar_id = Column(
        Integer,
        nullable=False
    )

    question = Column(
        String,
        nullable=False
    )

    is_active = Column(
        Integer,
        default=1
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
class PollOption(Base):
    __tablename__ = "poll_options"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    poll_id = Column(
        Integer,
        nullable=False
    )

    option_text = Column(
        String,
        nullable=False
    )
class PollVote(Base):
    __tablename__ = "poll_votes"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    poll_id = Column(
        Integer,
        nullable=False
    )

    option_id = Column(
        Integer,
        nullable=False
    )

    participant_id = Column(
        Integer,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )






class Question(Base):
    __tablename__ = "questions"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    webinar_id = Column(
        Integer,
        nullable=False
    )

    participant_id = Column(
        Integer,
        nullable=False
    )

    participant_name = Column(
        String,
        nullable=False
    )

    question = Column(
        String,
        nullable=False
    )

    is_answered = Column(
        Integer,
        default=0
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    ) 
