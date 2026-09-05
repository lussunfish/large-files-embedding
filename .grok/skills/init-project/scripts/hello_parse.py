"""Parse hello.txt sections. Shared by from_hello.py and validate.py."""

from __future__ import annotations

import re

UC_LINE = re.compile(r"^-\s*(UC-\d+)(?:\s*[:：]\s*|\s+)(.+)$")
FEATURE_BULLET = re.compile(r"^-\s+(.+)$")
ENV_LINE = re.compile(r"^-\s*([A-Z][A-Z0-9_]+)\s*:")
ENV_FULL = re.compile(r"^-\s*([A-Z][A-Z0-9_]+)\s*:\s*(.*)$")
ENV_VALUE_TOKEN = re.compile(r"^[A-Za-z0-9_.=+-]+$")
PY_IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
KNOWN_LANGS = (
    (re.compile(r"\bpython\b", re.I), "Python"),
    (re.compile(r"\bgolang\b|\bgo\b", re.I), "Go"),
    (re.compile(r"\brust\b", re.I), "Rust"),
    (re.compile(r"typescript|\bnode\b|\.ts\b", re.I), "TypeScript"),
    (re.compile(r"\bkotlin\b", re.I), "Kotlin"),
    (re.compile(r"\bjava\b", re.I), "Java"),
    (re.compile(r"\bruby\b", re.I), "Ruby"),
    (re.compile(r"\bphp\b", re.I), "PHP"),
    (re.compile(r"\bc#\b|\bdotnet\b|\.net\b", re.I), "C#"),
    (re.compile(r"\bswift\b", re.I), "Swift"),
    (re.compile(r"\bjavascript\b|\bjs\b", re.I), "JavaScript"),
)
FASTAPI_FRAMEWORKS = {"fastapi", "starlette"}
SECTION_ALIASES = {
    "프로젝트명": ("Project name", "Project"),
    "한 줄 설명": ("One-line description", "Summary"),
    "목표": ("Goals",),
    "비목표": ("Non-goals", "Out of scope"),
    "기술 스택": ("Tech stack", "Stack"),
    "실행 모드": ("Runtime", "Run mode"),
    "기능": ("Features", "Use cases"),
    "환경 변수": ("Environment variables", "Env"),
    "환경 변수 (선택)": ("Environment variables", "Env"),
    "GPU": ("GPU",),
    "Grok에게 추가 지시": ("Notes for Grok", "Agent notes"),
    "리스크": ("Risks",),
    "리스크 & 의존성": ("Risks", "Risks & dependencies"),
    "아키텍처": ("Architecture",),
    "작성자": ("Author",),
}


def section(text: str, heading: str) -> str:
    names = (heading, *SECTION_ALIASES.get(heading, ()))
    for name in names:
        pattern = re.compile(rf"^## {re.escape(name)}\s*$", re.M | re.I)
        m = pattern.search(text)
        if not m:
            continue
        start = m.end()
        nxt = re.search(r"^## ", text[start:], re.M)
        return text[start : start + nxt.start() if nxt else None]
    return ""


def first_value(body: str) -> str:
    for line in body.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("- "):
            raw = raw[2:].strip()
        return raw
    return ""


def parse_hello_features(hello: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Parse `## 기능` bullets. Unlabeled lines get UC-0N in document order."""
    body = section(hello, "기능")
    pending: list[tuple[str | None, str]] = []
    used: set[int] = set()
    for line in body.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        labeled = UC_LINE.match(raw)
        if labeled:
            uid, name = labeled.group(1), labeled.group(2).strip()
            pending.append((uid, name))
            used.add(int(re.search(r"\d+", uid).group()))
            continue
        bullet = FEATURE_BULLET.match(raw)
        if bullet:
            name = bullet.group(1).strip()
            if name:
                pending.append((None, name))
    assigned: list[str] = []
    found: list[tuple[str, str]] = []
    n = 1
    for uid, name in pending:
        if uid:
            found.append((uid, name))
            continue
        while n in used:
            n += 1
        new_id = f"UC-{n:02d}"
        found.append((new_id, name))
        assigned.append(new_id)
        used.add(n)
        n += 1
    return found, assigned


def parse_hello_ucs(hello: str) -> list[tuple[str, str]]:
    ucs, _assigned = parse_hello_features(hello)
    return ucs


def parse_hello_envs(hello: str) -> list[str]:
    return [item["name"] for item in parse_hello_env_items(hello)]


def env_example_from_rest(rest: str) -> str:
    """Use the first token only when it looks like a value, not a description."""
    rest = rest.strip()
    if not rest:
        return ""
    first = rest.split()[0].strip("()[],")
    if re.match(r"^https?://", first) or first.startswith("/") or first.startswith("./"):
        return first
    paren = re.match(r"^([A-Za-z0-9_.=+-]+)\s+\((.+)\)\s*$", rest)
    if paren:
        return paren.group(1)
    if ENV_VALUE_TOKEN.match(first) and not re.search(r"[가-힣]", first):
        return first
    return ""


def parse_hello_env_items(hello: str) -> list[dict[str, str]]:
    body = section(hello, "환경 변수 (선택)") or section(hello, "환경 변수")
    items: list[dict[str, str]] = []
    for line in body.splitlines():
        m = ENV_FULL.match(line.strip())
        if not m:
            continue
        name, rest = m.group(1), m.group(2).strip()
        items.append(
            {
                "name": name,
                "desc": rest or name,
                "required": "no",
                "example": env_example_from_rest(rest),
            }
        )
    return items


def parse_hello_risks(hello: str) -> list[dict[str, str]]:
    body = section(hello, "리스크") or section(hello, "리스크 & 의존성")
    risks: list[dict[str, str]] = []
    for line in body.splitlines():
        raw = line.strip()
        if not raw.startswith("- "):
            continue
        item = raw[2:].strip()
        if item:
            risks.append({"item": item, "impact": "—", "mitigation": "—"})
    return risks


def has_gpu(hello: str) -> bool:
    """True only when hello has a non-empty `## GPU` section. Do not scan 비목표/comments."""
    return bool(section(hello, "GPU").strip())


def runtime_mode_from_hello(hello: str) -> str | None:
    body = section(hello, "실행 모드").strip().lower()
    if not body:
        return None
    if "uv-native" in body:
        return "uv-native"
    if "docker-compose" in body:
        return "docker-compose"
    return None


def language_from_hello(hello: str) -> str | None:
    """Return a language named in `## 기술 스택`. Python wins if both are present."""
    stack = section(hello, "기술 스택")
    if not stack.strip():
        return None
    if re.search(r"\bpython\b", stack, re.I):
        return "Python"
    for pattern, name in KNOWN_LANGS:
        if name == "Python":
            continue
        if pattern.search(stack):
            return name
    return None


def resolved_language(hello: str) -> str:
    return language_from_hello(hello) or "Python"


def resolved_runtime_mode(hello: str, language: str) -> str:
    """Python + ## GPU overrides ## 실행 모드 (MPS is not available in Docker)."""
    gpu = has_gpu(hello)
    hello_mode = runtime_mode_from_hello(hello)
    if gpu and language == "Python":
        return "uv-native"
    return hello_mode or "docker-compose"


def python_package_name(project_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", project_name.lower()).strip("_")
    if slug and slug[0].isdigit():
        slug = f"p_{slug}"
    return slug if slug and PY_IDENT.match(slug) else "app"


def pep508_name(python_package: str) -> str:
    raw = (python_package or "app").strip().lower().replace("_", "-")
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-.")
    if not raw or not re.match(r"^[a-z0-9]", raw):
        return "app"
    return raw


def is_fastapi_framework(web: str) -> bool:
    return (web or "").strip().lower() in FASTAPI_FRAMEWORKS


def web_framework_from_hello(hello: str, language: str) -> str:
    stack = section(hello, "기술 스택")
    if re.search(r"\bfastapi\b", stack, re.I):
        return "FastAPI"
    if re.search(r"\bstarlette\b", stack, re.I):
        return "Starlette"
    if re.search(r"\bflask\b", stack, re.I):
        return "Flask"
    if re.search(r"\bdjango\b", stack, re.I):
        return "Django"
    if language != "Python":
        return "—"
    blob = (
        stack
        + section(hello, "목표")
        + section(hello, "한 줄 설명")
        + section(hello, "기능")
    )
    mentions_http = re.search(r"fastapi|starlette|rest\s*api|/api|\bapi\b", blob, re.I)
    if re.search(r"\btyper\b", stack, re.I) and not mentions_http:
        return "—"
    return "FastAPI"


def cli_framework_from_hello(hello: str, language: str) -> str:
    if language == "Python":
        return "Typer"
    stack = section(hello, "기술 스택")
    if re.search(r"\btyper\b", stack, re.I):
        return "Typer"
    return "—"


def database_from_hello(hello: str) -> str:
    non = section(hello, "비목표")
    if re.search(r"postgres", non, re.I):
        return "—"
    stack = section(hello, "기술 스택")
    if re.search(r"postgres", stack, re.I):
        return "PostgreSQL"
    return "—"


def snake_slug(uc_id: str, name: str) -> str:
    tail = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    num = uc_id.lower().replace("-", "_")
    return tail or num


ENTITY_SUFFIXES = {
    "api",
    "app",
    "service",
    "server",
    "backend",
    "cli",
    "web",
    "src",
    "lib",
}

VERB_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"스트리밍|stream", re.I), "stream"),
    (re.compile(r"로드|언로드|unload|\bload\b", re.I), "load"),
    (re.compile(r"삭제|delete|remove", re.I), "delete"),
    (re.compile(r"생성|create|추가|add", re.I), "create"),
    (re.compile(r"목록|리스트|list|조회|검색|search|\bget\b", re.I), "list"),
    (re.compile(r"완료|complete|finish", re.I), "complete"),
    (re.compile(r"수정|update|edit", re.I), "update"),
)


def pascalize(slug: str) -> str:
    return "".join(part.capitalize() for part in slug.split("_") if part)


def entity_slug(pkg: str) -> str:
    """Shared domain module from the Python package (todo_api → todo)."""
    if not pkg or pkg == "—":
        return "app"
    parts = [p for p in pkg.split("_") if p]
    while len(parts) > 1 and parts[-1] in ENTITY_SUFFIXES:
        parts.pop()
    return parts[-1] if parts else "app"


def pluralize(slug: str) -> str:
    if not slug:
        return "items"
    if slug.endswith("s"):
        return slug
    if slug.endswith("y") and len(slug) > 1 and slug[-2] not in "aeiou":
        return slug[:-1] + "ies"
    if slug.endswith(("ch", "sh", "x", "z")):
        return slug + "es"
    return slug + "s"


def verb_from_name(name: str) -> str:
    for pattern, verb in VERB_RULES:
        if pattern.search(name):
            return verb
    english = re.findall(r"[a-z]+", name.lower())
    if english:
        return english[0]
    return "run"


ACCEPTANCE_RULES: tuple[tuple[re.Pattern[str], dict[str, str]], ...] = (
    (
        re.compile(r"스트리밍|stream", re.I),
        {
            "given": "모델이 사용 가능한 상태이다",
            "when": "{name} 요청을 보낸다",
            "then": "응답이 스트리밍된다",
            "failure": "빈 입력은 거부한다",
            "red": "빈 입력이면 도메인 예외",
        },
    ),
    (
        re.compile(r"로드|언로드|unload|\bload\b", re.I),
        {
            "given": "대상 경로가 있다",
            "when": "{name}을 요청한다",
            "then": "대상 상태가 바뀐다",
            "failure": "없는 경로는 거부한다",
            "red": "없는 경로면 도메인 예외",
        },
    ),
    (
        re.compile(r"삭제|delete|remove", re.I),
        {
            "given": "대상 항목이 있다",
            "when": "{name} 요청을 보낸다",
            "then": "항목이 제거된다",
            "failure": "없는 id는 거부한다",
            "red": "없는 id면 도메인 예외",
        },
    ),
    (
        re.compile(r"생성|create|추가|add", re.I),
        {
            "given": "유효한 입력이 있다",
            "when": "{name} 요청을 보낸다",
            "then": "자원이 저장되고 식별자가 반환된다",
            "failure": "빈 필수 값은 거부한다",
            "red": "빈 필수 값이면 도메인 예외",
        },
    ),
    (
        re.compile(r"목록|리스트|list|조회|검색|search|\bget\b", re.I),
        {
            "given": "항목이 여러 개 있다",
            "when": "{name} 요청을 보낸다",
            "then": "조건에 맞는 항목만 반환된다",
            "failure": "알 수 없는 필터 값은 거부한다",
            "red": "필터가 대상 외 항목을 제외한다",
        },
    ),
    (
        re.compile(r"완료|complete|finish", re.I),
        {
            "given": "미완료 항목이 있다",
            "when": "{name} 요청을 보낸다",
            "then": "상태가 완료로 바뀐다",
            "failure": "없는 id는 거부한다",
            "red": "없는 id면 도메인 예외",
        },
    ),
)


def infer_acceptance(name: str) -> dict[str, str]:
    """GWT/red from the feature name so PLAN TDD is usable before LLM enrichment."""
    for pattern, tmpl in ACCEPTANCE_RULES:
        if pattern.search(name):
            return {key: val.replace("{name}", name) for key, val in tmpl.items()}
    return {
        "given": f"{name}을 수행할 수 있는 상태이다",
        "when": f"{name}을 요청한다",
        "then": f"{name} 결과가 반영된다",
        "failure": f"{name}의 잘못된 입력은 거부한다",
        "red": f"{name} 실패/경계",
    }


def default_port_names(entity: str, language: str) -> tuple[str | None, str | None]:
    if language != "Python" or not entity or entity == "—":
        return None, None
    pascal = pascalize(entity)
    if not pascal:
        return None, None
    return f"{pascal}Repository", f"InMemory{pascal}Repository"


def uniquify_filename(name: str, used: set[str]) -> str:
    if name not in used:
        return name
    stem, dot, ext = name.rpartition(".")
    base = stem or name
    suffix = f".{ext}" if dot else ""
    n = 2
    while True:
        candidate = f"{base}_{n}{suffix}"
        if candidate not in used:
            return candidate
        n += 1


def shared_layer_files(
    *,
    entity: str,
    name: str,
    pkg: str,
    language: str,
    has_http: bool,
    used_apps: set[str],
) -> dict[str, str | None]:
    """One domain/port per BC; one application module per UC."""
    if language != "Python":
        return {
            "domain": "—",
            "application": "—",
            "infrastructure": "—",
            "presentation": "—",
            "port": None,
            "adapter": None,
            "unit_test": "—",
            "integration_test": "—",
        }
    verb = verb_from_name(name)
    noun = pluralize(entity) if verb == "list" else entity
    application = uniquify_filename(f"{verb}_{noun}.py", used_apps)
    used_apps.add(application)
    stem = application[:-3] if application.endswith(".py") else application
    port, adapter = default_port_names(entity, language)
    presentation = f"http/{pluralize(entity)}.py" if has_http else "cli/main.py"
    return {
        "domain": f"{entity}.py",
        "application": application,
        "infrastructure": f"in_memory_{entity}_repository.py",
        "presentation": presentation,
        "port": port,
        "adapter": adapter,
        "unit_test": f"tests/unit/{pkg}/test_{stem}.py",
        "integration_test": f"tests/integration/{pkg}/test_{stem}.py",
    }
