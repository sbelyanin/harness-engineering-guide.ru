---
author: Nexu
---

# Harness vs. Framework

> **Главный инсайт:** Фреймворк добавляет сотни зависимостей и слои абстракции ради задачи, которой может хватить 50 строк Python. Но писать multi-agent-оркестрацию с нуля, когда CrewAI уже решает её — значит терять недели. Главное — подобрать инструмент под задачу, а не брать самый популярный по умолчанию.

Harness — это код, который вы пишете с нуля, чтобы обернуть модель tools, memory и context. **Фреймворк** — это библиотека с абстракциями для построения агентов: LangChain, CrewAI, AutoGen и другие. Выбор между ними — не вопрос «что лучше», а вопрос о том, когда каждый из них окупается.

## Дерево решений

```
Нужен агент?
│
├── Это цикл с одной моделью и < 5 tools?
│   └── ДА → Пишите сырой harness (50-200 строк)
│
├── Нужна multi-agent-оркестрация из коробки?
│   └── ДА → Присмотритесь к CrewAI или AutoGen
│
├── Нужны сложные RAG-пайплайны с vector-хранилищами?
│   └── ДА → Присмотритесь к LangChain
│
├── Это production-продукт, где нужен полный контроль?
│   └── ДА → Пишите сырой harness (владейте каждой строкой)
│
├── Вы быстро прототипируете / исследуете?
│   └── ДА → Фреймворк ок, но ожидайте переписывания позже
│
└── Нужно понимать, что реально происходит?
    └── ДА → Сначала сырой harness, потом решайте
```

## Одна задача — три способа

**Задача**: прочитать CSV-файл, проанализировать его и записать саммари в Markdown-файл.

### Сырой Harness (~60 строк)

```python
import json, csv, io
from openai import OpenAI

client = OpenAI()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    }
]

def execute(name, args):
    if name == "read_file":
        return open(args["path"]).read()
    elif name == "write_file":
        open(args["path"], "w").write(args["content"])
        return f"Written to {args['path']}"

def run(task):
    messages = [
        {"role": "system", "content": "You analyze data files and write reports."},
        {"role": "user", "content": task}
    ]
    for _ in range(10):
        resp = client.chat.completions.create(
            model="gpt-4o-mini", messages=messages, tools=TOOLS
        )
        msg = resp.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content
        for tc in msg.tool_calls:
            result = execute(tc.function.name, json.loads(tc.function.arguments))
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    return "Done"

run("Read data.csv, analyze the trends, and write a summary to report.md")
```

**Зависимости**: `openai` (1 пакет)
**Строк кода**: ~60
**Вы контролируете**: всё

### LangChain (~40 строк, но…)

```python
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import tool

@tool
def read_file(path: str) -> str:
    """Read a file's contents"""
    return open(path).read()

@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file"""
    open(path, "w").write(content)
    return f"Written to {path}"

llm = ChatOpenAI(model="gpt-4o-mini")
prompt = ChatPromptTemplate.from_messages([
    ("system", "You analyze data files and write reports."),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])

agent = create_openai_tools_agent(llm, [read_file, write_file], prompt)
executor = AgentExecutor(agent=agent, tools=[read_file, write_file], verbose=True)

executor.invoke({"input": "Read data.csv, analyze trends, write summary to report.md"})
```

**Зависимости**: `langchain`, `langchain-openai`, `langchain-core` плюс транзитивные (~50+ пакетов)
**Строк кода**: ~40 (но слои абстракции под ними — тысячи)
**Вы контролируете**: определения tools, шаблон промпта. Всё остальное — LangChain.

### CrewAI (~35 строк)

```python
from crewai import Agent, Task, Crew
from crewai_tools import FileReadTool, FileWriterTool

analyst = Agent(
    role="Data Analyst",
    goal="Analyze CSV data and produce insightful reports",
    backstory="You are an expert data analyst.",
    tools=[FileReadTool(), FileWriterTool()],
    verbose=True
)

task = Task(
    description="Read data.csv, analyze the trends, write a summary to report.md",
    expected_output="A markdown report with key findings",
    agent=analyst
)

crew = Crew(agents=[analyst], tasks=[task], verbose=True)
crew.kickoff()
```

**Зависимости**: `crewai`, `crewai-tools` плюс их зависимости (~80+ пакетов)
**Строк кода**: ~35
**Вы контролируете**: роли агентов, описания задач. Поток выполнения — CrewAI.

## Матрица компромиссов

| Параметр | Сырой Harness | LangChain | CrewAI |
|-----------|------------|-----------|--------|
| Строк кода | Больше | Меньше | Меньше всего |
| Зависимости | 1 | ~50 | ~80 |
| Дебаг | Лёгкий (ваш код) | Сложный (глубокие трейсы) | Средний |
| Гибкость | Тотальная | Ограничена абстракциями | Только role-based |
| Multi-agent | Строите сами | Возможно, но сложно | Из коробки |
| Порог входа | Понять API модели | Выучить концепции LangChain | Выучить концепции CrewAI |
| Путь апгрейда | Меняйте что хотите | Ждать апдейтов LangChain | Ждать апдейтов CrewAI |
| Production-готовность | Решаете вы | Зависит от стабильности версий | Новее, менее обкатан |

## Скрытая стоимость фреймворков

### 1. Дебаг «чёрных ящиков»

Когда что-то ломается в сыром harness, вы смотрите на свои 60 строк. Когда ломается в LangChain:

```
File "langchain/agents/openai_tools/base.py", line 147, in _plan
File "langchain_core/runnables/base.py", line 534, in invoke
File "langchain/chains/base.py", line 89, in __call__
File "langchain_core/callbacks/manager.py", line 442, in _handle_event
...
```

Вы дебажите чужую архитектуру.

### 2. Lock-in абстракциями

Хотите добавить streaming? Нестандартную memory? Нестандартный паттерн tool-calling? В сыром harness — просто пишете. Во фреймворке — работаете в рамках его точек расширения или форкаете библиотеку.

### 3. Version churn

У LangChain было несколько крупных переделок API. Код полугодовой давности может не запускаться сегодня. Сырой harness с одним пакетом `openai` стабилен годами.

## Когда фреймворки выигрывают

Фреймворки — не зло. Они реально помогают, когда:

- **Вы прототипируете** — за полдня получить работающее, чтобы валидировать идею. Переписать позже.
- **Multi-agent-оркестрация** — модель «агент-задача» у CrewAI действительно хороша для сложных multi-role-процессов.
- **RAG-пайплайны** — document loaders, сплиттеры и интеграции с vector-хранилищами у LangChain экономят реальную работу.
- **Вам не важна инфраструктура** — если агент — небольшая часть более крупного продукта и вам нужно просто, чтобы он работал.

## Гибридный подход

Многие production-команды начинают с фреймворка и мигрируют на сырой harness:

```
Неделя 1:  LangChain-прототип → «Работает!»
Неделя 4:  Уперлись в ограничение → «Почему я не могу сделать X?»
Неделя 8:  Форкаете/обходите полфреймворка → «Я борюсь с фреймворком»
Неделя 12: Переписываете как сырой harness → «Это 200 строк и делает ровно то, что нужно»
```

Это нормально. Фреймворк научил вас, что вам нужно. Harness даёт контроль.

## Частые ошибки

- **Начинать с фреймворка, не разобравшись в базе** — нельзя дебажить то, чего не понимаете. Соберите сырой harness хотя бы раз, даже если в production он не попадёт.
- **Выбирать по числу звёзд на GitHub** — звёзды ≠ соответствие задаче. Фреймворк на 80K звёзд, заточенный под RAG, не поможет собрать coding-агента.
- **Боязнь «изобрести велосипед»** — колесо здесь — это 50 строк Python. Не так уж много колеса.

## Что почитать

- [LangChain Documentation](https://python.langchain.com/) — самый популярный фреймворк
- [CrewAI Documentation](https://docs.crewai.com/) — multi-agent-оркестрация
- [AutoGen](https://microsoft.github.io/autogen/) — multi-agent-фреймворк от Microsoft
- [Ваш первый Harness](/guide/your-first-harness) — соберите сырую версию сами
