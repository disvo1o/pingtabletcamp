import asyncio
import html
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramBadRequest, TelegramConflictError

from database import (
    init_database,
    get_teams,
    get_team,
    rename_team,
    add_points,
    get_history,
    save_user,
    get_scoreboard_config,
    save_scoreboard_config,
    delete_scoreboard_config,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN")


# =========================================================
# АДМИНИСТРАТОРЫ
# =========================================================

ADMIN_IDS = {
    128835770,
    994383,
}


# =========================================================
# НАСТРОЙКИ
# =========================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# Временное состояние действий администраторов.
# Внешняя база для этого не нужна.
pending_actions = {}

# Один общий lock не даёт двум администраторам одновременно
# редактировать одно и то же закреплённое сообщение рейтинга.
scoreboard_lock = asyncio.Lock()


# =========================================================
# ПРОВЕРКА АДМИНИСТРАТОРА
# =========================================================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def clear_action(user_id: int):
    pending_actions.pop(user_id, None)


# =========================================================
# КЛАВИАТУРА АДМИНИСТРАТОРА
# =========================================================

def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить баллы",
                    callback_data="add_points",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Общий рейтинг",
                    callback_data="scoreboard",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 История изменения баллов",
                    callback_data="history",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Команды",
                    callback_data="teams",
                )
            ],
        ]
    )


# =========================================================
# КЛАВИАТУРА ОБЫЧНОГО ПОЛЬЗОВАТЕЛЯ
# =========================================================

def user_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏆 Общий рейтинг",
                    callback_data="scoreboard",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 История изменения баллов",
                    callback_data="history",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Команды",
                    callback_data="teams",
                )
            ],
        ]
    )


# =========================================================
# КНОПКА НАЗАД
# =========================================================

def back_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="home",
                )
            ]
        ]
    )


# =========================================================
# ВЫБОР КОМАНДЫ ДЛЯ НАЧИСЛЕНИЯ
# =========================================================

def points_teams_keyboard():
    rows = []

    for team in get_teams():
        rows.append(
            [
                InlineKeyboardButton(
                    text=team["name"],
                    callback_data=f"points_team:{team['id']}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="home",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


# =========================================================
# ДЕЙСТВИЯ С БАЛЛАМИ
# =========================================================

def points_actions_keyboard(team_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏆 Победа +100",
                    callback_data=f"win:{team_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Ввести баллы",
                    callback_data=f"custom_points:{team_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Выбрать другую команду",
                    callback_data="add_points",
                )
            ],
        ]
    )


# =========================================================
# КЛАВИАТУРА ПЕРЕИМЕНОВАНИЯ
# =========================================================

def rename_keyboard():
    rows = []

    for team in get_teams():
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {team['name']}",
                    callback_data=f"rename:{team['id']}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="home",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


# =========================================================
# БЕЗОПАСНОЕ РЕДАКТИРОВАНИЕ СООБЩЕНИЯ
# =========================================================

async def safe_edit(
    callback: CallbackQuery,
    text: str,
    keyboard=None,
):
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    except TelegramBadRequest as e:

        # Если сообщение уже содержит тот же текст и кнопки,
        # Telegram возвращает "message is not modified".
        if "message is not modified" not in str(e).lower():
            raise


# =========================================================
# ПУБЛИЧНЫЙ ЗАКРЕПЛЁННЫЙ РЕЙТИНГ
# =========================================================

def build_scoreboard_text():
    teams = sorted(
        get_teams(),
        key=lambda team: team["score"],
        reverse=True,
    )

    text = "🏆 <b>ОБЩИЙ РЕЙТИНГ пинг таблет кэмп</b>\\n\\n"

    medals = [
        "🥇",
        "🥈",
        "🥉",
    ]

    for index, team in enumerate(teams):
        if index < 3:
            prefix = medals[index]
        else:
            prefix = f"{index + 1}."

        text += (
            f"{prefix} "
            f"<b>{html.escape(team['name'])}</b>"
            f" — {team['score']} баллов\\n"
        )

    return text


async def update_pinned_scoreboard():
    async with scoreboard_lock:
        config = get_scoreboard_config()

        if not config:
            return

        text = build_scoreboard_text()

        try:
            await bot.edit_message_text(
                chat_id=config["chat_id"],
                message_id=config["message_id"],
                text=text,
                parse_mode="HTML",
            )

        except TelegramBadRequest as e:
            error_text = str(e).lower()

            if "message is not modified" in error_text:
                return

            if (
                "message to edit not found" in error_text
                or "message can't be edited" in error_text
                or "message identifier is not specified" in error_text
            ):
                delete_scoreboard_config()

                logger.warning(
                    "Закреплённое сообщение рейтинга больше недоступно. "
                    "Запусти /setup_scoreboard заново."
                )

                return

            raise


# =========================================================
# НАСТРОЙКА ЗАКРЕПЛЁННОГО РЕЙТИНГА
# =========================================================

@dp.message(Command("setup_scoreboard"))
async def setup_scoreboard_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    if message.chat.type not in ("group", "supergroup"):
        await message.answer(
            "❌ Эту команду нужно выполнить в целевом групповом чате."
        )
        return

    text = build_scoreboard_text()

    try:
        old_config = get_scoreboard_config()

        # Если рейтинг уже настроен и старое сообщение существует,
        # просто обновляем и закрепляем его повторно.
        if old_config:
            try:
                await bot.edit_message_text(
                    chat_id=old_config["chat_id"],
                    message_id=old_config["message_id"],
                    text=text,
                    parse_mode="HTML",
                )

                await bot.pin_chat_message(
                    chat_id=old_config["chat_id"],
                    message_id=old_config["message_id"],
                    disable_notification=True,
                )

                if (
                    old_config["chat_id"] == message.chat.id
                ):
                    await message.answer(
                        "✅ Закреплённый рейтинг уже настроен и обновлён."
                    )
                    return

            except TelegramBadRequest:
                delete_scoreboard_config()

        scoreboard_message = await message.answer(
            text,
            parse_mode="HTML",
        )

        await bot.pin_chat_message(
            chat_id=message.chat.id,
            message_id=scoreboard_message.message_id,
            disable_notification=True,
        )

        save_scoreboard_config(
            chat_id=message.chat.id,
            message_id=scoreboard_message.message_id,
        )

        await message.answer(
            "✅ <b>Публичный рейтинг настроен.</b>\\n\\n"
            "Это сообщение теперь будет автоматически "
            "обновляться после изменения баллов.",
            parse_mode="HTML",
        )

    except TelegramBadRequest as e:
        logger.exception(
            "Не удалось настроить публичный рейтинг: %s",
            e,
        )

        await message.answer(
            "❌ Не удалось закрепить рейтинг.\\n\\n"
            "Проверь, что бот является администратором этого чата "
            "и имеет право закреплять сообщения."
        )


# =========================================================
# ГЛАВНЫЙ ЭКРАН
# =========================================================

def home_text():
    return (
        "🎯 <b>CAMP WARS</b>\n\n"
        "Выбери нужный раздел:"
    )


# =========================================================
# START
# =========================================================

@dp.message(Command("start"))
async def start_handler(message: Message):

    # Регистрируем пользователя в базе.
    save_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    clear_action(message.from_user.id)

    # Администратор
    if is_admin(message.from_user.id):

        await message.answer(
            "👑 <b>Панель администратора пинг таблем кэмп</b>\n\n"
            "Выбери действие:",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )

    # Обычный пользователь
    else:

        await message.answer(
            home_text(),
            reply_markup=user_keyboard(),
            parse_mode="HTML",
        )


# =========================================================
# ГЛАВНОЕ МЕНЮ
# =========================================================

@dp.callback_query(F.data == "home")
async def home_handler(callback: CallbackQuery):

    clear_action(callback.from_user.id)

    if is_admin(callback.from_user.id):

        text = (
            "👑 <b>Панель администратора пинг таблет кэмп</b>\n\n"
            "Выбери действие:"
        )

        keyboard = admin_keyboard()

    else:

        text = home_text()
        keyboard = user_keyboard()

    await safe_edit(
        callback,
        text,
        keyboard,
    )

    await callback.answer()


# =========================================================
# 1. ДОБАВИТЬ БАЛЛЫ
# =========================================================

@dp.callback_query(F.data == "add_points")
async def add_points_start(callback: CallbackQuery):

    if not is_admin(callback.from_user.id):

        await callback.answer(
            "⛔ Эта функция доступна только администраторам.",
            show_alert=True,
        )

        return

    clear_action(callback.from_user.id)

    await safe_edit(
        callback,
        "➕ <b>Добавить баллы</b>\n\n"
        "Выбери команду:",
        points_teams_keyboard(),
    )

    await callback.answer()


# =========================================================
# ВЫБОР КОМАНДЫ
# =========================================================

@dp.callback_query(F.data.startswith("points_team:"))
async def points_team(callback: CallbackQuery):

    if not is_admin(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True,
        )

        return

    team_id = int(
        callback.data.split(":")[1]
    )

    team = get_team(team_id)

    if not team:

        await callback.answer(
            "Команда не найдена.",
            show_alert=True,
        )

        return

    clear_action(callback.from_user.id)

    await safe_edit(
        callback,
        f"➕ <b>{html.escape(team['name'])}</b>\n\n"
        "Выбери действие:",
        points_actions_keyboard(team["id"]),
    )

    await callback.answer()


# =========================================================
# ПОБЕДА = +100
# =========================================================

@dp.callback_query(F.data.startswith("win:"))
async def win_handler(callback: CallbackQuery):

    if not is_admin(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True,
        )

        return

    team_id = int(
        callback.data.split(":")[1]
    )

    team = get_team(team_id)

    if not team:

        await callback.answer(
            "Команда не найдена.",
            show_alert=True,
        )

        return

    new_score = add_points(
        team_id=team["id"],
        points=100,
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        activity="Победа",
    )

    await update_pinned_scoreboard()

    clear_action(callback.from_user.id)

    await safe_edit(
        callback,
        "🏆 <b>Победа засчитана!</b>\n\n"
        f"Команда: <b>{html.escape(team['name'])}</b>\n"
        "Изменение: <b>+100</b>\n"
        f"Новый счёт: <b>{new_score}</b>",
        admin_keyboard(),
    )

    await callback.answer(
        "+100 баллов добавлено"
    )


# =========================================================
# ВВЕСТИ СВОЁ КОЛИЧЕСТВО БАЛЛОВ
# =========================================================

@dp.callback_query(F.data.startswith("custom_points:"))
async def custom_points_start(callback: CallbackQuery):

    if not is_admin(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True,
        )

        return

    team_id = int(
        callback.data.split(":")[1]
    )

    team = get_team(team_id)

    if not team:

        await callback.answer(
            "Команда не найдена.",
            show_alert=True,
        )

        return

    pending_actions[callback.from_user.id] = {
        "action": "points",
        "team_id": team["id"],
    }

    await safe_edit(
        callback,
        f"✏️ <b>{html.escape(team['name'])}</b>\n\n"
        "Введи количество баллов числом.\n\n"
        "Например:\n"
        "<code>50</code>\n"
        "<code>-20</code>",
        back_keyboard(),
    )

    await callback.answer()


# =========================================================
# 2. ОБЩИЙ РЕЙТИНГ
# ДОСТУПЕН ВСЕМ
# =========================================================

@dp.callback_query(F.data == "scoreboard")
async def scoreboard(callback: CallbackQuery):

    clear_action(callback.from_user.id)

    text = build_scoreboard_text()

    if is_admin(callback.from_user.id):
        keyboard = admin_keyboard()
    else:
        keyboard = user_keyboard()

    await safe_edit(
        callback,
        text,
        keyboard,
    )

    await callback.answer()


# =========================================================
# 3. ИСТОРИЯ
# ДОСТУПНА ВСЕМ
# =========================================================

@dp.callback_query(F.data == "history")
async def history_handler(callback: CallbackQuery):

    clear_action(callback.from_user.id)

    history = get_history(
        limit=50
    )

    if not history:

        text = (
            "📜 <b>История изменения баллов</b>\n\n"
            "Изменений пока нет."
        )

    else:

        text = (
            "📜 <b>История изменения баллов</b>\n\n"
        )

        for row in history:

            if row["username"]:

                who = (
                    f"@{row['username']}"
                )

            elif row["first_name"]:

                who = row["first_name"]

            else:

                who = (
                    f"id {row['user_id']}"
                )

            sign = (
                "+"
                if row["points"] >= 0
                else ""
            )

            text += (
                f"👤 <b>{html.escape(str(who))}</b> "
                f"→ "
                f"<b>{html.escape(str(row['team_name']))}</b>: "
                f"<b>{sign}{row['points']}</b> баллов\n"
            )

            if row["activity"]:

                text += (
                    f"📝 "
                    f"{html.escape(str(row['activity']))}\n"
                )

            text += (
                f"🕐 {row['created_at']}\n\n"
            )

    if is_admin(callback.from_user.id):
        keyboard = admin_keyboard()
    else:
        keyboard = user_keyboard()

    await safe_edit(
        callback,
        text,
        keyboard,
    )

    await callback.answer()


# =========================================================
# 4. КОМАНДЫ
# ДОСТУПНЫ ВСЕМ
# =========================================================

@dp.callback_query(F.data == "teams")
async def teams_handler(callback: CallbackQuery):

    clear_action(callback.from_user.id)

    teams = get_teams()

    text = "👥 <b>КОМАНДЫ</b>\n\n"

    for team in teams:

        text += (
            f"🏆 <b>{html.escape(team['name'])}</b>"
            f" — {team['score']} баллов\n"
        )

    # Администратор может переименовывать команды.
    if is_admin(callback.from_user.id):

        text += (
            "\nВыбери команду, "
            "чтобы изменить название:"
        )

        keyboard = rename_keyboard()

    # Обычный пользователь только смотрит список.
    else:

        keyboard = user_keyboard()

    await safe_edit(
        callback,
        text,
        keyboard,
    )

    await callback.answer()


# =========================================================
# ПЕРЕИМЕНОВАНИЕ КОМАНДЫ
# ТОЛЬКО АДМИНИСТРАТОР
# =========================================================

@dp.callback_query(F.data.startswith("rename:"))
async def rename_start(callback: CallbackQuery):

    if not is_admin(callback.from_user.id):

        await callback.answer(
            "⛔ Изменять названия могут только администраторы.",
            show_alert=True,
        )

        return

    team_id = int(
        callback.data.split(":")[1]
    )

    team = get_team(team_id)

    if not team:

        await callback.answer(
            "Команда не найдена.",
            show_alert=True,
        )

        return

    pending_actions[callback.from_user.id] = {
        "action": "rename",
        "team_id": team["id"],
    }

    await safe_edit(
        callback,
        "✏️ <b>Переименование команды</b>\n\n"
        f"Сейчас: <b>{html.escape(team['name'])}</b>\n\n"
        "Отправь новое название:",
        back_keyboard(),
    )

    await callback.answer()


# =========================================================
# ОБРАБОТКА ТЕКСТА ОТ АДМИНА
# =========================================================

@dp.message()
async def text_handler(message: Message):

    # Обычные пользователи ничего через этот обработчик
    # сделать не могут.
    if not is_admin(message.from_user.id):
        return

    action = pending_actions.get(
        message.from_user.id
    )

    if not action:
        return

    text = (
        message.text or ""
    ).strip()

    if not text:
        return


    # =====================================================
    # ПЕРЕИМЕНОВАНИЕ
    # =====================================================

    if action["action"] == "rename":

        if len(text) > 50:

            await message.answer(
                "❗ Название слишком длинное.\n"
                "Максимум 50 символов."
            )

            return

        rename_team(
            action["team_id"],
            text,
        )

        await update_pinned_scoreboard()

        clear_action(
            message.from_user.id
        )

        await message.answer(
            "✅ <b>Команда переименована</b>\n\n"
            f"Новое название: "
            f"<b>{html.escape(text)}</b>",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )

        return


    # =====================================================
    # ВВОД БАЛЛОВ
    # =====================================================

    if action["action"] == "points":

        # Разрешаем положительные и отрицательные числа.
        if not text.lstrip("-").isdigit():

            await message.answer(
                "❗ Введи только число.\n\n"
                "Например:\n"
                "<code>50</code>\n"
                "<code>-20</code>",
                parse_mode="HTML",
            )

            return

        points = int(text)

        team = get_team(
            action["team_id"]
        )

        if not team:

            clear_action(
                message.from_user.id
            )

            await message.answer(
                "Команда не найдена."
            )

            return

        new_score = add_points(
            team_id=team["id"],
            points=points,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            activity="Ручное начисление",
        )

        await update_pinned_scoreboard()

        clear_action(
            message.from_user.id
        )

        sign = (
            "+"
            if points >= 0
            else ""
        )

        await message.answer(
            "✅ <b>Баллы изменены</b>\n\n"
            f"Команда: "
            f"<b>{html.escape(team['name'])}</b>\n"
            f"Изменение: "
            f"<b>{sign}{points}</b>\n"
            f"Новый счёт: "
            f"<b>{new_score}</b>",
            reply_markup=admin_keyboard(),
            parse_mode="HTML",
        )


# =========================================================
# ЗАПУСК
# =========================================================

async def main():

    init_database()

    logger.info(
        "CAMP WARS bot started"
    )

    try:

        await dp.start_polling(
            bot
        )

    except TelegramConflictError:

        logger.error(
            "Этот BOT_TOKEN уже используется "
            "другим экземпляром бота."
        )

        raise


if __name__ == "__main__":
    asyncio.run(main())
