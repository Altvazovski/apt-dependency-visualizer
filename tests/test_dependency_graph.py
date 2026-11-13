"""Проверки рекурсивного BFS, циклов и фильтрации графа."""

import sys
import unittest
from unittest.mock import Mock

from src.dependency_graph import (
    build_dependency_graph, build_test_dependency_graph
)


class TestDependencyGraph(unittest.TestCase):
    """Проверить порядок уровней и однократную обработку вершин."""

    def test_breadth_first_order(self):
        """Обработать весь уровень до перехода к потомкам следующего уровня."""
        source = {
            "A": ["B", "C"], "B": ["D"], "C": ["E"], "D": [], "E": []
        }
        loader = Mock(side_effect=source.__getitem__)
        graph = build_dependency_graph("A", loader)
        expected = ["A", "B", "C", "D", "E"]
        self.assertEqual(list(graph), expected)
        self.assertEqual(
            [call.args[0] for call in loader.call_args_list], expected
        )
        self.assertEqual(graph, source)

    def test_shared_dependency(self):
        """Получить соседей общей вершины один раз, сохранив оба ребра."""
        source = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
        loader = Mock(side_effect=source.__getitem__)
        self.assertEqual(build_dependency_graph("A", loader), source)
        self.assertEqual(loader.call_count, len(source))

    def test_cycle_and_self_reference(self):
        """Сохранить цикл и ссылку на себя без повторной загрузки вершины."""
        source = {"A": ["A", "B"], "B": ["C"], "C": ["A"]}
        loader = Mock(side_effect=source.__getitem__)
        self.assertEqual(build_dependency_graph("A", loader), source)
        self.assertEqual(loader.call_count, len(source))

    def test_filter_stops_branch(self):
        """Не загружать исключённую вершину и её недостижимого потомка."""
        source = {"A": ["B", "C"], "B": ["D"], "C": [], "D": []}
        loader = Mock(side_effect=source.__getitem__)
        self.assertEqual(
            build_dependency_graph("A", loader, "B"), {"A": ["C"], "C": []}
        )
        self.assertEqual(
            [call.args[0] for call in loader.call_args_list], ["A", "C"]
        )

    def test_alternative_path(self):
        """Сохранить потомка, доступного через другую разрешённую ветку."""
        source = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
        self.assertEqual(
            build_test_dependency_graph(source, "A", "B"),
            {"A": ["C"], "C": ["D"], "D": []}
        )

    def test_filtered_root(self):
        """Вернуть пустой граф без вызова загрузчика исключённого корня."""
        loader = Mock()
        self.assertEqual(build_dependency_graph("ABC", loader, "B"), {})
        loader.assert_not_called()

    def test_empty_filter_and_case(self):
        """Разрешить пустой фильтр и учитывать регистр подстроки."""
        source = {"A": ["B"], "B": []}
        self.assertEqual(build_test_dependency_graph(source, "A", ""), source)
        self.assertEqual(build_test_dependency_graph(source, "A", "b"), source)

    def test_unreachable_packages(self):
        """Не включать отдельную компоненту связности в достижимый граф."""
        source = {"A": ["B"], "B": [], "X": ["Y"], "Y": []}
        self.assertEqual(
            build_test_dependency_graph(source, "A"), {"A": ["B"], "B": []}
        )

    def test_isolated_root(self):
        """Сохранить вершину без зависимостей."""
        self.assertEqual(build_test_dependency_graph({"A": []}, "A"), {"A": []})

    def test_missing_root(self):
        """Обработать отсутствие корня, включая пустой репозиторий."""
        for source in ({}, {"B": []}):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, "отсутствует"):
                    build_test_dependency_graph(source, "A")

    def test_duplicate_edges(self):
        """Удалить повтор рёбер, сохранив исходные списки без изменения."""
        source = {"A": ["B", "B"], "B": []}
        self.assertEqual(
            build_test_dependency_graph(source, "A"), {"A": ["B"], "B": []}
        )
        self.assertEqual(source["A"], ["B", "B"])

    def test_loader_error(self):
        """Передать ошибку источника данных вызывающему коду."""
        loader = Mock(side_effect=ValueError("Ошибка источника"))
        with self.assertRaisesRegex(ValueError, "Ошибка источника"):
            build_dependency_graph("A", loader)

    def test_wide_level(self):
        """Не создавать рекурсивный вызов для каждой вершины уровня."""
        children = [f"N{index}" for index in range(1500)]
        source = {"ROOT": children}
        source.update({child: [] for child in children})
        self.assertEqual(
            build_dependency_graph("ROOT", source.__getitem__), source
        )

    def test_recursion_limit(self):
        """Сообщить о слишком длинной цепочке понятной ошибкой."""
        depth = sys.getrecursionlimit() + 1

        def loader(node):
            """Получить очередное звено длинной цепочки."""
            return [node + 1] if node < depth else []

        with self.assertRaisesRegex(ValueError, "слишком глубокий"):
            build_dependency_graph(0, loader)


if __name__ == "__main__":
    unittest.main()
