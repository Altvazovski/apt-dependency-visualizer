"""Проверки обратного поиска через интерфейс командной строки."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.main import RUNTIME_ERROR, SUCCESS, main, parse_args


class TestReverseCli(unittest.TestCase):
    """Проверить переключение режима, вывод потребителей и ошибки."""

    @property
    def args(self):
        """Вернуть независимый набор параметров обратного поиска Ubuntu."""
        return [
            "--package", "bash", "--repository", "https://example.com",
            "--reverse"
        ]

    def run_application(self, args, packages=None, error=None):
        """Перехватить вывод и заменить реальный обратный поиск."""
        output, errors = io.StringIO(), io.StringIO()
        with patch(
            "src.main.get_apt_reverse_dependencies", side_effect=error,
            return_value=[] if packages is None else packages
        ) as reverse:
            with patch("src.main.build_apt_dependency_graph") as forward:
                with redirect_stdout(output), redirect_stderr(errors):
                    code = main(args)
        return (
            code, output.getvalue().splitlines(), errors.getvalue(),
            reverse, forward
        )

    def run_repository(self, graph, package, options=None):
        """Выполнить настоящий обратный поиск по временному JSON."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            path.write_text(json.dumps(graph), encoding="utf-8")
            args = [
                "--package", package, "--repository", str(path),
                "--test-mode", "--reverse"
            ]
            args.extend([] if options is None else options)
            return self.run_application(args)

    def test_json_bfs(self):
        """Вывести прямых и транзитивных потребителей без сети."""
        graph = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
        code, output, errors, reverse, forward = self.run_repository(graph, "D")
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output, [
            "Обратные зависимости для D:", "- B", "- C", "- A"
        ])
        self.assertEqual(errors, "")
        reverse.assert_not_called()
        forward.assert_not_called()

    def test_json_cycle(self):
        """Сохранить потребителей цикла, исключив саму цель из результата."""
        graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
        code, output, _, _, _ = self.run_repository(graph, "A")
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output, ["Обратные зависимости для A:", "- C", "- B"])

    def test_json_filter(self):
        """Сохранить путь к A через C после исключения B."""
        graph = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
        code, output, _, _, _ = self.run_repository(
            graph, "D", ["--filter", "B"]
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output, ["Обратные зависимости для D:", "- C", "- A"])

    def test_json_no_consumers(self):
        """Показать отсутствие потребителей без ошибки приложения."""
        code, output, _, _, _ = self.run_repository({"A": ["B"], "B": []}, "A")
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output, [
            "Обратные зависимости для A:",
            "Обратных зависимостей в выбранном репозитории нет."
        ])

    def test_json_missing_target(self):
        """Сообщить об отсутствии цели без частичного вывода результата."""
        code, output, errors, _, _ = self.run_repository({"A": []}, "Z")
        self.assertEqual(code, RUNTIME_ERROR)
        self.assertEqual(output, [])
        self.assertIn("Z отсутствует", errors)
        self.assertNotIn("Traceback", errors)

    def test_filtered_json_target(self):
        """Отличить исключённый пакет от пакета без потребителей."""
        code, output, _, _, _ = self.run_repository(
            {"A": []}, "A", ["--filter", "A"]
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output[-1], "Целевой пакет исключён фильтром.")

    def test_apt_mode_and_filter(self):
        """Передать настройки обратному загрузчику вместо прямого обхода."""
        code, output, errors, reverse, forward = self.run_application(
            self.args + ["--filter", "lib"], ["first", "second"]
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertEqual(output, [
            "Обратные зависимости для bash:", "- first", "- second"
        ])
        reverse.assert_called_once_with("https://example.com", "bash", "lib")
        forward.assert_not_called()

    def test_apt_no_consumers(self):
        """Вывести отсутствие результата в реальном режиме."""
        code, output, errors, _, _ = self.run_application(self.args)
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertEqual(
            output[-1], "Обратных зависимостей в выбранном репозитории нет."
        )

    def test_apt_failure(self):
        """Обработать ошибку реального индекса без трассировки."""
        code, output, errors, _, _ = self.run_application(
            self.args, error=ValueError("Ошибка сети")
        )
        self.assertEqual(code, RUNTIME_ERROR)
        self.assertEqual(output, [])
        self.assertIn("Ошибка сети", errors)
        self.assertNotIn("Traceback", errors)

    def test_filtered_apt_target(self):
        """Показать исключение цели в режиме реального репозитория."""
        code, output, _, _, _ = self.run_application(
            self.args + ["--filter", "bash"]
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output[-1], "Целевой пакет исключён фильтром.")

    def test_reverse_is_flag(self):
        """Проверить включение режима самим присутствием флага."""
        self.assertTrue(parse_args(self.args).reverse)


if __name__ == "__main__":
    unittest.main()
