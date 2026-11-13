"""Обратный поиск по полному тестовому репозиторию или индексу Ubuntu."""

if __package__:
    from .apt_graph import (
        PACKAGE_PATTERN, get_dependency_names, load_apt_repository
    )
    from .dependency_graph import build_dependency_graph
else:
    from apt_graph import (
        PACKAGE_PATTERN, get_dependency_names, load_apt_repository
    )
    from dependency_graph import build_dependency_graph


def reverse_graph(graph):
    """Развернуть рёбра, сохранив вершины и порядок прямых потребителей."""
    reversed_graph = {package: [] for package in graph}
    for package, dependencies in graph.items():
        for dependency in dict.fromkeys(dependencies):
            reversed_graph.setdefault(dependency, []).append(package)
    return reversed_graph


def find_reverse_dependencies(graph, package, excluded_substring=""):
    """Найти прямых и транзитивных потребителей прежним рекурсивным BFS."""
    reversed_graph = reverse_graph(graph)
    if package not in reversed_graph:
        raise ValueError(f"Пакет {package} отсутствует в графе репозитория.")
    reachable = build_dependency_graph(
        package, reversed_graph.__getitem__, excluded_substring
    )
    # Не выводим цель среди собственных потребителей даже при цикле.
    return [name for name in reachable if name != package]


def get_apt_reverse_dependencies(repository, package, excluded_substring=""):
    """Загрузить один индекс и найти всех известных в нём потребителей."""
    if not isinstance(package, str) or not PACKAGE_PATTERN.fullmatch(package):
        raise ValueError("Некорректное имя Ubuntu-пакета для обратного поиска.")
    if excluded_substring and excluded_substring in package:
        return []
    records = load_apt_repository(repository)
    graph = {}
    for name, record in records.items():
        if excluded_substring and excluded_substring in name:
            continue
        # Разбираем все разрешённые пакеты, а не только потомков цели.
        graph[name] = get_dependency_names(record)
    return find_reverse_dependencies(graph, package, excluded_substring)
