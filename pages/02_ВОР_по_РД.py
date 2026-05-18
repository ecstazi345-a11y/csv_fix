import streamlit as st
import pandas as pd
import os
import json
import tempfile
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
st.set_page_config(page_title="ВОР по РД", layout="wide")


DEFAULT_PROMPT = """Ты выступаешь как senior инженер ПТО, cost engineer и BIM quantity surveyor по внутренним инженерным системам.

Твоя задача — на основе загруженного чертежа, схемы, спецификации или выгрузки из проектной модели сформировать черновую ведомость объемов работ.

Проанализируй:
1. систему;
2. оборудование;
3. трубопроводы / воздуховоды / кабельные линии;
4. диаметры, сечения, материалы;
5. фасонные части;
6. арматуру;
7. отметки, уклоны, привязки;
8. зоны и участки работ;
9. недостающие данные;
10. риски ошибки расчета.

Не придумывай данные.
Если объем невозможно определить точно — укажи "требуется уточнение".
Если объем можно определить только ориентировочно — пометь как "оценочно".

Результат выдай в формате таблицы:

Раздел | Система | Зона | Наименование работ | Ед. изм. | Кол-во | Основание | Уверенность | Комментарий
"""

REGISTRY_FIELDS = [
    ("Source_File", "исходный файл РД или спецификации"),
    ("System", "система"),
    ("Zone", "зона или участок работ"),
    ("Work_Package", "пакет работ"),
    ("BoQ_Code", "код позиции BOQ"),
    ("Work_Name", "наименование работы"),
    ("Unit", "единица измерения"),
    ("Quantity", "объем"),
    ("Quantity_Status", "точно / оценочно / требуется уточнение"),
    ("Confidence", "уверенность распознавания"),
    ("Required_For_Executability", "требуется ли для допуска фронта"),
    ("Required_For_Acceptance", "требуется ли для приемки и признания"),
    ("Comment", "комментарий инженера"),
]

ARCHITECTURE_TEXT = """РД / Спецификация
↓
AI Extraction
↓
ВОР
↓
Реестр работ
↓
Зоны и пакеты работ
↓
Допуск фронта
↓
Допуск к оплате
↓
Паспорт месяца
↓
Недельный план
↓
Дневное задание
↓
Факт
↓
Приемка
↓
Признание
↓
Деньги"""


def analyze_pdf_with_ai(uploaded_file, prompt):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getvalue())
            temp_path = tmp.name

        uploaded_openai_file = client.files.create(
            file=open(temp_path, "rb"),
            purpose="assistants",
        )

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "file_id": uploaded_openai_file.id,
                        },
                        {
                            "type": "input_text",
                            "text": prompt
                            + """

Верни результат СТРОГО как JSON массив.

Без текста.
Без объяснений.

Формат:

[
  {
    "Раздел": "",
    "Система": "",
    "Зона": "",
    "Наименование работ": "",
    "Ед. изм.": "",
    "Кол-во": "",
    "Основание": "",
    "Уверенность": "",
    "Комментарий": ""
  }
]
""",
                        },
                    ],
                }
            ],
        )

        return json.loads(response.output_text)

    except Exception as e:
        st.error(f"Ошибка AI-анализа: {str(e)}")
        return None


st.title("ВОР по РД")
st.caption("AI-агент формирования ведомости объемов работ по чертежам и спецификациям")

st.info(
    "Эта страница является первым слоем цепочки: "
    "РД → ВОР → Реестр работ → Зоны → Пакеты работ → Допуск фронта → "
    "План → Факт → Приемка → Признание → Деньги."
)

st.divider()

st.subheader("Загрузка исходных данных")

uploaded = st.file_uploader(
    "Загрузите чертеж, схему, спецификацию или выгрузку из проектной модели",
    type=["pdf", "png", "jpg", "jpeg", "dwg", "dxf", "xml", "xlsx", "csv"],
    accept_multiple_files=False,
)

file_name = "файл не загружен"
file_type = "—"
file_size = "—"

if uploaded is not None:
    file_name = uploaded.name
    file_type = uploaded.type or "не определен"
    file_size = f"{uploaded.size / (1024 * 1024):.2f} МБ"

    st.success("Файл загружен")
    st.write(f"**Файл:** {file_name}")
    st.write(f"**Тип:** {file_type}")
    st.write(f"**Размер:** {file_size}")
else:
    st.warning("Файл пока не загружен. Можно использовать демонстрационный режим.")

st.divider()

st.subheader("Промт анализа РД")

st.text_area(
    "Текст промта для будущего AI-агента",
    value=DEFAULT_PROMPT,
    height=300,
    key="vor_rd_prompt",
)

st.divider()

AI_PASSWORD = os.getenv("VOR_AI_PASSWORD", "")

st.subheader("Доступ к AI-анализу")

user_password = st.text_input(
    "Введите пароль для AI-анализа",
    type="password",
)

is_ai_allowed = user_password == AI_PASSWORD

st.subheader("Черновая ВОР")

if uploaded is None:
    st.info("Загрузите файл РД для анализа.")

else:
    if not is_ai_allowed:

        st.warning("AI-анализ временно доступен только администраторам.")

    else:

        st.success("Доступ к AI-анализу разрешён")

        if st.button("AI-анализ PDF"):

            with st.spinner("AI анализирует PDF..."):

                ai_result = analyze_pdf_with_ai(uploaded, DEFAULT_PROMPT)

                if ai_result:

                    df = pd.DataFrame(ai_result)

                    st.success("Черновая ВОР сформирована")

                    st.dataframe(df, use_container_width=True, hide_index=True)

                else:
                    st.warning("AI-анализ не вернул данные.")

st.divider()

st.subheader("Минимальная структура будущего реестра работ")

registry_df = pd.DataFrame(
    [{"Поле": field, "Назначение": purpose} for field, purpose in REGISTRY_FIELDS]
)

st.dataframe(registry_df, use_container_width=True, hide_index=True)

st.divider()

st.subheader("Куда передается результат")

st.markdown(
    "**ВОР → Реестр работ → Системы → Зоны → Пакеты работ → Допуск фронта → "
    "Паспорт месяца → Неделя → День → Человек → Факт → Приемка → Признание → Деньги**"
)

st.divider()

st.subheader("Следующий этап развития")

st.markdown("""
- чтение PDF;
- распознавание изображений;
- чтение DXF/DWG;
- извлечение спецификаций;
- расчет длин труб и воздуховодов;
- подсчет фасонных частей;
- связка с BOQ;
- расчет трудозатрат;
- передача в Допуск фронта;
- передача в Monthly Passport Plan.
""")

st.divider()

st.subheader("Будущая архитектура")
st.code(ARCHITECTURE_TEXT, language=None)

st.divider()

st.warning(
    "На текущем этапе это демонстрационный модуль. "
    "Финальные объемы должны подтверждаться инженером ПТО по РД, спецификациям и договорной BOQ."
)
