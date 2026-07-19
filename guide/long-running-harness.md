---
title: "Дизайн Long-Running Harness"
section: practice
author: Nexu
---

# Дизайн Long-Running Harness

> **Главный инсайт:** Агенты для коротких задач падают предсказуемо — они либо заканчивают, либо таймаутятся. Долгоиграющие агенты падают коварно. Они раздували context, тихо деградируют и убеждают себя, что делают великое дело, тогда как сами дрейфуют мимо курса. Дизайн harness для долгоиграющих агентов — это дизайн против этих failure-модов.

## Почему долгоиграющие агенты сложны

«Короткозадачный» агент — ответить на вопрос, написать функцию, саммаризовать документ — живёт и умирает в одном context window. Он либо заканчивает, либо падает заметно.

«Долгоиграющий» агент работает часами или днями: рефакторит кодовую базу, пишет отчёт на 50 страниц, гоняет многостадийный pipeline. Такие агенты сталкиваются с проблемами, которых у короткозадачных не бывает:

1. **Context накапливается.** Каждый tool-вызов, каждый промежуточный результат, каждый шаг рассуждения добавляет токены. Окно 200K заполняется быстрее, чем кажется.
2. **Качество деградирует тихо.** Агент не падает — он просто становится хуже. Ответы расплываются, инструкции забываются, ранний context вытесняется.
3. **Самооценка врёт.** Спросите агента «у тебя хорошая работа?» — он скажет да. Всегда. Для 30-секундной задачи, которую можно проверить глазом, это ок. Для 4-часового pipeline, за которым вы не следите, — катастрофа.

## Failure-мод #1: Context Anxiety

Когда долгоиграющий агент заполняет context window, происходит контринтуитивное: модель начинает спешить. Преждевременно завершает, срезает углы и заявляет «готово» до того, как работа реально закончена.

Это **context anxiety** — неявное осознание моделью, что место заканчивается. Проявляется как:

- Пропуск шагов, которые она обычно делает
- Более короткие, менее тщательные выводы
- Преждевременное объявление завершения с «я покрыл основные моменты»
- Избегание tool-вызовов, которые добавили бы context

Context anxiety эмерджентна для разных архитектур. Модель выучила, что диалоги заканчиваются, и по мере сжатия места тяготеет к завершению.

**Больше окно откладывает проблему, а не решает.** Фикс архитектурный: управлять lifecycle context явно.

## Failure-мод #2: Bias самооценки

Попросите генератор оценить свой вывод. Он поставит себе 8/10 или выше — стабильно, независимо от реального качества. Это **bias самооценки**, второй тихий убийца долгоиграющих агентов.

Почему? У модели полный context собственного рассуждения — каждый выбор кажется оправданным. Признать провал значит противоречить предыдущим выводам, к чему LLM сопротивляются. А обучающие данные вознаграждают уверенность, а не самокопание.

В короткой задаче человек ловит проблемы. В долгоиграющей агент работает автономно. Если он оценивает собственный вывод и всегда говорит «выглядит ок», ошибки накапливаются без контроля.

```
Короткая задача:  Агент делает → Человек ревьюит → Фидбек
Долгоиграющая:    Агент делает → Агент ревьюит → «Выглядит супер!» → Ошибки копятся
```

Здесь работает инсайт из дизайна adversarial-сетей: **никогда не давайте генератору оценивать собственный экзамен.**

## Управление Context: Reset vs. Compaction

Когда context заполняется, у вас два варианта. У каждого реальные компромиссы.

### Context Reset

Стираете диалог и начинаете свежо. В новый context передаёте саммари предыдущей работы как «брифинг».

```
Ходы 1-50:  [полная история диалога]
            ↓ context заполнен на 80%
Ход 51:     [system prompt + саммари ходов 1-50 + текущая задача]
            ↓ свежий старт, ~10% context использовано
Ходы 51-100: [продолжение от саммари]
```

**Плюсы:** Чистый лист, предсказуемый токен-бюджет, устраняет context anxiety для нового сегмента.

**Минусы:** С потерями — саммари упускают нюансы и провальные подходы. «Саммари саммари» деградирует через несколько reset'ов. Агент может возвращаться к тупикам.

### Context Compaction

Селективно сжимаете старые ходы, сохраняя недавние нетронутыми. Сворачиваете многоходовое рассуждение в саммари, выбрасываете многословные выводы tools.

```
Ходы 1-20:  [сжато: саммари раннего исследования на 3 строки]
Ходы 21-40: [сжато: ключевые решения и исходы]
Ходы 41-50: [полностью: текущая работа в процессе]
```

**Плюсы:** Сохраняет непрерывность. Градуированно — недавние ходы детальны, старые сжаты. Агент помнит, что пробовал.

**Минусы:** Качество сжатия варьируется. Сложнее в реализации. Сжатый context может путать модель, если саммари конфликтует с недавним состоянием.

### Что выбрать?

| Сценарий | Предпочтительно |
|----------|--------|
| Задачи с ясными фазами (исследование → письмо → ревью) | Reset между фазами |
| Непрерывная итерация над одним артефактом | Compaction |
| Агент часто возвращается к ранним решениям | Compaction (сохраняет историю решений) |
| Context накопил много выводов tools | Reset (выводы tools сжимаются плохо) |

На практике многие harness используют гибрид: compaction внутри фазы, reset между фазами.

## Архитектура Generator-Evaluator

Заимствуем у GAN: генератор создаёт, дискриминатор судит — раздельные сети с противоположными целями. Тот же принцип применим к агентам:

```
┌─────────────┐         ┌──────────────┐
│  Generator  │────────►│  Evaluator   │
│  (Agent A)  │         │  (Agent B)   │
│             │◄────────│              │
│  Производит │ feedback │  Судит       │
│  вывод      │         │  вывод       │
└─────────────┘         └──────────────┘
        │                       │
        │  Отдельный context    │
        │  Отдельный промпт     │
        │  Отдельные критерии   │
```

**Ключевые проектные правила:**

1. **Раздельные context.** Evaluator видит только вывод, а не рассуждения генератора. Предотвращает sympathy-bias.
2. **Явный rubric.** Оценивайте по чек-листу, а не по ощущениям. «Обрабатывает ли код edge-case X?» лучше, чем «Хороший ли код?».
3. **Actionable-feedback.** Возвращайте конкретные проблемы, а не оценки. «Функция `parse_input` не обрабатывает пустые строки» — полезно. «7/10» — нет.
4. **Бюджет итераций.** Ограничивайте цикл. Без лимита перфекционист-evaluator + рьяный generator = бесконечный цикл.

```python
def generator_evaluator_loop(task, max_iterations=3):
    output = None
    for i in range(max_iterations):
        # Generator: produce or revise
        if output is None:
            output = generator.run(task)
        else:
            output = generator.revise(task, output, feedback)

        # Evaluator: judge with fresh eyes
        evaluation = evaluator.judge(task, output)  # no generator context!

        if evaluation.passes:
            return output

        feedback = evaluation.issues

    return output  # best effort after max iterations
```

## Трёхагентная архитектура: Planner → Generator → Evaluator

Для сложных долгоиграющих задач добавьте **Planner** для декомпозиции, выполнения и контроля качества.

```
                    ┌─────────────┐
                    │   Planner   │
                    │             │
                    │ Декомпозирует│
                    │ задачу в    │
                    │ подзадачи   │
                    └──────┬──────┘
                           │
                           ▼
              ┌── список подзадач ──┐
              │                    │
              ▼                    ▼
     ┌─────────────┐      ┌─────────────┐
     │  Generator  │      │  Generator  │   (параллельно или последовательно)
     │  подзадача 1│      │  подзадача 2│
     └──────┬──────┘      └──────┬──────┘
            │                    │
            ▼                    ▼
     ┌─────────────┐      ┌─────────────┐
     │  Evaluator  │      │  Evaluator  │
     │  подзадача 1│      │  подзадача 2│
     └──────┬──────┘      └──────┬──────┘
            │                    │
            └────────┬───────────┘
                     ▼
              ┌─────────────┐
              │   Planner   │
              │ (ревьюит   │
              │  результаты│
              │  переплани-│
              │  рует если │
              │  надо)     │
              └─────────────┘
```

**Planner** — декомпозирует цель в подзадачи с критериями успеха. Перепланирует, когда evaluator'ы флажат проблемы. Держит видение, но не исполняет.

**Generator** — исполняет по одной подзадаче со свежим context. Имеет tools, файлы, среды выполнения. Не оценивает собственную работу.

**Evaluator** — видит только вывод генератора (не рассуждение). Оценивает по критериям planner'а. Возвращает pass/fail плюс конкретные проблемы.

Ключевое свойство: **каждый агент работает в своём context window.** Generator может забить своё окно 200K исследованием кода и всё равно выдать чистый вывод. Evaluator стартует свежим. Planner держит high-level-видение без деталей реализации.

```python
def three_agent_pipeline(goal, max_replans=2):
    plan = planner.decompose(goal)

    for replan in range(max_replans + 1):
        results = {}
        for subtask in plan.subtasks:
            # Generator: fresh context per subtask
            output = generator.execute(subtask)

            # Evaluator: fresh context, only sees output + criteria
            evaluation = evaluator.judge(
                subtask=subtask,
                output=output,
                criteria=subtask.success_criteria
            )

            results[subtask.id] = {
                "output": output,
                "evaluation": evaluation
            }

        # Check if all subtasks pass
        failures = [r for r in results.values() if not r["evaluation"].passes]
        if not failures:
            return assemble_results(results)

        # Re-plan: planner sees which subtasks failed and why
        plan = planner.replan(goal, results)

    return assemble_results(results)  # best effort
```

## Антипаттерны

### Антипаттерн #1: Монолитный агент

Запихивание планирования, выполнения, оценки и управления context в одного агента.

```python
# DON'T DO THIS
response = llm.chat(
    system="""You are a planner, coder, reviewer, and project manager.
    First plan the work, then do the work, then review your own work.
    If the review finds issues, fix them and review again.""",
    messages=conversation  # 150K tokens of accumulated history
)
```

Падает по всем причинам выше: context заполняется, самооценка ненадёжна, нет разделения ответственности. Работает на простых задачах, рушится на сложных.

### Антипаттерн #2: Оценка без rubric

```python
# DON'T DO THIS
evaluation = evaluator.judge(
    prompt=f"Is this output good? Rate 1-10.\n\n{output}"
)
# Result: always 8/10. Always.
```

Evaluator без критериев — это просто генератор с синдромом самозванца. Всегда давайте rubric:

```python
# DO THIS
evaluation = evaluator.judge(
    prompt=f"""Evaluate the following output against these criteria:
    1. Does every function have error handling for edge cases?
    2. Are all API calls wrapped in retry logic?
    3. Does the code match the spec in {spec_file}?
    4. Are there any hardcoded values that should be config?

    Output to evaluate:
    {output}

    For each criterion, answer PASS or FAIL with a one-line explanation."""
)
```

### Антипаттерн #3: Бесконечное перепланирование

```python
# DON'T DO THIS
while not all_subtasks_pass:
    plan = planner.replan(goal, results)  # loops forever
    results = execute_plan(plan)
```

Всегда ограничивайте итерации. Три провальных перепланирования — проблема в спеке, а не в исполнении. Эскалируйте человеку.

## Собираем вместе: минимальная реализация

```python
class LongRunningHarness:
    """Planner → Generator → Evaluator harness for long-running tasks."""

    def __init__(self, planner_model, generator_model, evaluator_model):
        self.planner = Agent(model=planner_model, role="planner")
        self.generator = Agent(model=generator_model, role="generator")
        self.evaluator = Agent(model=evaluator_model, role="evaluator")

    def run(self, goal, max_replans=2, max_gen_iterations=3):
        plan = self.planner.decompose(goal)

        for _ in range(max_replans + 1):
            results = {}

            for subtask in plan.subtasks:
                output = self._generate_with_eval(
                    subtask, max_iterations=max_gen_iterations
                )
                results[subtask.id] = output

            failures = {k: v for k, v in results.items() if not v["passed"]}
            if not failures:
                return self._assemble(results)

            plan = self.planner.replan(goal, plan, failures)

        return self._assemble(results, partial=True)  # best effort

    def _generate_with_eval(self, subtask, max_iterations):
        output = None
        for i in range(max_iterations):
            output = self.generator.execute(
                subtask=subtask,
                prior_feedback=output.get("feedback") if output else None
            )

            evaluation = self.evaluator.judge(
                output=output["result"],
                criteria=subtask.success_criteria
            )

            if evaluation["passes"]:
                return {"result": output["result"], "passed": True}

            output["feedback"] = evaluation["issues"]

        return {"result": output["result"], "passed": False,
                "feedback": evaluation["issues"]}

    def _assemble(self, results, partial=False):
        assembled = "\n\n".join(r["result"] for r in results.values())
        if partial:
            failed = [k for k, v in results.items() if not v["passed"]]
            assembled += f"\n\n⚠️ Incomplete subtasks: {failed}"
        return assembled
```

## Ключевые выводы

1. **Долгоиграющий ≠ короткозадачный с большим временем.** Failure-моды качественно другие.
2. **Context anxiety реален.** Управляйте lifecycle context через reset, compaction или и то и другое.
3. **Никогда не давайте генератору оценивать собственный экзамен.** Раздельные агенты, раздельные context, явные rubric.
4. **Ограничивайте всё.** Максимум ходов, максимум перепланирований, максимум итераций. Неограниченные циклы жгут токены.
5. **Декомпозируйте сначала.** Куски размером с context предотвращают большинство context-проблем до их появления.

## Что почитать

- [Context Engineering](context-engineering.md) — глубокий разбор сборки, сжатия и бюджетирования context
- [Multi-Agent Orchestration](multi-agent-orchestration.md) — паттерны оркестрации за пределами трёхагентной архитектуры
- [Error Handling](error-handling.md) — обработка падений, retry и graceful degradation в agent-циклах
- [Anthropic: Building effective agents](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/building-effective-agents) — гайд Anthropic по паттернам дизайна агентов
