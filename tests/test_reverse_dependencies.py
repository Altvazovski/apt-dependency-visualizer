"""Проверки обратных зависимостей и полного индекса Ubuntu."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from src.reverse_dependencies import (
    find_reverse_dependencies, get_apt_reverse_dependencies, reverse_graph
)


class TestReverseDependencies(unittest.TestCase):
    """Проверить обратные рёбра, уровни, циклы и фильтрацию."""

    def test_reverse_graph(self):
        """Развернуть рёбра и сохранить вершины без потребителей."""
        graph = {"A": ["B", "C"], "B": ["C"], "C": [], "X": []}
        self.assertEqual(reverse_graph(graph), {
            "A": [], "B": ["A"], "C": ["A", "B"], "X": []
        })

    def test_transitive_bfs_order(self):
        """Найти прямых потребителей раньше транзитивного потребителя."""
        graph = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
        self.assertEqual(
            find_reverse_dependencies(graph, "D"), ["B", "C", "A"]
        )

    def test_all_consumers(self):
        """Найти обе группы потребителей выбранного пакета."""
        graph = {"A": ["B"], "B": [], "X": ["B"], "Y": ["X"]}
        self.assertEqual(find_reverse_dependencies(graph, "B"), ["A", "X", "Y"])

    def test_cycle(self):
        """Завершить обход цикла и исключить саму цель из ответа."""
        graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
        self.assertEqual(find_reverse_dependencies(graph, "A"), ["C", "B"])

    def test_self_reference(self):
        """Сохранить ребро к себе, но не считать корень своим потребителем."""
        graph = {"A": ["A"], "B": ["A"]}
        self.assertEqual(reverse_graph(graph), {"A": ["A", "B"], "B": []})
        self.assertEqual(find_reverse_dependencies(graph, "A"), ["B"])

    def test_no_consumers(self):
        """Вернуть пустой список для обычного и изолированного корня."""
        graph = {"A": ["B"], "B": [], "X": []}
        self.assertEqual(find_reverse_dependencies(graph, "A"), [])
        self.assertEqual(find_reverse_dependencies(graph, "X"), [])

    def test_missing_target(self):
        """Обработать отсутствие цели, включая пустой репозиторий."""
        for graph in ({}, {"B": []}):
            with self.subTest(graph=graph):
                with self.assertRaisesRegex(ValueError, "A отсутствует"):
                    find_reverse_dependencies(graph, "A")

    def test_filter_stops_path(self):
        """Не находить транзитивного потребителя через исключённую вершину."""
        graph = {"A": ["B"], "B": ["C"], "C": []}
        self.assertEqual(find_reverse_dependencies(graph, "C", "B"), [])

    def test_filter_alternative_path(self):
        """Сохранить потребителя при наличии другой разрешённой ветки."""
        graph = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
        self.assertEqual(
            find_reverse_dependencies(graph, "D", "B"), ["C", "A"]
        )

    def test_filtered_target(self):
        """Вернуть пустой результат при исключении самой цели."""
        graph = {"A": ["B"], "B": []}
        self.assertEqual(find_reverse_dependencies(graph, "B", "B"), [])

    def test_filter_case_and_empty(self):
        """Учитывать регистр и разрешать пустой фильтр."""
        graph = {"A": ["B"], "B": []}
        self.assertEqual(find_reverse_dependencies(graph, "B", ""), ["A"])
        self.assertEqual(find_reverse_dependencies(graph, "B", "a"), ["A"])

    def test_duplicates_and_implicit_leaf(self):
        """Не повторять потребителя и разрешить цель без собственного ключа."""
        graph = {"A": ["B", "B"]}
        self.assertEqual(reverse_graph(graph), {"A": [], "B": ["A"]})
        self.assertEqual(find_reverse_dependencies(graph, "B"), ["A"])

    def test_original_unchanged(self):
        """Не менять исходные списки и ключи во время обратного обхода."""
        graph = {"A": ["B", "B"], "B": []}
        original = deepcopy(graph)
        find_reverse_dependencies(graph, "B")
        self.assertEqual(graph, original)


class TestAptReverseDependencies(unittest.TestCase):
    """Проверить обработку всего выбранного индекса в режиме Ubuntu."""

    def test_whole_index(self):
        """Найти потребителей, отсутствующих в прямом обходе от цели."""
        records = {
            "target": {}, "alpha": {"depends": "target"},
            "beta": {"depends": "alpha"}, "other": {}
        }
        with patch(
            "src.reverse_dependencies.load_apt_repository", return_value=records
        ) as load:
            result = get_apt_reverse_dependencies(
                "https://example.com", "target"
            )
        self.assertEqual(result, ["alpha", "beta"])
        load.assert_called_once_with("https://example.com")

    def test_virtual_target(self):
        """Разрешить виртуальную цель, упомянутую в обязательной связи."""
        records = {
            "base": {"pre-depends": "awk"}, "other": {"depends": "base"}
        }
        with patch(
            "src.reverse_dependencies.load_apt_repository", return_value=records
        ):
            self.assertEqual(
                get_apt_reverse_dependencies("https://example.com", "awk"),
                ["base", "other"]
            )

    def test_alternatives_and_cycles(self):
        """Учитывать каждую альтернативу и завершать циклический обход."""
        records = {
            "alpha": {"depends": "first | second"},
            "first": {}, "second": {"depends": "alpha"}
        }
        with patch(
            "src.reverse_dependencies.load_apt_repository", return_value=records
        ):
            self.assertEqual(
                get_apt_reverse_dependencies("https://example.com", "second"),
                ["alpha"]
            )

    def test_filter_before_dependency_parsing(self):
        """Не разбирать повреждённые зависимости исключённого пакета."""
        records = {
            "target": {}, "bad": {"depends": "invalid |"},
            "good": {"depends": "target"}
        }
        with patch(
            "src.reverse_dependencies.load_apt_repository", return_value=records
        ):
            self.assertEqual(
                get_apt_reverse_dependencies(
                    "https://example.com", "target", "bad"
                ),
                ["good"]
            )

    def test_filtered_target_no_download(self):
        """Не загружать индекс для исключённого целевого пакета."""
        with patch("src.reverse_dependencies.load_apt_repository") as load:
            self.assertEqual(
                get_apt_reverse_dependencies(
                    "https://example.com", "bash", "bash"
                ),
                []
            )
        load.assert_not_called()

    def test_missing_target(self):
        """Не выдавать отсутствие имени в индексе за отсутствие потребителей."""
        with patch(
            "src.reverse_dependencies.load_apt_repository",
            return_value={"demo": {}}
        ):
            with self.assertRaisesRegex(ValueError, "unknown отсутствует"):
                get_apt_reverse_dependencies("https://example.com", "unknown")

    def test_invalid_target_no_download(self):
        """Проверить имя цели до обращения к репозиторию."""
        with patch("src.reverse_dependencies.load_apt_repository") as load:
            with self.assertRaisesRegex(ValueError, "Некорректное имя"):
                get_apt_reverse_dependencies("https://example.com", "Bad")
        load.assert_not_called()

    def test_load_failure(self):
        """Передать ошибку загрузки вызывающему коду."""
        with patch(
            "src.reverse_dependencies.load_apt_repository",
            side_effect=ValueError("Ошибка сети")
        ):
            with self.assertRaisesRegex(ValueError, "Ошибка сети"):
                get_apt_reverse_dependencies("https://example.com", "bash")


if __name__ == "__main__":
    unittest.main()
