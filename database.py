import os
from datetime import datetime

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    BigInteger,
    String,
    DateTime,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, sessionmaker


# ============================================================
# DATABASE
# ============================================================
# Никакого DATABASE_URL / PostgreSQL не требуется.
# База хранится в локальном SQLite-файле рядом с app.py.
#
# Для Render важно понимать: на бесплатном инстансе локальный
# файл может быть удалён при новом deploy/restart. Для тестов
# и текущей версии это работает без внешней БД.
# ============================================================

DATABASE_PATH = os.getenv(
    "SQLITE_DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "camp_wars.db"),
)

engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
)

Base = declarative_base()


# ============================================================
# КОМАНДЫ
# ============================================================

class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    score = Column(Integer, default=0, nullable=False)


# ============================================================
# ПОЛЬЗОВАТЕЛИ / КАПИТАНЫ
# ============================================================

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    team_id = Column(Integer, nullable=True)


# ============================================================
# ИСТОРИЯ НАЧИСЛЕНИЙ
# ============================================================

class PointsHistory(Base):
    __tablename__ = "points_history"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, nullable=False)
    team_name = Column(String(100), nullable=False)
    points = Column(Integer, nullable=False)
    new_score = Column(Integer, nullable=False)

    user_id = Column(BigInteger, nullable=False)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)

    activity = Column(String(255), nullable=True)
    result = Column(String(255), nullable=True)
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


# ============================================================
# СЕКРЕТНЫЕ МИССИИ
# ============================================================

class Mission(Base):
    __tablename__ = "missions"

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    points = Column(Integer, nullable=False)
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


# ============================================================
# ВЫДАННЫЕ МИССИИ
# ============================================================

class IssuedMission(Base):
    __tablename__ = "issued_missions"

    id = Column(Integer, primary_key=True)

    mission_id = Column(Integer, nullable=False)
    team_id = Column(Integer, nullable=False)

    issued_to_user_id = Column(BigInteger, nullable=True)

    status = Column(
        String(50),
        default="active",
        nullable=False,
    )

    issued_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    completed_at = Column(DateTime, nullable=True)

    # Одна и та же миссия не может быть выдана одной
    # команде дважды.
    __table_args__ = (
        UniqueConstraint(
            "mission_id",
            "team_id",
            name="uq_mission_team",
        ),
    )


# ============================================================
# СОЗДАНИЕ ТАБЛИЦ
# ============================================================

def init_database():
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        existing = session.query(Team).count()

        if existing == 0:
            default_names = [
                "Команда 1",
                "Команда 2",
                "Команда 3",
                "Команда 4",
                "Команда 5",
                "Команда 6",
                "Команда 7",
                "Команда 8",
                "Команда 9",
                "Команда 10",
            ]

            for name in default_names:
                session.add(
                    Team(
                        name=name,
                        score=0,
                    )
                )

            session.commit()


# ============================================================
# КОМАНДЫ
# ============================================================

def get_teams():
    with SessionLocal() as session:
        teams = (
            session.query(Team)
            .order_by(Team.id)
            .all()
        )

        return [
            {
                "id": team.id,
                "name": team.name,
                "score": team.score,
            }
            for team in teams
        ]


def get_team(team_id):
    with SessionLocal() as session:
        team = (
            session.query(Team)
            .filter(Team.id == team_id)
            .first()
        )

        if not team:
            return None

        return {
            "id": team.id,
            "name": team.name,
            "score": team.score,
        }


def rename_team(team_id, new_name):
    with SessionLocal() as session:
        team = (
            session.query(Team)
            .filter(Team.id == team_id)
            .first()
        )

        if not team:
            return None

        team.name = new_name
        session.commit()

        return {
            "id": team.id,
            "name": team.name,
            "score": team.score,
        }


# ============================================================
# НАЧИСЛЕНИЕ БАЛЛОВ
# ============================================================

def add_points(
    team_id,
    points,
    user_id,
    username=None,
    first_name=None,
    activity=None,
    result=None,
):
    with SessionLocal() as session:
        team = (
            session.query(Team)
            .filter(Team.id == team_id)
            .first()
        )

        if not team:
            return None

        team.score += points

        history = PointsHistory(
            team_id=team.id,
            team_name=team.name,
            points=points,
            new_score=team.score,
            user_id=user_id,
            username=username,
            first_name=first_name,
            activity=activity,
            result=result,
        )

        session.add(history)
        session.commit()

        return team.score


# ============================================================
# ИСТОРИЯ
# ============================================================

def get_history(limit=30):
    with SessionLocal() as session:
        rows = (
            session.query(PointsHistory)
            .order_by(PointsHistory.id.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": row.id,
                "team_id": row.team_id,
                "team_name": row.team_name,
                "points": row.points,
                "new_score": row.new_score,
                "user_id": row.user_id,
                "username": row.username,
                "first_name": row.first_name,
                "activity": row.activity,
                "result": row.result,
                "created_at": row.created_at.strftime(
                    "%d.%m %H:%M"
                ),
            }
            for row in rows
        ]


# ============================================================
# ПОЛЬЗОВАТЕЛИ
# ============================================================

def save_user(
    user_id,
    username=None,
    first_name=None,
):
    with SessionLocal() as session:
        user = (
            session.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if not user:
            user = User(
                id=user_id,
                username=username,
                first_name=first_name,
            )
            session.add(user)
        else:
            user.username = username
            user.first_name = first_name

        session.commit()


def get_user(user_id):
    with SessionLocal() as session:
        user = (
            session.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if not user:
            return None

        return {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "team_id": user.team_id,
        }


def set_user_team(user_id, team_id):
    with SessionLocal() as session:
        user = (
            session.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if not user:
            user = User(
                id=user_id,
                team_id=team_id,
            )
            session.add(user)
        else:
            user.team_id = team_id

        session.commit()


# ============================================================
# МИССИИ
# ============================================================

def create_mission(title, description, points):
    with SessionLocal() as session:
        mission = Mission(
            title=title,
            description=description,
            points=points,
        )

        session.add(mission)
        session.commit()

        return mission.id


def get_missions():
    with SessionLocal() as session:
        missions = (
            session.query(Mission)
            .order_by(Mission.id)
            .all()
        )

        return [
            {
                "id": mission.id,
                "title": mission.title,
                "description": mission.description,
                "points": mission.points,
            }
            for mission in missions
        ]


def get_mission(mission_id):
    with SessionLocal() as session:
        mission = (
            session.query(Mission)
            .filter(Mission.id == mission_id)
            .first()
        )

        if not mission:
            return None

        return {
            "id": mission.id,
            "title": mission.title,
            "description": mission.description,
            "points": mission.points,
        }


def mission_was_issued(mission_id, team_id):
    with SessionLocal() as session:
        exists = (
            session.query(IssuedMission)
            .filter(
                IssuedMission.mission_id == mission_id,
                IssuedMission.team_id == team_id,
            )
            .first()
        )

        return exists is not None


def issue_mission(mission_id, team_id, user_id=None):
    with SessionLocal() as session:
        existing = (
            session.query(IssuedMission)
            .filter(
                IssuedMission.mission_id == mission_id,
                IssuedMission.team_id == team_id,
            )
            .first()
        )

        if existing:
            return None

        issued = IssuedMission(
            mission_id=mission_id,
            team_id=team_id,
            issued_to_user_id=user_id,
            status="active",
        )

        session.add(issued)
        session.commit()

        return issued.id


def get_available_missions(team_id):
    with SessionLocal() as session:
        issued_ids = (
            session.query(IssuedMission.mission_id)
            .filter(IssuedMission.team_id == team_id)
            .all()
        )

        issued_ids = {
            item[0]
            for item in issued_ids
        }

        query = (
            session.query(Mission)
            .order_by(Mission.id)
        )

        if issued_ids:
            query = query.filter(
                ~Mission.id.in_(issued_ids)
            )

        missions = query.all()

        return [
            {
                "id": mission.id,
                "title": mission.title,
                "description": mission.description,
                "points": mission.points,
            }
            for mission in missions
        ]


def get_active_mission_for_team(team_id):
    with SessionLocal() as session:
        issued = (
            session.query(IssuedMission)
            .filter(
                IssuedMission.team_id == team_id,
                IssuedMission.status == "active",
            )
            .order_by(IssuedMission.id.desc())
            .first()
        )

        if not issued:
            return None

        mission = (
            session.query(Mission)
            .filter(Mission.id == issued.mission_id)
            .first()
        )

        if not mission:
            return None

        return {
            "issued_id": issued.id,
            "mission_id": mission.id,
            "team_id": issued.team_id,
            "title": mission.title,
            "description": mission.description,
            "points": mission.points,
            "issued_at": issued.issued_at.strftime(
                "%d.%m %H:%M"
            ),
            "status": issued.status,
        }


def get_issued_missions(limit=50):
    with SessionLocal() as session:
        rows = (
            session.query(IssuedMission)
            .order_by(IssuedMission.id.desc())
            .limit(limit)
            .all()
        )

        result = []

        for row in rows:
            mission = (
                session.query(Mission)
                .filter(Mission.id == row.mission_id)
                .first()
            )

            team = (
                session.query(Team)
                .filter(Team.id == row.team_id)
                .first()
            )

            result.append(
                {
                    "id": row.id,
                    "mission_id": row.mission_id,
                    "mission_title": (
                        mission.title
                        if mission
                        else "Удалённая миссия"
                    ),
                    "team_id": row.team_id,
                    "team_name": (
                        team.name
                        if team
                        else "Неизвестная команда"
                    ),
                    "user_id": row.issued_to_user_id,
                    "status": row.status,
                    "issued_at": row.issued_at.strftime(
                        "%d.%m %H:%M"
                    ),
                }
            )

        return result
