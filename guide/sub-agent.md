---
author: Nexu
---

# Sub-Agent

> **Главный инсайт:** У одного агента один context window. Когда задача перерастает это окно — или когда несколько независимых задач можно гонять параллельно — нужны sub-agent'ы. Паттерн прост: лидер делегирует работу воркерам, каждый со своим изолированным context, и сливает результаты.

## Когда использовать Sub-Agent

Не каждая задача требует multi-agent-оркестрации. Sub-agent'ы добавляют сложность — порождение процессов, управление коммуникацией, слияние результатов. Используйте их, когда:

| Сигнал | Пример |
|--------|---------|
| **Задача не влезает в один context** | «Отрефакторить все 50 файлов сервисов под новый паттерн обработки ошибок» |
| **Независимая параллельная работа** | «Написать тесты для модулей A, B и C» — между ними нет зависимостей |
| **Доменная изоляция** | «Исследовать конкурентов, затем написать маркетинговый текст» — разные навыки, разный context |
| **Долгоиграющая фоновая работа** | «Мониторить этот CI-pipeline и чинить падения по мере появления» |

**Не** используйте sub-agent'ов для задач, где нужна плотная координация над общим состоянием. Два агента, одновременно правящих один файл, дадут конфликты. Последовательные tool-вызовы в одном context проще и надёжнее.

## Паттерн Leader-Worker

Самый практичный multi-agent-паттерн — три фазы:

```
Фаза 1: Plan          Фаза 2: Execute          Фаза 3: Merge
┌────────────┐        ┌──────────┐              ┌────────────┐
│   Leader   │─spawn─►│ Worker A │──result──┐   │   Leader   │
│  (планирует│        └──────────┘          │   │  (ревьюит, │
│  делегирует│─spawn─►┌──────────┐          ├──►│   мержит,  │
│   )        │        │ Worker B │──result──┘   │   отчёт)   │
│            │─spawn─►┌──────────┐          │   │            │
│            │        │ Worker C │──result──┘   └────────────┘
└────────────┘        └──────────┘
```

Лидер:
1. Анализирует задачу и разбивает на независимые подзадачи
2. Порождает воркер для каждой подзадачи с чёткой самодостаточной инструкцией
3. Ждёт завершения всех воркеров
4. Ревьюит и мержит результаты
5. Отчитывается пользователю

```python
import subprocess
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

@dataclass
class SubTask:
    name: str
    instruction: str
    working_dir: str | None = None

@dataclass
class SubResult:
    name: str
    success: bool
    output: str
    artifacts: list[str]  # Paths to files produced

class SubAgentSpawner:
    """Spawn and manage sub-agents as isolated processes."""

    def __init__(
        self,
        agent_command: str = "python -m agent",
        max_workers: int = 4,
        timeout: int = 300,
    ):
        self.agent_command = agent_command
        self.max_workers = max_workers
        self.timeout = timeout

    def spawn(self, tasks: list[SubTask]) -> list[SubResult]:
        """Spawn sub-agents for each task and collect results."""
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self._run_agent, task): task
                for task in tasks
            }
            for future in as_completed(futures):
                task = futures[future]
                try:
                    result = future.result(timeout=self.timeout)
                    results.append(result)
                except Exception as e:
                    results.append(SubResult(
                        name=task.name,
                        success=False,
                        output=f"Agent failed: {type(e).__name__}: {e}",
                        artifacts=[],
                    ))
        return results

    def _run_agent(self, task: SubTask) -> SubResult:
        """Run a single sub-agent in an isolated process."""
        # Each sub-agent gets its own working directory
        work_dir = task.working_dir or tempfile.mkdtemp(prefix=f"agent-{task.name}-")

        # Write the task instruction to a file the sub-agent reads
        task_file = os.path.join(work_dir, "TASK.md")
        with open(task_file, "w") as f:
            f.write(task.instruction)

        # Write a result file path for the sub-agent to populate
        result_file = os.path.join(work_dir, "RESULT.json")

        env = os.environ.copy()
        env["AGENT_TASK_FILE"] = task_file
        env["AGENT_RESULT_FILE"] = result_file
        env["AGENT_WORK_DIR"] = work_dir

        proc = subprocess.run(
            self.agent_command.split(),
            cwd=work_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

        # Read the result file if it exists
        if os.path.exists(result_file):
            with open(result_file) as f:
                result_data = json.load(f)
            return SubResult(
                name=task.name,
                success=result_data.get("success", True),
                output=result_data.get("output", ""),
                artifacts=result_data.get("artifacts", []),
            )

        return SubResult(
            name=task.name,
            success=proc.returncode == 0,
            output=proc.stdout[-5000:] or proc.stderr[-5000:],
            artifacts=[],
        )
```

## Общение через файлы

Sub-agent'ы не могут разделять memory — они выполняются в изолированных процессах со своими context window. Коммуникация идёт через файловую систему:

```python
import json
import time
from pathlib import Path

class FileInbox:
    """File-based message passing between agents."""

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def send(self, recipient: str, message: dict):
        """Write a message to a recipient's inbox."""
        inbox = self.base_dir / recipient / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        msg_file = inbox / f"{int(time.time() * 1000)}.json"
        msg_file.write_text(json.dumps(message, indent=2))

    def receive(self, agent_id: str) -> list[dict]:
        """Read and consume messages from this agent's inbox."""
        inbox = self.base_dir / agent_id / "inbox"
        if not inbox.exists():
            return []
        messages = []
        for msg_file in sorted(inbox.glob("*.json")):
            messages.append(json.loads(msg_file.read_text()))
            msg_file.unlink()  # Consume after reading
        return messages

    def claim(self, agent_id: str, task_id: str) -> bool:
        """Atomic claim — prevents two agents from working the same task."""
        claim_file = self.base_dir / "claims" / f"{task_id}.claimed"
        claim_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            # O_CREAT | O_EXCL = atomic create-if-not-exists
            fd = os.open(str(claim_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, agent_id.encode())
            os.close(fd)
            return True
        except FileExistsError:
            return False  # Another agent already claimed this task
```

Паттерн claim-файла важен: когда несколько воркеров могут взять одну задачу, атомарное создание файла работает как распределённый лок без БД.

## Изоляция Session

Каждый sub-agent получает полностью независимый context window. Это значит:

- **Нет общей memory** — результаты tools одного агента невидимы другим
- **Независимое состояние tools** — каждый агент грузит свои skills
- **Отдельные токен-бюджеты** — sub-agent может использовать полное окно 128K под свою задачу

```python
def prepare_sub_agent_context(task: SubTask, shared_context: dict) -> list[dict]:
    """Build an isolated context for a sub-agent."""
    return [
        {
            "role": "system",
            "content": (
                "You are a sub-agent executing a specific task. "
                "Complete the task and write results to RESULT.json.\n\n"
                f"Task: {task.instruction}"
            ),
        },
        {
            "role": "system",
            "content": f"[Shared context]\n{json.dumps(shared_context)}",
        },
    ]
```

Dict shared-context передаёт только то, что нужно sub-agent'у — конвенции проекта, расположение файлов, ограничения. Не передавайте весь диалог лидера; это убивает смысл изоляции.

## Git Worktrees для параллельных правок кода

Когда sub-agent'ам нужно одновременно менять код, git worktrees предотвращают конфликты веток:

```python
import subprocess

def create_worktree(repo_path: str, branch_name: str) -> str:
    """Create a git worktree for a sub-agent to work in."""
    worktree_path = f"/tmp/worktrees/{branch_name}"
    subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, worktree_path],
        cwd=repo_path,
        check=True,
    )
    return worktree_path

def merge_worktrees(repo_path: str, branches: list[str], target: str = "main"):
    """Merge all sub-agent branches back into the target branch."""
    subprocess.run(["git", "checkout", target], cwd=repo_path, check=True)
    for branch in branches:
        result = subprocess.run(
            ["git", "merge", "--no-ff", branch, "-m", f"Merge {branch}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Conflict merging {branch}: {result.stderr}")
            subprocess.run(["git", "merge", "--abort"], cwd=repo_path)

def cleanup_worktrees(repo_path: str, branches: list[str]):
    """Remove worktrees and branches after merge."""
    for branch in branches:
        worktree_path = f"/tmp/worktrees/{branch}"
        subprocess.run(
            ["git", "worktree", "remove", worktree_path],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "branch", "-d", branch],
            cwd=repo_path,
            check=True,
        )
```

Каждый sub-agent получает свой worktree (полную рабочую копию на уникальной ветке). Можно свободно править файлы, не наступая друг другу. Лидер потом мержит ветки.

## Частые ошибки

- **Избыточная декомпозиция** — дробление 5-минутной задачи на 3 sub-agent'ов добавляет больше оверхеда, чем экономит. Берите sub-agent'ов для задач от 10+ минут или там, где реально нужен параллелизм.
- **Разделяемое mutable-состояние** — два sub-agent'а, правящих один файл, гарантированно дают конфликты. Проектируйте задачи так, чтобы каждый агент работал над своими файлами или секциями.
- **Неограниченное порождение** — лидер, порождающий sub-agent'ов, которые порождают своих sub-agent'ов, создаёт неуправляемое дерево. Ограничивайте глубину 1–2 уровнями.
- **Без таймаута на воркерах** — зависший sub-agent повесит весь pipeline. Всегда ставьте таймауты и обрабатывайте случай падения/таймаута воркера.
- **Слишком много context** — вываливание полного диалога лидера в каждого sub-agent'а тратит токены и путает воркер. Давайте каждому sub-agent'у только то, что нужно под его задачу.

## Что почитать

- [Anthropic: Building Effective Agents — Multi-Agent](https://www.anthropic.com/research/building-effective-agents) — паттерны оркестрации для production multi-agent-систем
- [OpenAI: Agents SDK — Handoffs](https://openai.github.io/openai-agents-python/) — паттерны делегирования и handoff агентов
- [Git Worktrees Documentation](https://git-scm.com/docs/git-worktree) — параллельные рабочие директории для concurrent-разработки
