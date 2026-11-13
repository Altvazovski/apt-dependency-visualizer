"""Проверки графа объявленных зависимостей Ubuntu Packages."""

import gzip
import unittest
from unittest.mock import patch

from src.apt_graph import (
    build_apt_dependency_graph, get_dependency_names, read_repository
)


class TestAptGraph(unittest.TestCase):
    """Проверить загрузку одного индекса, альтернативы и неизвестные имена."""

    def test_dependency_names(self):
        """Извлечь все альтернативы, убирая версии и уточнения архитектуры."""
        record = {
            "pre-depends": "libc6:any (>= 2.38)",
            "depends": "helper | other:amd64 (<< 1:2.0-3), helper"
        }
        self.assertEqual(
            get_dependency_names(record), ["libc6", "helper", "other"]
        )

    def test_invalid_alternative(self):
        """Отклонить пустую альтернативу или недопустимое имя зависимости."""
        for expression in ("helper |", "helper || other", "Bad", "a"):
            with self.subTest(expression=expression):
                with self.assertRaisesRegex(ValueError, "Некорректная"):
                    get_dependency_names({"depends": expression})

    def test_read_repository(self):
        """Разобрать записи один раз и проиндексировать их по имени."""
        text = "Package: demo\nDepends: helper\n\nPackage: helper\n"
        records = read_repository(text)
        self.assertEqual(list(records), ["demo", "helper"])
        self.assertEqual(records["demo"]["depends"], "helper")

    def test_duplicate_record(self):
        """Не выбирать произвольную запись при неоднозначном индексе."""
        with self.assertRaisesRegex(ValueError, "Несколько записей"):
            read_repository("Package: demo\n\nPackage: demo\n")

    def test_invalid_package_field(self):
        """Требовать корректное поле Package у каждой записи индекса."""
        for text in ("Version: 1\n", "Package: Bad\n", "Package: a\n"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "поле Package"):
                    read_repository(text)

    def test_complete_graph_and_one_download(self):
        """Сохранить цикл, альтернативы и общую зависимость без перезагрузок."""
        data = gzip.compress(
            b"Package: demo\nPre-Depends: core\nDepends: left | right\n\n"
            b"Package: core\nDepends: demo\n\n"
            b"Package: left\nDepends: leaf\n\n"
            b"Package: right\nDepends: leaf\n\nPackage: leaf\n"
        )
        with patch("src.apt_graph.download_index", return_value=data) as load:
            graph = build_apt_dependency_graph("https://example.com", "demo")
        self.assertEqual(list(graph), ["demo", "core", "left", "right", "leaf"])
        self.assertEqual(graph, {
            "demo": ["core", "left", "right"], "core": ["demo"],
            "left": ["leaf"], "right": ["leaf"], "leaf": []
        })
        load.assert_called_once()

    def test_unknown_name_is_terminal(self):
        """Сохранить имя без записи, например виртуальный пакет, как лист."""
        data = b"Package: demo\nDepends: virtual-task\n"
        with patch("src.apt_graph.download_index", return_value=data):
            self.assertEqual(
                build_apt_dependency_graph("https://example.com", "demo"),
                {"demo": ["virtual-task"], "virtual-task": []}
            )

    def test_missing_root(self):
        """Отсутствие выбранного корня считать ошибкой, а не пустым графом."""
        with patch(
            "src.apt_graph.download_index", return_value=b"Package: other"
        ):
            with self.assertRaisesRegex(ValueError, "demo не найден"):
                build_apt_dependency_graph("https://example.com", "demo")

    def test_filtered_root_no_download(self):
        """Не обращаться к сети при исключении начального пакета."""
        with patch("src.apt_graph.download_index") as load:
            self.assertEqual(
                build_apt_dependency_graph(
                    "https://example.com", "demo", "dem"
                ),
                {}
            )
        load.assert_not_called()

    def test_filter_stops_parsing_branch(self):
        """Не анализировать зависимости исключённой вершины."""
        data = (
            b"Package: demo\nDepends: bad, good\n\n"
            b"Package: bad\nDepends: invalid |\n\nPackage: good\n"
        )
        with patch("src.apt_graph.download_index", return_value=data):
            self.assertEqual(
                build_apt_dependency_graph(
                    "https://example.com", "demo", "bad"
                ),
                {"demo": ["good"], "good": []}
            )

    def test_filter_names_only(self):
        """Не применять фильтр к тексту ограничений версий."""
        data = b"Package: demo\nDepends: helper (>= 1.0)\n\nPackage: helper\n"
        with patch("src.apt_graph.download_index", return_value=data):
            self.assertEqual(
                build_apt_dependency_graph(
                    "https://example.com", "demo", "1.0"
                ),
                {"demo": ["helper"], "helper": []}
            )

    def test_invalid_root_no_download(self):
        """Отклонить неправильное имя корня до загрузки индекса."""
        with patch("src.apt_graph.download_index") as load:
            with self.assertRaisesRegex(ValueError, "Некорректное имя"):
                build_apt_dependency_graph("https://example.com", "Bad")
        load.assert_not_called()

    def test_download_error(self):
        """Передать ошибку загрузки на уровень командной строки."""
        with patch(
            "src.apt_graph.download_index", side_effect=ValueError("Сеть")
        ):
            with self.assertRaisesRegex(ValueError, "Сеть"):
                build_apt_dependency_graph("https://example.com", "demo")


if __name__ == "__main__":
    unittest.main()
