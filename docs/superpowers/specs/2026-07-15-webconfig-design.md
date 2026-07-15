# Webconfig — Design Document

> CLI-утилита для редактирования конфигурационных файлов (TOML/JSON/ENV) через Web UI.
> Дата: 2026-07-15

---

## 1. Overview

**Webconfig** — Python CLI-утилита, запускающая локальный веб-сервер с интерфейсом для редактирования конфигурационного файла. Поддерживает форматы TOML, JSON, ENV и опциональную валидацию по JSON Schema.

### Целевой сценарий

```bash
$ webconfig config.toml --port 8080 --schema schema.json
 * Server started at http://127.0.0.1:8080
 * Opening browser...
 * Press Ctrl+C to stop
```

Разработчик открывает браузер, видит автосгенерированную форму на основе структуры конфига, редактирует поля, нажимает Save — файл сохраняется. Схема даёт подсказки (enum → выпадайки), описания полей (тултипы) и валидацию перед сохранением.

---

## 2. Requirements

### Функциональные

| ID | Требование |
|----|-----------|
| R1 | Запуск веб-сервера на указанном порту из командной строки |
| R2 | Парсинг конфигурационного файла в формате TOML, JSON, ENV |
| R3 | Автоматическая генерация HTML-формы на основе структуры конфига |
| R4 | Редактирование полей формы (текст, число, bool, enum, вложенные объекты, массивы) |
| R5 | Сохранение изменений обратно в файл (ручное, по кнопке Save) |
| R6 | Опциональная поддержка JSON Schema: типы полей, enum, default, описание, min/max, required |
| R7 | Валидация перед сохранением: типы значений + JSON Schema |
| R8 | Обработка ошибок парсинга: показ сообщения об ошибке, форма не рендерится |
| R9 | Автооткрытие браузера при старте сервера (можно отключить флагом `--no-browser`) |
| R10 | Остановка сервера по Ctrl+C |
| R11 | Перечитывание файла с диска (кнопка Reload) |
| R12 | Переключение цветовой схемы light/dark (авто по системе или флаг `--preset`) |
| R13 | Вложенные объекты сворачиваются в `<details>` |
| R14 | Массивы с возможностью добавления/удаления элементов |

### Нефункциональные

| ID | Требование |
|----|-----------|
| N1 | Python 3.11+ (tomllib в stdlib) |
| N2 | Flask + Jinja2 для серверного рендеринга |
| N3 | HTMX для интерактивности без кастомного JS |
| N4 | S4 (Система 4) — CSS-система для визуала |
| N5 | Минимум зависимостей |
| N6 | Работает на localhost (127.0.0.1), без внешнего доступа |

### Не входит в scope

- Редактирование нескольких файлов одновременно (одна сессия = один файл)
- Сохранение комментариев в конфигах (форма их не отображает)
- Аутентификация / авторизация (локальный инструмент)
- Конвертация между форматами
- Real-time collaboration

---

## 3. Architecture

### Технологический стек

| Слой | Технология |
|------|-----------|
| CLI | Python `argparse` |
| Сервер | Flask 3.x |
| Шаблоны | Jinja2 (встроен в Flask) |
| Интерактивность | HTMX 2.x (~14KB) |
| CSS-система | S4 v0.3 (light/dark пресеты) |
| TOML | `tomllib` (Python 3.11 stdlib) |
| JSON | `json` (stdlib) |
| ENV | Собственный парсер (key=value) |
| JSON Schema | `jsonschema` |

### Структура проекта

```
webconfig/
├── pyproject.toml
├── README.md
├── webconfig/
│   ├── __init__.py
│   ├── __main__.py           # точка входа: python -m webconfig
│   ├── cli.py                # argparse
│   ├── server.py             # Flask-приложение, маршруты
│   ├── parser.py             # ConfigParser: TOML/JSON/ENV → dict
│   ├── form_generator.py     # dict + schema → FieldModel (дерево)
│   ├── validator.py          # Валидация типов + jsonschema
│   ├── templates/
│   │   ├── base.html         # <html> с S4 и HTMX
│   │   └── editor.html       # Форма с S4-классами
│   └── static/
│       ├── s4/               # S4 CSS/JS (vendored)
│       │   ├── css/
│       │   │   ├── elements.css
│       │   │   ├── desktop/
│       │   │   │   ├── landscape.css
│       │   │   │   ├── portrait.css
│       │   │   │   └── config.css
│       │   │   ├── tablet/
│       │   │   │   ├── landscape.css
│       │   │   │   ├── portrait.css
│       │   │   │   └── config.css
│       │   │   └── mobile/
│       │   │       ├── landscape.css
│       │   │       ├── portrait.css
│       │   │       └── config.css
│       │   └── js/
│       │       ├── device-state.min.js
│       │       └── s4.min.js
│       └── htmx.min.js       # HTMX (vendored или CDN)
├── tests/
│   ├── fixtures/
│   │   ├── config.toml
│   │   ├── config.json
│   │   ├── config.env
│   │   └── schema.json
│   ├── test_parser.py
│   ├── test_form_generator.py
│   ├── test_validator.py
│   └── test_server.py
```

---

## 4. Component Design

### 4.1 CLI (`cli.py`)

```python
import argparse

def parse_args():
    parser = argparse.ArgumentParser(
        prog="webconfig",
        description="Edit config files (TOML/JSON/ENV) via Web UI"
    )
    parser.add_argument("config", help="Path to config file (.toml, .json, .env)")
    parser.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--schema", default=None, help="Path to JSON Schema file")
    parser.add_argument("--preset", choices=["light", "dark", "auto"], default="auto",
                        help="Color preset (default: auto = system preference)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    return parser.parse_args()
```

Формат файла определяется по расширению: `.toml` → TOML, `.json` → JSON, `.env` → ENV.

### 4.2 Парсер (`parser.py`)

Единый интерфейс:

```python
@dataclass
class ConfigFile:
    path: str
    format: str   # "toml" | "json" | "env"
    data: dict    # всегда нормализован в dict

class ConfigParser:
    @staticmethod
    def parse(path: str) -> ConfigFile:
        """Определяет формат по расширению, парсит в dict.
        При ошибке синтаксиса — ConfigParseError."""
        ...

    @staticmethod
    def serialize(data: dict, path: str) -> str:
        """dict → строка в нужном формате (для записи в файл)."""
        ...
```

**ENV parser**: плоский key=value, строки без кавычек, комментарии `#` игнорируются. Вложенности нет.

**TOML/NULL/Boolean обработка**: TOML-значения мапятся в Python-типы (`int`, `float`, `bool`, `str`, `list`, `dict`). При сериализации обратно в TOML используется кастомный writer (или `tomli_w`).

### 4.3 Модель формы (`form_generator.py`)

```python
@dataclass
class Field:
    key: str              # ключ в конфиге
    label: str            # человеческое название (из ключа или schema.title)
    field_type: str       # "text" | "number" | "boolean" | "select" | "textarea" | "object" | "array"
    value: Any            # текущее значение
    depth: int            # 0 = корень, 1 = первый уровень, ...
    path: str             # полный путь: "server.host"

    # Из JSON Schema (опционально)
    description: str | None = None
    enum: list[str] | None = None
    default: Any = None
    required: bool = False
    constraints: dict = field(default_factory=dict)  # min, max, pattern

    # Для object/array
    children: list["Field"] = field(default_factory=list)
    # Для array — тип элементов:
    item_type: str | None = None


class FormGenerator:
    def generate(self, data: dict, schema: dict | None = None) -> Field:
        """Строит дерево Field из dict + опциональной схемы."""
        ...
```

**Логика типов**:
- Без схемы: `int/float` → number, `bool` → boolean, `str` (длинный) → textarea, `str` (короткий) → text, `list` → array, `dict` → object
- Со схемой: `FormGenerator` обходит data-дерево и schema-дерево параллельно.
  - Для верхнего уровня: `schema["properties"][key]`
  - Для вложенного `server.host`: `schema["properties"]["server"]["properties"]["host"]`
  - Тип берётся из `schema_node["type"]`
- `enum` в схеме → `field_type="select"`, варианты из `schema["enum"]`
- `default` из схемы подставляется для отсутствующих ключей

### 4.4 Сервер (`server.py`)

```python
def create_app(config_path: str, schema: dict | None, preset: str) -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def editor():
        """GET / — рендерит форму."""
        config = ConfigParser.parse(config_path)
        field_tree = FormGenerator().generate(config.data, schema)
        return render_template("editor.html",
                               field=field_tree,
                               filename=os.path.basename(config_path),
                               preset=preset)

    @app.route("/save", methods=["POST"])
    def save():
        """POST /save — принимает форму, валидирует, сохраняет файл.
        Возвращает HTML формы (с ошибками или с flash-успехом)."""
        ...

    @app.route("/api/validate/<path:field_path>", methods=["POST"])
    def validate_field(field_path):
        """POST /api/validate/<path> — валидация одного поля.
        Возвращает пустой ответ или HTML с ошибкой."""
        ...

    @app.route("/api/array/add/<path:array_path>", methods=["POST"])
    def array_add(array_path):
        """POST /api/array/add/<path> — добавляет элемент в массив.
        Возвращает HTML секции массива."""
        ...

    @app.route("/api/array/remove/<path:array_path>/<int:index>", methods=["DELETE"])
    def array_remove(array_path, index):
        """DELETE /api/array/remove/<path>/<idx> — удаляет элемент.
        Возвращает HTML секции массива."""
        ...

    return app
```

### 4.5 Шаблоны

**base.html** — обёртка с S4 и HTMX:

```html
<!DOCTYPE html>
<html lang="en" {% if preset != "auto" %}preset="{{ preset }}"{% endif %}>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>webconfig — {{ filename }}</title>
    <script src="/static/s4/js/s4.min.js"></script>
    <script>S4()</script>
    <script src="/static/htmx.min.js"></script>
</head>
<body>
    {% block content %}{% endblock %}
</body>
</html>
```

**editor.html** — форма:

- Header с именем файла, кнопками Save/Reload, индикатором пресета
- Основная область: рекурсивный рендеринг дерева Field
- Каждый object → `<details open>` с заголовком-ключом
- Каждый array → список полей `[index]` + кнопка `+ Add`
- Поля ввода: `<input>`, `<select>`, `<textarea>`, `<input type="checkbox">` с S4-стилизацией
- Ошибки: `<small class="color">` — S4 Formula 3 даст акцентный цвет `--negative`
- HTMX-атрибуты: `hx-post`, `hx-swap`, `hx-target`, `hx-trigger`
- Flash-сообщения: `<e-badge>` от S4

**Визуальная раскладка (light preset)**:

```
┌──────────────────────────────────────────────────────────┐
│  config.toml                [Save]  [Reload]    light ○ ●│
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ▸ server ────────────────────────────────────── object  │
│    host        ┌──────────────────────────────┐  string  │
│                │ 0.0.0.0                      │          │
│                └──────────────────────────────┘          │
│    port        ┌──────────────────────────────┐  number  │
│                │ 8080                         │          │
│                └──────────────────────────────┘          │
│    features─────────────────────────── array[2]          │
│      [0]       ┌──────────────────────────────┐          │
│                │ a                            │          │
│                └──────────────────────────────┘          │
│      [1]       ┌──────────────────────────────┐          │
│                │ b                            │ [x]      │
│                └──────────────────────────────┘          │
│      [+ Add item]                                       │
│                                                          │
│  ▸ database ────────────────────────────────── object   │
│                                                          │
│  ▸ logging ─────────────────────────────────── object   │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 5. Data Flow

### GET / — загрузка редактора

```
ConfigParser.parse(path)       → ConfigFile(format, data)
FormGenerator.generate(data)   → Field (дерево)
                                 ↓
render_template("editor.html")  → HTML с S4-классами
                                 ↓
                            Браузер отображает форму
```

### POST /save — сохранение

```
Form data (flat key=value)     → Парсим в nested dict
                                 ↓
Validator.validate(dict)        → Проверка типов (int для number и т.д.)
                               ┌─ OK: продолжаем
                               └─ Ошибки: рендерим editor.html с ошибками → swap в #editor
                                 ↓
Validator.validate_json_schema  → jsonschema.validate()
                               ┌─ OK: продолжаем
                               └─ Ошибки: рендерим editor.html с ошибками → swap в #editor
                                 ↓
ConfigParser.serialize(dict)    → Строка в формате файла
                                 ↓
write(file)                     → Записываем на диск
                                 ↓
render_template("editor.html")  → Форма с flash-сообщением ✓ → swap в #editor
```

### POST /api/validate/<path> — валидация поля

```
Значение из form + путь       → Парсим, валидируем одно поле
                               ┌─ OK: return "" (пустой ответ)
                               └─ Ошибка: return "<small class='color'>msg</small>"
                                 ↓
                            HTMX вставляет в .error-msg рядом с полем
```

### POST /api/array/add/<path> — добавить элемент массива

```
Путь массива                   → Находим в дереве Field
                                → Добавляем дочерний Field с default-значением
                                → Перерендериваем секцию массива
                                → HTMX swap outerHTML #array-<path>
```

---

## 6. Error Handling

### Ошибки при запуске

| Ошибка | Поведение |
|--------|-----------|
| Файл не найден | `sys.exit("Error: file not found: ...")` |
| Неподдерживаемое расширение | `sys.exit("Error: unsupported format. Use .toml, .json, or .env")` |
| Ошибка парсинга файла | `sys.exit("Error: failed to parse: ...")` |
| Ошибка загрузки схемы | `sys.exit("Error: invalid JSON Schema: ...")` |
| Порт занят | Flask error → `sys.exit("Error: port N is already in use")` |

### Ошибки во время работы

| Ситуация | Поведение |
|-----------|-----------|
| Синтаксическая ошибка TOML/JSON при открытии | Страница с сообщением, форма не рендерится |
| Невалидное значение поля (тип) | Ошибка на поле, форма перерендеривается |
| Невалидное значение по схеме | Ошибка на поле, форма перерендеривается |
| Файл удалён с диска во время сессии | При Save → создаётся заново; при Reload → ошибка |
| Файл изменён снаружи | Reload перечитывает; несохранённые изменения теряются (предупреждение) |
| Пустой файл | Пустая форма с кнопкой `[+ Add key]` |
| Глубокий nesting (>8 уровней) | Сворачиваем в `<details>` от depth ≥ 4 |
| Схема не соответствует данным | Форма показывается как есть + ошибки валидации схемы |

---

## 7. JSON Schema Mapping

| JSON Schema | Field |
|-------------|-------|
| `type: "string"` | `field_type = "text"` (или `"textarea"` для длинных) |
| `type: "number"` / `"integer"` | `field_type = "number"` |
| `type: "boolean"` | `field_type = "boolean"` → checkbox |
| `type: "object"` | `field_type = "object"`, дети из `properties` |
| `type: "array"` | `field_type = "array"`, тип элементов из `items` |
| `enum: [...]` | `field_type = "select"`, варианты из enum |
| `default` | Подставляется для отсутствующих ключей |
| `description` | Тултип (атрибут `title`) |
| `title` | Переопределяет `label` |
| `required` | Помечает поле звёздочкой, валидирует наличие |
| `minimum` / `maximum` | `constraints` → валидация числа |
| `minLength` / `maxLength` | `constraints` → валидация строки |
| `pattern` | `constraints` → regex-валидация строки |

---

## 8. CLI Usage Examples

```bash
# Минимальный вызов
webconfig config.toml

# С указанием порта
webconfig config.json --port 9090

# Со схемой
webconfig config.toml --schema schema.json

# Тёмная тема принудительно
webconfig config.env --preset dark

# Без открытия браузера
webconfig config.toml --no-browser

# Полная справка
webconfig --help
```

---

## 9. Testing Strategy

| Слой | Что тестируем | Фреймворк |
|------|--------------|-----------|
| `parser.py` | Парсинг TOML → dict, JSON → dict, ENV → dict | `pytest` |
| `parser.py` | Ошибки синтаксиса (битый TOML, JSON с дубликатами) | `pytest` |
| `parser.py` | Сериализация dict → TOML/JSON/ENV | `pytest` |
| `form_generator.py` | dict → Field tree: типы, глубина, enum | `pytest` |
| `form_generator.py` | dict + schema → Field tree: доп. метаданные | `pytest` |
| `validator.py` | Валидация типов, jsonschema | `pytest` |
| `server.py` | GET /: рендеринг, код 200 | `pytest` + `Flask.test_client` |
| `server.py` | POST /save: сохранение, проверка файла | `pytest` + `Flask.test_client` |
| `server.py` | POST /save: ошибки валидации, ответ с ошибкой | `pytest` + `Flask.test_client` |
| `server.py` | API array add/remove | `pytest` + `Flask.test_client` |

**Тестовые фикстуры** — в `tests/fixtures/`:
- `config.toml` — типичный TOML с вложенными таблицами и массивами
- `config.json` — эквивалентный JSON
- `config.env` — плоский ENV
- `schema.json` — JSON Schema с разными типами, enum, constraints

---

## 10. Dependencies

```toml
[project]
name = "webconfig"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "flask>=3.0",
    "jsonschema>=4.20",
]

[project.scripts]
webconfig = "webconfig.cli:main"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]
```

**HTMX** — vendored (один файл `htmx.min.js`, ~14KB) или CDN. Решение: vendored для работы без интернета.

**S4** — vendored из [релиза v0.3.0](https://github.com/s4-design/s4/releases/tag/v0.3.0). Лицензия CC BY-NC-SA — допустимо для dev-инструмента.

**TOML writer**: для сериализации dict → TOML может потребоваться `tomli-w` или собственная реализация (TOML достаточно прост для написания writer-а без внешней зависимости).

---

## 11. S4 Integration Notes

### Как S4 подключается

1. S4 CSS/JS копируются в `webconfig/static/s4/` из релиза
2. В `<head>` подключается `s4.min.js` + вызов `S4()` (определяет устройство, загружает CSS)
3. Перед вызовом `S4()` на `<html>` устанавливается `[preset=light]` или `[preset=dark]` (если `--preset` не `auto`)
4. S4 автоматически определяет device (desktop/tablet/mobile) и ориентацию → грузит соответствующие CSS

### S4-классы в шаблонах

- **Элементы**: `<button>`, `<input>`, `<select>`, `<details>`, `<fieldset>`, `<label>`, `<table>` — S4 стилизует нативно через `elements.css`
- **Кастомные элементы**: `<e-badge>` для flash-сообщений
- **Утилитарные классы** (Formula 1/2): для раскладки — `d_l_display--flex`, `d_l_gap--md`, `d_l_padding--md`, `d_l_flex-direction--column`
- **Formula 3** (переменные): `.color`, `.background-color` — для привязки к цветам пресета
- **Ошибки**: `.border-color` с `--negative` через пресет

### S4 и HTMX — не конфликтуют

S4 — CSS + device-detection JS. HTMX — обмен HTML с сервером. Они на разных слоях, конфликта нет.

---

## 12. Open Questions / TBD

- **TOML writer**: использовать `tomli-w` или написать свой (TOML writer — ~100 строк)?
  - Решение: написать свой writer для TOML. Зависимость `tomli-w` избыточна для задачи.
- **ENV writer**: нужен ли writer или достаточно `dict → key=value`?
  - Решение: простой writer, строки без кавычек, `\n`-разделитель.
