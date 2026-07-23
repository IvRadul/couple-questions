from sqlalchemy.orm import Session
from app import models, crud

# Стартовый бесплатный пак — открыт всем парам сразу, свободные текстовые ответы,
# совпадение подтверждает вручную тот, кто отвечал "про себя" (Тип 1).
STARTER_OPEN_QUESTIONS = [
    ("Какое любимое блюдо твоего партнёра?", "быт"),
    ("Какой фильм партнёр может пересматривать бесконечно?", "развлечения"),
    ("Какая мечта у твоего партнёра, о которой мало кто знает?", "личное"),
    ("В какой стране партнёр хотел бы жить, если бы мог выбрать?", "путешествия"),
    ("Какая любимая песня у твоего партнёра?", "развлечения"),
    ("Чего партнёр больше всего боится?", "личное"),
    ("Какой подарок партнёр запомнил больше всего?", "воспоминания"),
    ("Какое качество партнёр больше всего ценит в людях?", "личное"),
    ("Какой самый смешной момент был в ваших отношениях?", "воспоминания"),
    ("Какую суперспособность выбрал бы твой партнёр?", "фантазия"),
    ("Какой десерт любимый у твоего партнёра?", "быт"),
    ("Какое время года любит партнёр больше всего?", "быт"),
    ("Какая профессия была мечтой партнёра в детстве?", "личное"),
    ("Какой напиток закажет партнёр в кафе почти всегда?", "быт"),
    ("Какое животное партнёр хотел бы завести дома?", "быт"),
]

# Вопросы Типа 2 с готовыми вариантами ответа — сравниваются автоматически.
STARTER_CHOICE_QUESTIONS = [
    (
        "Какое время суток партнёр любит больше всего?",
        "быт",
        ["Раннее утро", "День", "Вечер", "Глубокая ночь"],
    ),
    (
        "Какой формат отдыха партнёр выберет в первую очередь?",
        "путешествия",
        ["Пляж и море", "Горы и поход", "Город и музеи", "Диван и сериалы"],
    ),
    (
        "Что партнёр закажет на завтрак, если можно всё что угодно?",
        "быт",
        ["Омлет", "Блины", "Овсянку", "Круассан с кофе"],
    ),
    (
        "Какой жанр фильма партнёр выберет для вечернего просмотра?",
        "развлечения",
        ["Комедия", "Драма", "Ужасы", "Фантастика"],
    ),
    (
        "Сколько детей партнёр хотел бы в будущем?",
        "личное",
        ["Ни одного", "Одного", "Двоих", "Троих и больше"],
    ),
]

# Платный тематический пак — открывается за монеты.
MEMORIES_PACK_OPEN_QUESTIONS = [
    ("Какое воспоминание о первом свидании партнёр вспоминает чаще всего?", "воспоминания"),
    ("Какой комплимент партнёру запомнился больше всего?", "воспоминания"),
    ("Какая черта характера партнёра тебе нравится больше всего?", "личное"),
    ("Куда партнёр мечтает поехать в следующий отпуск?", "путешествия"),
    ("Какую книгу партнёр рекомендует чаще всего?", "развлечения"),
    ("Что партнёр считает своим главным достижением?", "личное"),
    ("Какая привычка партнёра тебя веселит?", "быт"),
    ("Какой праздник партнёр любит больше всего?", "быт"),
    ("Что партнёр обычно делает, чтобы расслабиться после тяжёлого дня?", "быт"),
    ("Что партнёр считает романтикой?", "личное"),
]

MEMORIES_PACK_CHOICE_QUESTIONS = [
    (
        "Какую музыку партнёр включит на долгой дороге?",
        "развлечения",
        ["Плейлист любимой группы", "Подкаст", "Тишину", "Радио"],
    ),
    (
        "Какой подарок обрадует партнёра больше всего?",
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
