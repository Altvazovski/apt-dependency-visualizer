"""Построение графа зависимостей рекурсивным BFS по уровням."""


def build_dependency_graph(root, get_dependencies, excluded_substring=""):
    """Получить достижимый граф, исключая пакеты по подстроке имени."""
    if excluded_substring and excluded_substring in root:
        return {}
    graph = {}
    discovered = {root}

    def visit_level(level):
        """Обработать весь текущий уровень и перейти к следующему."""
        if not level:
            return
        next_level = []
        for package in level:
            dependencies = list(dict.fromkeys(
                name for name in get_dependencies(package)
                if not excluded_substring or excluded_substring not in name
            ))
            graph[package] = dependencies
            for name in dependencies:
                if name not in discovered:
                    discovered.add(name)
                    next_level.append(name)
        visit_level(next_level)

    try:
        visit_level([root])
    except RecursionError as error:
        raise ValueError(
            "Граф слишком глубокий для рекурсивного BFS."
        ) from error
    return graph


def build_test_dependency_graph(repository, root, excluded_substring=""):
    """Применить BFS к предварительно проверенному тестовому словарю."""
    if root not in repository:
        raise ValueError(f"Пакет {root} отсутствует в тестовом репозитории.")
    return build_dependency_graph(
        root, repository.__getitem__, excluded_substring
    )
