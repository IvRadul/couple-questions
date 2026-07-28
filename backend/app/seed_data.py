from sqlalchemy.orm import Session
from app import models, crud

# Тексты вопросов используют плейсхолдер {username}, который на бэкенде
# подставляется отображаемым именем ОТВЕЧАЮЩЕГО (answerer) — см.
# crud.render_question_text() и routers/game.py::_question_payload().
#
# ВАЖНО: имя вставляется как есть, без склонения по падежам, поэтому
# {username} в каждом вопросе стоит строго в позиции подлежащего
# (именительный падеж, "{username} делает/любит/боится..."), а не как
# дополнение/определение ("подарок {username}а", "у {username}") —
# иначе для многих имён фраза будет грамматически некорректной.

# Стартовый бесплатный пак — открыт всем парам сразу, свободные текстовые ответы,
# совпадение подтверждает вручную тот, кто отвечал "про себя" (Тип 1).
STARTER_OPEN_QUESTIONS = [
    ("Какое блюдо больше всего любит {username}?", "быт"),
    ("Какой фильм {username} может пересматривать бесконечно?", "развлечения"),
    ("Какую мечту, о которой мало кто знает, скрывает {username}?", "личное"),
    ("В какой стране больше всего хочет жить {username}?", "путешествия"),
    ("Какую песню больше всего любит {username}?", "развлечения"),
    ("Чего больше всего боится {username}?", "личное"),
    ("Какой подарок {username} запомнит на всю жизнь?", "воспоминания"),
    ("Какое качество {username} больше всего ценит в людях?", "личное"),
    ("Какой самый смешной момент из ваших отношений чаще всего вспоминает {username}?", "воспоминания"),
    ("Какую суперспособность больше всего хочет получить {username}?", "фантазия"),
    ("Какой десерт больше всего любит {username}?", "быт"),
    ("Какое время года больше всего любит {username}?", "быт"),
    ("Какую профессию {username} мечтает получить с детства?", "личное"),
    ("Какой напиток закажет {username} в кафе почти всегда?", "быт"),
    ("Какое животное больше всего хочет завести {username}?", "быт"),
]

# Вопросы Типа 2 с готовыми вариантами ответа — сравниваются автоматически.
STARTER_CHOICE_QUESTIONS = [
    (
        "Какое время суток больше всего любит {username}?",
        "быт",
        ["Раннее утро", "День", "Вечер", "Глубокая ночь"],
    ),
    (
        "Какой формат отдыха выберет {username} в первую очередь?",
        "путешествия",
        ["Пляж и море", "Горы и поход", "Город и музеи", "Диван и сериалы"],
    ),
    (
        "Что закажет на завтрак {username}, если можно всё что угодно?",
        "быт",
        ["Омлет", "Блины", "Овсянку", "Круассан с кофе"],
    ),
    (
        "Какой жанр фильма выберет {username} для вечернего просмотра?",
        "развлечения",
        ["Комедия", "Драма", "Ужасы", "Фантастика"],
    ),
    (
        "Сколько детей хочет {username} в будущем?",
        "личное",
        ["Ни одного", "Одного", "Двоих", "Троих и больше"],
    ),
]

# Платный тематический пак — открывается за монеты.
MEMORIES_PACK_OPEN_QUESTIONS = [
    ("Какое воспоминание о первом свидании чаще всего вспоминает {username}?", "воспоминания"),
    ("Какой комплимент {username} запомнит на всю жизнь?", "воспоминания"),
    ("Какой своей чертой характера больше всего гордится {username}?", "личное"),
    ("Куда мечтает поехать в следующий отпуск {username}?", "путешествия"),
    ("Какую книгу чаще всего рекомендует {username}?", "развлечения"),
    ("Что {username} считает своим главным достижением?", "личное"),
    ("Чем {username} обычно веселит тебя?", "быт"),
    ("Какой праздник больше всего любит {username}?", "быт"),
    ("Что обычно делает {username}, чтобы расслабиться после тяжёлого дня?", "быт"),
    ("Что {username} считает романтикой?", "личное"),
]

MEMORIES_PACK_CHOICE_QUESTIONS = [
    (
        "Какую музыку включит {username} на долгой дороге?",
        "развлечения",
        ["Плейлист любимой группы", "Подкаст", "Тишину", "Радио"],
    ),
    (
        "Чему {username} больше всего обрадуется?",
        "личное",
        ["Впечатления/поездка", "Что-то практичное", "Украшение", "Хендмейд от тебя"],
    ),
]


def _create_question(db: Session, text: str, category: str, pack_id: int) -> None:
    db.add(models.Question(text=text, category=category, question_type=models.QuestionType.open, pack_id=pack_id))


def _create_choice_question(db: Session, text: str, category: str, options, pack_id: int) -> None:
    question = models.Question(
        text=text, category=category, question_type=models.QuestionType.choice, pack_id=pack_id
    )
    db.add(question)
    db.flush()  # получаем question.id до commit
    for i, option_text in enumerate(options):
        db.add(models.QuestionOption(question_id=question.id, text=option_text, sort_order=i))


def seed_packs_and_questions(db: Session) -> None:
    if db.query(models.QuestionPack).count() > 0:
        return

    starter_pack = models.QuestionPack(
        name="Стартовый набор",
        description="Базовые вопросы, доступны сразу без доплат",
        price_coins=0,
        is_default=True,
        sort_order=0,
    )
    memories_pack = models.QuestionPack(
        name="Воспоминания и мечты",
        description="Вопросы о совместных воспоминаниях и планах на будущее",
        price_coins=50,
        is_default=False,
        sort_order=1,
    )
    db.add_all([starter_pack, memories_pack])
    db.flush()

    for text, category in STARTER_OPEN_QUESTIONS:
        _create_question(db, text, category, starter_pack.id)
    for text, category, options in STARTER_CHOICE_QUESTIONS:
        _create_choice_question(db, text, category, options, starter_pack.id)

    for text, category in MEMORIES_PACK_OPEN_QUESTIONS:
        _create_question(db, text, category, memories_pack.id)
    for text, category, options in MEMORIES_PACK_CHOICE_QUESTIONS:
        _create_choice_question(db, text, category, options, memories_pack.id)

    db.commit()


def run_all_seeds(db: Session) -> None:
    seed_packs_and_questions(db)
    crud.seed_achievements(db)
