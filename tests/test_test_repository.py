"""Проверки JSON-репозитория с заглавными именами пакетов."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.test_repository import load_test_repository, validate_test_graph


class TestTestRepository(unittest.TestCase):
    """Проверить формат данных, ошибки и циклические связи."""

    def load_text(self, text, encoding="utf-8"):
        """Прочитать содержимое настоящего временного файла."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "repository.json"
            path.write_text(text, encoding=encoding)
            return load_test_repository(path)

    def test_valid_graph(self):
        """Прочитать несколько имён и удалить повторяющееся ребро."""
        self.assertEqual(
            self.load_text('{"A": ["BC", "BC"], "BC": []}'),
            {"A": ["BC"], "BC": []}
        )

    def test_bom(self):
        """Разрешить UTF-8 с маркером BOM."""
        self.assertEqual(self.load_text('{"A": []}', "utf-8-sig"), {"A": []})

    def test_cycles(self):
        """Разрешить цикл и ссылку вершины на себя."""
        graph = {"A": ["A", "B"], "B": ["A"]}
        self.assertEqual(self.load_text(json.dumps(graph)), graph)

    def test_empty_graph(self):
        """Разрешить пустой репозиторий для дальнейшей проверки корня."""
        self.assertEqual(self.load_text("{}"), {})

    def test_wrong_root_type(self):
        """Отклонить список, число и null вместо объекта со связями."""
        for value in ([], 1, None, "text"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "объект"):
                    self.load_text(json.dumps(value))

    def test_invalid_names(self):
        """Отклонить строчные, кириллические, числовые и пустые имена."""
        for name in ("a", "А", "A1", "", 1):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "A-Z"):
                    validate_test_graph({name: []})

    def test_invalid_dependencies(self):
        """Потребовать список допустимых имён в значении каждой записи."""
        for value in ("B", {}, None, [1], ["b"]):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_test_graph({"A": value})

    def test_missing_dependency(self):
        """Потребовать отдельный ключ для каждого соседа."""
        with self.assertRaisesRegex(ValueError, "B не описан"):
            self.load_text('{"A": ["B"]}')

    def test_duplicate_names(self):
        """Не терять повтор ключа при преобразовании JSON в словарь."""
        with self.assertRaisesRegex(ValueError, "повторяется"):
            self.load_text('{"A": [], "A": ["A"]}')

    def test_broken_json(self):
        """Показать положение синтаксической ошибки JSON."""
        with self.assertRaisesRegex(ValueError, "Ошибка JSON: строка"):
            self.load_text('{"A": [')

    def test_unreadable_file(self):
        """Преобразовать отказ доступа в ошибку приложения."""
        with patch("src.test_repository.Path.read_text", side_effect=OSError):
            with self.assertRaisesRegex(ValueError, "прочитать"):
                load_test_repository("unreadable.json")

    def test_invalid_encoding(self):
        """Обработать файл с неправильной кодировкой."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_bytes(b"\xff\xfeinvalid")
            with self.assertRaisesRegex(ValueError, "UTF-8"):
                load_test_repository(path)

    def test_input_unchanged(self):
        """Проверка и удаление повторов не должны менять входной словарь."""
        graph = {"A": ["B", "B"], "B": []}
        validate_test_graph(graph)
        self.assertEqual(graph["A"], ["B", "B"])


if __name__ == "__main__":
    unittest.main()
