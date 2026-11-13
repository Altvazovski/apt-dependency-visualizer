"""Обход объявленных зависимостей одного индекса Ubuntu Packages."""

import re

if __package__:
    from .apt_repository import (
        decode_index, download_index, extract_dependencies,
        get_index_url, iter_package_records,
    )
    from .dependency_graph import build_dependency_graph
else:
    from apt_repository import (
        decode_index, download_index, extract_dependencies,
        get_index_url, iter_package_records,
    )
    from dependency_graph import build_dependency_graph


PACKAGE_PATTERN = re.compile(r"[a-z0-9][a-z0-9+.-]+")
DEPENDENCY_PATTERN = re.compile(
    r"(?P<name>[a-z0-9][a-z0-9+.-]+)"
    r"(?::[a-z0-9][a-z0-9-]*)?(?:\s*\([^()]+\))?"
)


def read_repository(text):
    """Создать словарь однозначных записей пакетов выбранного индекса."""
    repository = {}
    for record in iter_package_records(text):
        name = record.get("package", "")
        if not PACKAGE_PATTERN.fullmatch(name):
            raise ValueError(
                "В индексе отсутствует или некорректно поле Package."
            )
        if name in repository:
            raise ValueError(
                f"Несколько записей пакета {name}: нужен однозначный индекс."
            )
        repository[name] = record
    return repository


def load_apt_repository(repository):
    """Один раз загрузить и разобрать весь индекс для полного обхода."""
    data = download_index(get_index_url(repository))
    return read_repository(decode_index(data))


def get_dependency_names(record):
    """Извлечь имена всех альтернатив Depends и Pre-Depends без повторов."""
    names = []
    for kind, expression in extract_dependencies(record):
        for alternative in expression.split("|"):
            match = DEPENDENCY_PATTERN.fullmatch(alternative.strip())
            if not match:
                raise ValueError(
                    f"Некорректная зависимость {kind}: {expression}."
                )
            # Версия и уточнение архитектуры не являются частью имени вершины.
            names.append(match.group("name"))
    return list(dict.fromkeys(names))


def build_apt_dependency_graph(repository, root, excluded_substring=""):
    """Построить рекурсивным BFS граф объявленных зависимостей Ubuntu."""
    if not isinstance(root, str) or not PACKAGE_PATTERN.fullmatch(root):
        raise ValueError("Некорректное имя начального Ubuntu-пакета.")
    if excluded_substring and excluded_substring in root:
        return {}
    records = load_apt_repository(repository)
    if root not in records:
        raise ValueError(f"Пакет {root} не найден в указанном индексе.")

    def get_dependencies(name):
        """Прочитать соседей; имя без записи сохранить конечной вершиной."""
        return get_dependency_names(records.get(name, {}))

    return build_dependency_graph(root, get_dependencies, excluded_substring)
