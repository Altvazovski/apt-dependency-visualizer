"""Текстовое представление графа зависимостей на языке D2."""

import json


def generate_d2(graph):
    """Описать вершины и направленные связи без запуска визуализатора."""
    lines = ["direction: right"]
    if not graph:
        return "\n".join(lines + ["# Граф пуст после фильтрации."])

    # Отдельные ключи сохраняют точки и знаки '+' именно в подписях.
    names = dict.fromkeys(graph)
    for dependencies in graph.values():
        names.update(dict.fromkeys(dependencies))
    identifiers = {name: f"n{index}" for index, name in enumerate(names)}
    for name, identifier in identifiers.items():
        label = json.dumps(name, ensure_ascii=False)
        lines.append(f"{identifier}: {label}")

    # Повторное ребро D2 создаёт новую связь: удаляем повторы явно.
    for name, dependencies in graph.items():
        for dependency in dict.fromkeys(dependencies):
            lines.append(f"{identifiers[name]} -> {identifiers[dependency]}")
    return "\n".join(lines)
