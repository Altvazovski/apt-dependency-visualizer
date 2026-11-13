"""Проверки сохранения структуры графа в описании D2."""

from contextlib import redirect_stderr, redirect_stdout
import io
import unittest
from unittest.mock import patch

from src.d2_visualization import generate_d2
from src.main import main


class TestD2Visualization(unittest.TestCase):
    """Проверить вершины, подписи, циклы и повторяющиеся связи."""

    def test_empty_graph(self):
        """Получить корректный текст D2 при исключении всего графа."""
        self.assertEqual(generate_d2({}),
                         "direction: right\n# Граф пуст после фильтрации.")

    def test_isolated_nodes(self):
        """Сохранить вершины, у которых нет ни одного ребра."""
        self.assertEqual(generate_d2({"A": [], "B": []}).splitlines(), [
            "direction: right", 'n0: "A"', 'n1: "B"'
        ])

    def test_shared_dependency_and_cycle(self):
        """Сохранить общую зависимость и замыкающее цикл ребро."""
        graph = {"A": ["B", "C"], "B": ["C"], "C": ["A"]}
        self.assertEqual(generate_d2(graph).splitlines(), [
            "direction: right", 'n0: "A"', 'n1: "B"', 'n2: "C"',
            "n0 -> n1", "n0 -> n2", "n1 -> n2", "n2 -> n0"
        ])

    def test_self_reference_and_duplicate(self):
        """Оставить единственную петлю при повторении зависимости."""
        self.assertEqual(generate_d2({"A": ["A", "A"]}).splitlines(), [
            "direction: right", 'n0: "A"', "n0 -> n0"
        ])

    def test_missing_dependency_record(self):
        """Объявить подпись зависимости без собственной записи."""
        self.assertEqual(generate_d2({"base-files": ["awk"]}).splitlines(), [
            "direction: right", 'n0: "base-files"', 'n1: "awk"', "n0 -> n1"
        ])

    def test_package_labels_are_not_keys(self):
        """Не превращать точки и зарезервированные слова в синтаксис D2."""
        graph = {"direction": ["libstdc++6", "python3.12", "n0"]}
        lines = generate_d2(graph).splitlines()
        self.assertEqual(lines[1:5], [
            'n0: "direction"', 'n1: "libstdc++6"',
            'n2: "python3.12"', 'n3: "n0"'
        ])
        self.assertEqual(lines[5:], ["n0 -> n1", "n0 -> n2", "n0 -> n3"])

    def test_input_is_unchanged(self):
        """Не менять исходные связи при генерации описания."""
        graph = {"A": ["B", "B"], "B": []}
        generate_d2(graph)
        self.assertEqual(graph, {"A": ["B", "B"], "B": []})

    def test_packages_to_cli_d2(self):
        """Пройти от HTTP-индекса до D2 с виртуальным именем и циклом."""
        index = (
            b"Package: bash\nDepends: helper, virtual\n\n"
            b"Package: helper\nPre-Depends: bash\n\n"
        )
        output, errors = io.StringIO(), io.StringIO()
        with patch("src.apt_graph.download_index", return_value=index) as load:
            with redirect_stdout(output), redirect_stderr(errors):
                code = main([
                    "--package", "bash", "--repository",
                    "https://archive.ubuntu.com/ubuntu"
                ])
        self.assertEqual(code, 0)
        self.assertEqual(errors.getvalue(), "")
        load.assert_called_once_with(
            "https://archive.ubuntu.com/ubuntu/"
            "dists/noble/main/binary-amd64/Packages.xz"
        )
        self.assertEqual(output.getvalue().splitlines(), [
            "# Граф зависимостей для bash", "direction: right",
            'n0: "bash"', 'n1: "helper"', 'n2: "virtual"',
            "n0 -> n1", "n0 -> n2", "n1 -> n0"
        ])


if __name__ == "__main__":
    unittest.main()
