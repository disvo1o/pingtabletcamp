import asyncio
import html
import logging
import os
import random
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramConflictError

from database import (
    init_database,
    get_teams,
    get_team,
    rename_team,
    add_points,
    get_history,
    save_user,
    get_user,
    set_user_team,
    create_mission,
    get_missions,
    get_available_missions,
    issue_mission,
    get_active_mission_for_team,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN")

ADMIN_IDS = {128835770, 994383}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Состояние действий администраторов хранится в памяти.
# Для двух администраторов этого достаточно и не требует внешней БД.
pending_actions: dict[int, dict] = {}


MISSIONS = [
    ("Кричалка", "Придумайте командную кричалку и запишите короткое видео всей командой.", 20),
    ("Башня", "Постройте самую высокую устойчивую башню из безопасных предметов лагеря.", 25),
    ("Фото-поза", "Сделайте командное фото, где каждый участник изображает букву своего имени.", 15),
    ("Лагерный логотип", "Создайте логотип команды из подручных безопасных материалов и сфотографируйте.", 30),
    ("Синхрон", "Снимите видео, где вся команда одновременно делает одно простое движение.", 15),
    ("Реклама лагеря", "Снимите короткую весёлую рекламу вашего лагеря.", 30),
    ("Гимн", "Придумайте и исполните короткий гимн команды.", 35),
    ("Статуя", "Сделайте командную живую статую на заданную тему.", 20),
    ("Алфавит", "Составьте слово CAMP из людей, стоящих рядом.", 20),
    ("Талисман", "Придумайте талисман команды и представьте его на видео.", 25),
    ("Мем", "Придумайте лагерный мем и покажите его в безопасной сценке.", 25),
    ("Модель", "Создайте мини-модель лагерного объекта из бумаги или картона.", 30),
    ("Секунда", "Снимите видео ровно на 10 секунд с командной мини-сценкой.", 20),
    ("Поздравление", "Запишите необычное поздравление другой команде.", 15),
    ("Пантомима", "Покажите без слов известный фильм, чтобы команда капитанов угадала.", 25),
    ("Скороговорка", "Вся команда по очереди произносит одну скороговорку.", 20),
    ("Новости", "Снимите выпуск «лагерных новостей» продолжительностью до минуты.", 30),
    ("Слоган", "Придумайте слоган из пяти слов и покажите его на видео.", 20),
    ("Командный кадр", "Сделайте фото, где вся команда помещается в необычную композицию.", 20),
    ("Танец", "Придумайте безопасное короткое командное танцевальное движение.", 30),
    ("Репортаж", "Снимите репортаж о самом интересном месте лагеря.", 25),
    ("Сказка", "Перескажите известную сказку за 30 секунд.", 30),
    ("Эмодзи", "Изобразите три эмодзи одновременно всей командой.", 15),
    ("Заголовок", "Придумайте газетный заголовок про вашу команду.", 15),
    ("Киноафиша", "Создайте живую киноафишу с названием вашей команды.", 25),
    ("Роботы", "Снимите видео, где вся команда двигается как роботы.", 20),
    ("Диктор", "Запишите серьёзный дикторский текст о совершенно обычном предмете.", 20),
    ("Три слова", "Придумайте историю, используя три слова, которые выберет капитан.", 25),
    ("Смена ролей", "На видео каждый участник на 5 секунд играет роль другого участника.", 30),
    ("Зеркало", "Два участника синхронно повторяют движения друг друга.", 20),
    ("Командный алфавит", "Покажите 5 букв телами участников команды.", 30),
    ("Один кадр", "Снимите мини-фильм без остановки записи одним дублем.", 35),
    ("Песня", "Переделайте припев известной песни под CAMP WARS.", 35),
    ("Радио", "Запишите 30-секундное радиообъявление команды.", 25),
    ("Профессии", "Изобразите три профессии без слов.", 20),
    ("Замри", "Сделайте видео, где команда одновременно замирает по команде капитана.", 15),
    ("Обложка", "Создайте живую обложку музыкального альбома.", 25),
    ("Словарь", "Придумайте новое слово и объясните его значение.", 20),
    ("Дубляж", "Сделайте смешной дубляж короткой собственной сценки.", 30),
    ("Ритм", "Создайте командный ритм хлопками и повторите его синхронно.", 25),
    ("Капитан", "Капитан должен сказать речь ровно из 20 слов.", 20),
    ("Команда букв", "Постройте из участников первые три буквы названия команды.", 30),
    ("Пародия", "Сделайте добрую пародию на ведущего или телевизионный формат.", 30),
    ("Интервью", "Возьмите короткое интервью у трёх участников команды.", 25),
    ("Сюрприз", "Подготовьте безопасный визуальный сюрприз для капитанов.", 35),
    ("Квест-слово", "Составьте из бумажных букв слово CAMP и снимите результат.", 20),
    ("История", "Расскажите историю команды, используя только 5 предложений.", 25),
    ("Фото-ребус", "Создайте фото-ребус из трёх безопасных предметов.", 25),
    ("Флаг", "Создайте временный флаг команды из бумаги.", 30),
    ("Презентация", "Представьте команду как супергероев за 30 секунд.", 30),
    ("Синхронная фраза", "Вся команда одновременно произносит одну короткую фразу.", 15),
    ("Смайлик", "Изобразите большой смайлик всей командой.", 20),
    ("Турист", "Снимите сценку «турист впервые приехал в лагерь».", 25),
    ("Шпион", "Снимите шуточную сценку про секретного агента без опасных действий.", 30),
    ("Телешоу", "Создайте заставку собственного телешоу.", 30),
    ("Ведущий", "Один участник ведёт мини-шоу, остальные — гости.", 25),
    ("Микро-театр", "Поставьте сценку продолжительностью до 45 секунд.", 35),
    ("Фраза дня", "Придумайте фразу дня и произнесите её хором.", 15),
    ("Фото-история", "Расскажите историю команды в трёх фотографиях.", 30),
    ("Кроссворд", "Составьте мини-кроссворд из 5 слов про лагерь.", 30),
    ("Шифр", "Придумайте простой шифр и зашифруйте название команды.", 25),
    ("Командный портрет", "Нарисуйте общий портрет команды на бумаге.", 25),
    ("Мини-комикс", "Создайте комикс из четырёх кадров про CAMP WARS.", 30),
    ("Песня наоборот", "Придумайте смешной текст к знакомой мелодии.", 30),
    ("Три эмоции", "Покажите одну сцену с тремя разными эмоциями.", 20),
    ("Немое кино", "Снимите немую сценку продолжительностью до 30 секунд.", 30),
    ("Лагерный прогноз", "Запишите шуточный прогноз погоды для вашей команды.", 20),
    ("Премия", "Придумайте и вручите участнику шуточную командную премию.", 25),
    ("Командный девиз", "Произнесите девиз команды в трёх разных стилях.", 25),
    ("Фотограф", "Сделайте креативное фото команды с обычным предметом.", 20),
    ("Оживший предмет", "Снимите сценку, где обычный предмет становится героем.", 30),
    ("Маскот", "Нарисуйте маскота команды и представьте его.", 25),
    ("Пять кадров", "Расскажите короткую историю ровно в пяти кадрах.", 35),
    ("Капитанский дубль", "Капитан произносит мотивационную речь, команда отвечает хором.", 20),
    ("Рекламный ролик", "Продайте зрителю обычный лагерный предмет как люксовый товар.", 30),
    ("Титры", "Снимите видео с придуманными титрами участников.", 25),
    ("Карта", "Нарисуйте схематичную карту вашего лагерного пространства.", 30),
    ("Слово без буквы", "Объясните слово, не используя одну выбранную букву.", 25),
    ("Угадайка", "Придумайте три загадки для капитанов.", 25),
    ("Командная мозаика", "Сделайте узор из поз участников и сфотографируйте сверху.", 30),
    ("Стоп-кадр", "Создайте живую сцену из фильма и замрите для фото.", 20),
    ("Мини-интервью", "Каждый участник отвечает на один короткий вопрос о команде.", 25),
    ("Лагерный гимн", "Исполните короткий гимн с придуманным припевом.", 35),
    ("Буква", "Сформируйте телами одну выбранную букву.", 15),
    ("Секретный знак", "Придумайте секретный знак команды и покажите его.", 20),
    ("Фото с предметом", "Сделайте фото всей команды с одним необычным безопасным предметом.", 20),
    ("Командный жест", "Придумайте уникальный жест команды и запишите его.", 20),
    ("Финальная сцена", "Сыграйте финальную сцену воображаемого фильма о вашей команде.", 40),
    ("Лагерный трейлер", "Снимите трейлер фильма «CAMP WARS: Наша команда».", 40),
    ("Оскар", "Устройте мини-церемонию награждения внутри команды.", 30),
    ("Постер", "Создайте постер CAMP WARS из бумаги и сфотографируйте.", 30),
    ("Командная история", "Снимите историю вашей команды от начала до конца за 45 секунд.", 40),
    ("Финальный клич", "Придумайте мощный финальный клич и исполните его всей командой.", 30),
]


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Табло", callback_data="scoreboard")],
            [
                InlineKeyboardButton(text="🏅 За активность", callback_data="activity"),
                InlineKeyboardButton(text="➕ Добавить баллы", callback_data="add_points"),
            ],
            [InlineKeyboardButton(text="📜 История", callback_data="history")],
            [InlineKeyboardButton(text="✏️ Команды", callback_data="teams")],
            [InlineKeyboardButton(text="🕵️ Выдать задание", callback_data="issue_mission")],
        ]
    )


def captain_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Табло", callback_data="scoreboard")],
            [InlineKeyboardButton(text="🕵️ Моё задание", callback_data="my_mission")],
        ]
    )


def back_keyboard(callback_data: str = "admin_home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data)]
        ]
    )


async def safe_edit(
    callback: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
):
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


def seed_missions():
    # Добавляем 100 заданий только если база ещё пустая.
    existing = get_missions()
    if existing:
        return
    for title, description, points in MISSIONS:
        create_mission(title=title, description=description, points=points)
    logger.info("Добавлено %s встроенных миссий", len(MISSIONS))


def team_selection_keyboard() -> InlineKeyboardMarkup:
    teams = get_teams()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=team["name"],
                    callback_data=f"select_team:{team['id']}",
                )
            ]
            for team in teams
        ]
    )


def points_team_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=team["name"],
                callback_data=f"points_team:{team['id']}",
            )
        ]
        for team in get_teams()
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def activity_team_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=team["name"],
                callback_data=f"activity_team:{team['id']}",
            )
        ]
        for team in get_teams()
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rename_teams_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"✏️ {team['name']}",
                callback_data=f"rename:{team['id']}",
            )
        ]
        for team in get_teams()
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def scoreboard_text() -> str:
    teams = sorted(get_teams(), key=lambda x: x["score"], reverse=True)
    text = "🏆 <b>CAMP WARS — ТАБЛО</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for index, team in enumerate(teams):
        prefix = medals[index] if index < 3 else f"{index + 1}."
        text += f"{prefix} <b>{html.escape(team['name'])}</b> — {team['score']} очков\n"
    return text


@dp.message(Command("start"))
async def start_handler(message: Message):
    save_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    if is_admin(message.from_user.id):
        await message.answer(
            "👑 <b>Панель администратора CAMP WARS</b>\n\n"
            "Ты вошёл как администратор.",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )
        return

    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Ошибка регистрации. Попробуйте ещё раз.")
        return

    if not user["team_id"]:
        await message.answer(
            "🧢 <b>CAMP WARS</b>\n\nВыбери свою команду:",
            reply_markup=team_selection_keyboard(),
            parse_mode="HTML",
        )
        return

    team = get_team(user["team_id"])
    await message.answer(
        f"🧢 <b>Ты капитан команды «{html.escape(team['name'])}»</b>\n\n"
        "Здесь будут появляться ваши секретные задания.",
        reply_markup=captain_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("select_team:"))
async def select_team(callback: CallbackQuery):
    # Администратор не может использовать капитанский выбор команды.
    if is_admin(callback.from_user.id):
        await callback.answer("Эта функция доступна капитанам.", show_alert=True)
        return

    team_id = int(callback.data.split(":")[1])
    team = get_team(team_id)
    if not team:
        await callback.answer("Команда не найдена.", show_alert=True)
        return

    set_user_team(callback.from_user.id, team_id)

    await safe_edit(
        callback,
        f"🧢 <b>Команда выбрана:</b>\n«{html.escape(team['name'])}»\n\n"
        "Теперь бот сможет присылать тебе секретные задания.",
        captain_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "scoreboard")
async def scoreboard(callback: CallbackQuery):
    await safe_edit(
        callback,
        scoreboard_text(),
        admin_keyboard() if is_admin(callback.from_user.id) else captain_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "add_points")
async def add_points_start(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    pending_actions.pop(callback.from_user.id, None)
    await safe_edit(
        callback,
        "➕ <b>Добавить баллы</b>\n\nВыбери команду:",
        points_team_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("points_team:"))
async def points_team(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    team_id = int(callback.data.split(":")[1])
    team = get_team(team_id)
    if not team:
        await callback.answer("Команда не найдена.", show_alert=True)
        return

    pending_actions[callback.from_user.id] = {
        "action": "points",
        "team_id": team_id,
        "activity": False,
    }

    await safe_edit(
        callback,
        f"➕ <b>{html.escape(team['name'])}</b>\n\n"
        "Теперь отправь мне количество баллов числом.\n\n"
        "Например:\n<code>150</code>\n<code>-50</code>",
    )
    await callback.answer()


@dp.callback_query(F.data == "activity")
async def activity_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    pending_actions.pop(callback.from_user.id, None)
    await safe_edit(
        callback,
        "🏅 <b>За активность</b>\n\nВыбери команду:",
        activity_team_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("activity_team:"))
async def activity_team(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    team_id = int(callback.data.split(":")[1])
    team = get_team(team_id)
    if not team:
        await callback.answer("Команда не найдена.", show_alert=True)
        return

    pending_actions[callback.from_user.id] = {
        "action": "points",
        "team_id": team_id,
        "activity": True,
    }

    await safe_edit(
        callback,
        f"🏅 <b>{html.escape(team['name'])}</b>\n\n"
        "Отправь количество баллов за активность числом.\n\n"
        "Например: <code>50</code>",
    )
    await callback.answer()


@dp.callback_query(F.data == "history")
async def history_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    history = get_history(limit=30)
    if not history:
        text = "📜 <b>История пока пустая.</b>"
    else:
        text = "📜 <b>Последние изменения</b>\n\n"
        for row in history:
            sign = "+" if row["points"] >= 0 else ""
            username = f"@{row['username']}" if row["username"] else row["first_name"]
            activity = f" — {row['activity']}" if row["activity"] else ""
            text += (
                f"🕐 {row['created_at']}\n"
                f"🏆 {html.escape(row['team_name'])}: "
                f"<b>{sign}{row['points']}</b>\n"
                f"👤 {html.escape(username or 'без username')}{html.escape(activity)}\n\n"
            )

    await safe_edit(callback, text, admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "teams")
async def teams_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    text = "✏️ <b>Команды</b>\n\n"
    for team in get_teams():
        text += (
            f"{team['id']}. {html.escape(team['name'])} — "
            f"{team['score']} очков\n"
        )

    await safe_edit(callback, text, rename_teams_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("rename:"))
async def rename_start(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    team_id = int(callback.data.split(":")[1])
    team = get_team(team_id)
    if not team:
        await callback.answer("Команда не найдена.", show_alert=True)
        return

    pending_actions[callback.from_user.id] = {
        "action": "rename",
        "team_id": team_id,
    }

    await safe_edit(
        callback,
        f"✏️ Команда: <b>{html.escape(team['name'])}</b>\n\n"
        "Отправь новое название:",
    )
    await callback.answer()


@dp.callback_query(F.data == "issue_mission")
async def issue_mission_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    teams = get_teams()
    if not teams:
        await callback.answer("Команд пока нет.", show_alert=True)
        return

    # Получаем капитанов/пользователей, которые выбрали команду.
    # Для каждой команды берём первого зарегистрированного пользователя.
    from database import SessionLocal, User

    with SessionLocal() as session:
        captain_by_team = {}
        users = session.query(User).filter(User.team_id.isnot(None)).all()
        for user in users:
            captain_by_team.setdefault(user.team_id, user)

    sent = 0
    failed = 0
    no_captain = 0

    # Не выдаём одной команде уже полученное ранее задание.
    for team in teams:
        available = get_available_missions(team["id"])
        if not available:
            failed += 1
            continue

        captain = captain_by_team.get(team["id"])
        if not captain:
            no_captain += 1
            continue

        mission = random.choice(available)

        # Сначала фиксируем выдачу в БД. Уникальный индекс не позволит
        # повторить эту же миссию этой же команде.
        issue_mission(
            mission_id=mission["id"],
            team_id=team["id"],
            user_id=captain.id,
        )

        text = (
            "🕵️ <b>СЕКРЕТНОЕ ЗАДАНИЕ</b>\n\n"
            f"<b>{html.escape(mission['title'])}</b>\n\n"
            f"{html.escape(mission['description'])}\n\n"
            f"🏆 Награда: <b>+{mission['points']} очков</b>\n\n"
            "📸 <b>Важно:</b> доказательство выполнения необходимо "
            "прислать в <b>чат капитанов</b>.\n\n"
            "🤫 Не рассказывайте другим командам о своём задании."
        )

        try:
            await bot.send_message(captain.id, text, parse_mode="HTML")
            sent += 1
        except Exception as e:
            logger.exception(
                "Не удалось отправить миссию капитану %s: %s",
                captain.id,
                e,
            )
            failed += 1

    result = (
        "🕵️ <b>Задания выданы</b>\n\n"
        f"📨 Отправлено: <b>{sent}</b>\n"
        f"⚠️ Не отправлено: <b>{failed}</b>\n"
        f"🧢 Без зарегистрированного капитана: <b>{no_captain}</b>\n\n"
        "Если капитан не получил сообщение, он должен сначала "
        "нажать /start в личке с ботом."
    )

    await callback.message.answer(result, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "my_mission")
async def my_mission_handler(callback: CallbackQuery):
    if is_admin(callback.from_user.id):
        await callback.answer("Эта кнопка доступна капитанам.", show_alert=True)
        return

    user = get_user(callback.from_user.id)
    if not user or not user["team_id"]:
        await callback.answer("Сначала выбери команду.", show_alert=True)
        return

    mission = get_active_mission_for_team(user["team_id"])
    if not mission:
        await callback.message.answer(
            "🕵️ Сейчас у вашей команды нет активного задания."
        )
        await callback.answer()
        return

    text = (
        "🕵️ <b>ВАШЕ СЕКРЕТНОЕ ЗАДАНИЕ</b>\n\n"
        f"<b>{html.escape(mission['title'])}</b>\n\n"
        f"{html.escape(mission['description'])}\n\n"
        f"🏆 Награда: <b>+{mission['points']} очков</b>\n\n"
        "📸 <b>Доказательство выполнения пришлите в чат капитанов.</b>"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "admin_home")
async def admin_home(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    pending_actions.pop(callback.from_user.id, None)
    await safe_edit(
        callback,
        "👑 <b>Панель администратора CAMP WARS</b>",
        admin_keyboard(),
    )
    await callback.answer()


@dp.message()
async def text_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    action = pending_actions.get(message.from_user.id)
    if not action:
        return

    text = (message.text or "").strip()
    if not text:
        return

    if action["action"] == "rename":
        new_name = text
        if len(new_name) > 50:
            await message.answer("Название слишком длинное. Максимум 50 символов.")
            return

        rename_team(action["team_id"], new_name)
        pending_actions.pop(message.from_user.id, None)

        await message.answer(
            f"✅ <b>Команда переименована:</b>\n\n"
            f"<b>{html.escape(new_name)}</b>",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )
        return

    if action["action"] == "points":
        if not text.lstrip("-").isdigit():
            await message.answer(
                "❗ Отправь только число, например <code>50</code> или <code>-20</code>.",
                parse_mode="HTML",
            )
            return

        points = int(text)
        team = get_team(action["team_id"])
        if not team:
            pending_actions.pop(message.from_user.id, None)
            await message.answer("Команда не найдена.")
            return

        activity = "За активность" if action.get("activity") else "Ручное начисление"

        new_score = add_points(
            team_id=action["team_id"],
            points=points,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            activity=activity,
        )

        pending_actions.pop(message.from_user.id, None)

        sign = "+" if points >= 0 else ""
        await message.answer(
            f"✅ <b>Баллы добавлены</b>\n\n"
            f"Команда: <b>{html.escape(team['name'])}</b>\n"
            f"Причина: <b>{activity}</b>\n"
            f"Изменение: <b>{sign}{points}</b>\n"
            f"Новый счёт: <b>{new_score}</b>",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )


async def main():
    init_database()
    seed_missions()

    logger.info("CAMP WARS bot started")
    try:
        await dp.start_polling(bot)
    except TelegramConflictError:
        logger.error(
            "TelegramConflictError: этот BOT_TOKEN уже используется другим "
            "процессом. Оставь только один запущенный экземпляр бота."
        )
        raise


if __name__ == "__main__":
    asyncio.run(main())
