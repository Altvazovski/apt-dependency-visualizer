"""Чтение тестового JSON-репозитория с заглавными именами пакетов."""

import json
from pathlib import Path
import re


def unique_object(pairs):
    """Отклонить повторяющиеся ключи JSON до создания словаря."""
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"Имя пакета {name} повторяется в JSON.")
        result[name] = value
    return result


def validate_node_name(name):
    """Проверить, что имя состоит из заглавных латинских букв."""
    if not isinstance(name, str) or not re.fullmatch(r"[A-Z]+", name):
        raise ValueError("Имена тестовых пакетов должны состоять из букв A-Z.")


def validate_test_graph(graph):
    """Проверить структуру графа, ссылки и повторы рёбер."""
    if not isinstance(graph, dict):
        raise ValueError("Тестовый JSON должен содержать объект со связями.")
    for name in graph:
        validate_node_name(name)
    result = {}
    for name, dependencies in graph.items():
        if not isinstance(dependencies, list):
            raise ValueError(f"Зависимости пакета {name} должны быть списком.")
        for dependency in dependencies:
            validate_node_name(dependency)
            if dependency not in graph:
                raise ValueError(
                    f"Пакет {dependency} не описан отдельным ключом."
                )
        result[name] = list(dict.fromkeys(dependencies))
    return result


def load_test_repository(filename):
    """Прочитать JSON в UTF-8, включая BOM, и проверить его граф."""
    try:
        text = Path(filename).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Тестовый файл должен быть в UTF-8.") from error
    except OSError as error:
        raise ValueError("Не удалось прочитать тестовый файл.") from error
    try:
        graph = json.loads(text, object_pairs_hook=unique_object)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Ошибка JSON: строка {error.lineno}, столбец {error.colno}."
        ) from error
    return validate_test_graph(graph)
