"""Проверки загрузки и чтения индекса Ubuntu Packages."""

import bz2
import gzip
from http.client import HTTPException
import lzma
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from src.apt_repository import (
    DEFAULT_INDEX, TIMEOUT, decode_index, download_index,
    extract_dependencies, find_package, get_direct_dependencies,
    get_index_url, iter_package_records,
)


class TestAptRepository(unittest.TestCase):
    """Проверить HTTP, сжатие, формат полей и обязательные зависимости."""

    def test_root_url(self):
        """Дополнить корень репозитория путём Ubuntu noble/main/amd64."""
        expected = "https://archive.ubuntu.com/ubuntu/" + DEFAULT_INDEX
        for url in (
            "https://archive.ubuntu.com/ubuntu",
            "https://archive.ubuntu.com/ubuntu/"
        ):
            with self.subTest(url=url):
                self.assertEqual(get_index_url(url), expected)

    def test_direct_index_url(self):
        """Сохранить полный URL обычного или сжатого Packages."""
        for filename in (
            "Packages", "Packages.gz", "Packages.xz", "Packages.bz2"
        ):
            with self.subTest(filename=filename):
                url = "https://example.com/index/" + filename + "?download=1"
                self.assertEqual(get_index_url(url), url)

    def test_ambiguous_root_url(self):
        """Не переносить параметры запроса или фрагмент на другой путь."""
        for url in ("https://example.com/?q=1", "https://example.com/#part"):
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, "URL корня"):
                    get_index_url(url)

    def test_download(self):
        """Передать серверу запрос с тайм-аутом и именем приложения."""
        with patch("src.apt_repository.urlopen") as open_url:
            response = open_url.return_value.__enter__.return_value
            response.read.return_value = b"ok"
            data = download_index("https://example.com/Packages")
            self.assertEqual(data, b"ok")
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.com/Packages")
        self.assertIn(
            "apt-dependency-visualizer", request.get_header("User-agent")
        )
        self.assertEqual(open_url.call_args.kwargs, {"timeout": TIMEOUT})

    def test_http_error(self):
        """Показать код ответа сервера при отсутствии индекса."""
        error = HTTPError("https://example.com", 404, "missing", {}, None)
        with patch("src.apt_repository.urlopen", side_effect=error):
            with self.assertRaisesRegex(ValueError, "HTTP 404"):
                download_index("https://example.com/Packages")

    def test_network_errors(self):
        """Обработать отсутствие сети, тайм-аут и обрыв HTTP-ответа."""
        cases = (URLError("offline"), TimeoutError(), HTTPException("cut"))
        for error in cases:
            with self.subTest(error=error):
                with patch("src.apt_repository.urlopen", side_effect=error):
                    with self.assertRaisesRegex(ValueError, "загрузить индекс"):
                        download_index("https://example.com/Packages")

    def test_index_encodings(self):
        """Прочитать UTF-8, в том числе с BOM, после разных видов сжатия."""
        text = "Package: bash\nDescription: описание\n"
        data = ("\ufeff" + text).encode("utf-8")
        for encoded in (data, gzip.compress(data), lzma.compress(data),
                        bz2.compress(data)):
            with self.subTest(signature=encoded[:6]):
                self.assertEqual(decode_index(encoded), text)

    def test_invalid_utf8(self):
        """Вывести понятную ошибку вместо трассировки декодирования."""
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            decode_index(b"\xff\xfeinvalid")

    def test_broken_compression(self):
        """Отклонить обрезанные данные каждого поддержанного формата."""
        for data in (b"\x1f\x8b", b"\xfd7zXZ\x00", b"BZh"):
            with self.subTest(data=data):
                with self.assertRaisesRegex(ValueError, "повреждён"):
                    decode_index(data)

    def test_records_and_continuations(self):
        """Разделить абзацы и сохранить продолжения полей с двоеточиями."""
        text = (
            "\r\nPackage: bash\r\nDepends: libc6,\r\n libtinfo6\r\n"
            "Description: first\r\n more: detail\r\n .\r\n\r\n"
            "Package: other\r\n"
        )
        records = list(iter_package_records(text))
        self.assertEqual(records, [
            {"package": "bash", "depends": "libc6,\nlibtinfo6",
             "description": "first\nmore: detail\n."},
            {"package": "other"}
        ])

    def test_field_names_are_case_insensitive(self):
        """Привести имена полей к одному регистру."""
        self.assertEqual(list(iter_package_records("PACKAGE: bash")), [
            {"package": "bash"}
        ])

    def test_duplicate_field(self):
        """Отклонить повтор поля, даже если меняется регистр его имени."""
        with self.assertRaisesRegex(ValueError, "повторяется"):
            list(iter_package_records("Package: bash\nPACKAGE: other"))

    def test_invalid_fields(self):
        """Отклонить строки без двоеточия и неверные имена полей."""
        for text in ("invalid", ": value", "Bad field: value", "#Bad: value"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "строке 1"):
                    list(iter_package_records(text))

    def test_orphan_continuation(self):
        """Не принимать продолжение строки без предшествующего поля."""
        with self.assertRaisesRegex(ValueError, "Продолжение"):
            list(iter_package_records(" Depends: libc6"))

    def test_empty_index(self):
        """Разрешить чтение пустого текста и пробельных разделителей."""
        self.assertEqual(list(iter_package_records("\n \t\n")), [])

    def test_exact_package_name(self):
        """Не путать выбранный пакет с похожим именем."""
        text = "Package: bash-doc\n\nPackage: bash\nVersion: 5.2\n"
        self.assertEqual(find_package(text, "bash")["version"], "5.2")

    def test_missing_package(self):
        """Сообщить об отсутствии выбранного пакета в индексе."""
        with self.assertRaisesRegex(ValueError, "bash не найден"):
            find_package("Package: other\n", "bash")

    def test_duplicate_package(self):
        """Потребовать однозначный индекс при нескольких записях пакета."""
        with self.assertRaisesRegex(ValueError, "Несколько записей"):
            find_package("Package: bash\n\nPackage: bash\n", "bash")

    def test_dependency_groups(self):
        """Сохранить альтернативы, условия версий и уточнение архитектуры."""
        record = {
            "pre-depends": "libc6 (>= 2.34)",
            "depends": "libone:any (>= 1:2.0-3) | libtwo,\n helper"
        }
        self.assertEqual(extract_dependencies(record), [
            ("Pre-Depends", "libc6 (>= 2.34)"),
            ("Depends", "libone:any (>= 1:2.0-3) | libtwo"),
            ("Depends", "helper")
        ])

    def test_optional_relationships(self):
        """Отделить обязательные зависимости от рекомендаций и конфликтов."""
        self.assertEqual(extract_dependencies({
            "recommends": "extra", "suggests": "docs", "conflicts": "other"
        }), [])

    def test_no_dependencies(self):
        """Вернуть пустой список для пакета без обязательных зависимостей."""
        self.assertEqual(extract_dependencies({"package": "leaf"}), [])

    def test_empty_dependency_group(self):
        """Отклонить пустое поле и лишнюю запятую в списке зависимостей."""
        for value in ("", "libc6,", ",libc6", "libc6,,helper"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Пустая группа"):
                    extract_dependencies({"depends": value})

    def test_complete_pipeline(self):
        """Прочитать сжатый ответ и вернуть зависимости выбранного пакета."""
        data = lzma.compress(b"Package: bash\nDepends: libc6 | other\n")
        with patch(
            "src.apt_repository.download_index", return_value=data
        ) as load:
            result = get_direct_dependencies("https://example.com", "bash")
        self.assertEqual(result, [("Depends", "libc6 | other")])
        load.assert_called_once_with("https://example.com/" + DEFAULT_INDEX)


if __name__ == "__main__":
    unittest.main()
