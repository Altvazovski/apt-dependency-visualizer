"""Проверки параметров и вывода прямого графа зависимостей."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.main import RUNTIME_ERROR, SUCCESS, main, parse_args, validate_file


CLI_ERROR = 2


class TestCommandLine(unittest.TestCase):
    """Проверить настройки, ошибки параметров и вывод прямого графа."""

    def setUp(self):
        """Подготовить допустимый набор параметров реального репозитория."""
        self.args = [
            "--package", "bash",
            "--repository", "https://archive.ubuntu.com/ubuntu"
        ]

    def replace_option(self, option, value):
        """Заменить значение настройки в копии параметров."""
        args = self.args.copy()
        if option not in args:
            return args + [option, value]
        args[args.index(option) + 1] = value
        return args

    def assert_cli_error(self, args, option):
        """Проверить код ошибки и название неправильного параметра."""
        with redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as result:
                parse_args(args)
        self.assertEqual(result.exception.code, CLI_ERROR)
        self.assertIn(option, errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())

    def run_application(self, args=None, graph=None, error=None):
        """Запустить CLI с подменой графа Ubuntu и перехватом вывода."""
        output, errors = io.StringIO(), io.StringIO()
        with patch(
            "src.main.build_apt_dependency_graph", side_effect=error,
            return_value={"bash": []} if graph is None else graph
        ) as load:
            with redirect_stdout(output), redirect_stderr(errors):
                code = main(self.args if args is None else args)
        return code, output.getvalue(), errors.getvalue(), load

    def run_test_application(self, graph, options=None, raw_text=None):
        """Запустить тестовый режим с настоящим временным JSON-файлом."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            text = json.dumps(graph) if raw_text is None else raw_text
            path.write_text(text, encoding="utf-8")
            args = [
                "--package", "A", "--repository", str(path), "--test-mode"
            ]
            args.extend([] if options is None else options)
            return self.run_application(args)

    def test_default_settings(self):
        """Прочитать обязательные параметры и значения по умолчанию."""
        args = parse_args(self.args)
        self.assertEqual(args.package, "bash")
        self.assertEqual(args.repository, "https://archive.ubuntu.com/ubuntu")
        self.assertFalse(args.test_mode)
        self.assertFalse(args.reverse)
        self.assertEqual(args.filter, "")

    def test_valid_package_names(self):
        """Разрешить имена с цифрами, точками, дефисами и плюсами."""
        for name in ("bash", "libc6", "libstdc++6", "python3.12", "0ad"):
            with self.subTest(name=name):
                args = parse_args(self.replace_option("--package", name))
                self.assertEqual(args.package, name)

    def test_invalid_package_names(self):
        """Отклонить нарушение синтаксиса имён Ubuntu-пакетов."""
        for name in ("", "a", "Bash", "пакет", "my_pkg", "-bash", "ba sh"):
            with self.subTest(name=name):
                self.assert_cli_error(
                    self.replace_option("--package", name), "--package"
                )

    def test_valid_urls(self):
        """Принять HTTP, HTTPS и корректный явно заданный порт."""
        for url in ("http://example.com", "https://example.com:8443/index"):
            with self.subTest(url=url):
                args = parse_args(self.replace_option("--repository", url))
                self.assertEqual(args.repository, url)

    def test_invalid_urls(self):
        """Отклонить неполный адрес, неподходящую схему и ошибочный порт."""
        cases = (
            "", "archive.ubuntu.com", "ftp://example.com", "https://",
            "https://example.com:wrong", "https://example.com:65536",
            "https://[bad", "https://exam ple.com", "https://example.com\n"
        )
        for url in cases:
            with self.subTest(url=url):
                self.assert_cli_error(
                    self.replace_option("--repository", url), "--repository"
                )

    def test_filter_parameter(self):
        """Сохранить непустую подстроку фильтра без изменения регистра."""
        args = parse_args(self.args + ["--filter", "lib"])
        self.assertEqual(args.filter, "lib")

    def test_invalid_filter(self):
        """Отклонить пробельный фильтр и управляющие символы."""
        for value in (" ", "  ", "\t", "a\nb"):
            with self.subTest(value=value):
                self.assert_cli_error(
                    self.args + ["--filter", value], "--filter"
                )

    def test_missing_required_options(self):
        """Проверить отсутствие каждого обязательного параметра."""
        for option in ("--package", "--repository"):
            with self.subTest(option=option):
                args = self.args.copy()
                index = args.index(option)
                del args[index:index + 2]
                self.assert_cli_error(args, option)

    def test_missing_option_values(self):
        """Проверить отсутствие значения после параметра."""
        for option in ("--package", "--repository", "--filter"):
            with self.subTest(option=option):
                self.assert_cli_error(self.args + [option], option)

    def test_flag_does_not_accept_value(self):
        """Отклонить значения после переключателей режимов."""
        for option in ("--test-mode", "--reverse"):
            with self.subTest(option=option):
                self.assert_cli_error(self.args + [option + "=false"], option)

    def test_unknown_options(self):
        """Отклонить неизвестные параметры и сокращённые имена."""
        for options in (
            ["--unknown"], ["--pack", "bash"],
            ["--version", "1.0.0"], ["--ascii"]
        ):
            with self.subTest(options=options):
                self.assert_cli_error(self.args + options, options[0])

    def test_test_repository_settings(self):
        """Проверить путь с пробелом и параметры тестового режима."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "test graph.json"
            path.write_text('{"ABC": []}', encoding="utf-8")
            args = [
                "--package", "ABC", "--repository", str(path),
                "--test-mode", "--filter", "B"
            ]
            settings = parse_args(args)
            self.assertTrue(settings.test_mode)
            self.assertEqual(settings.package, "ABC")
            self.assertEqual(settings.repository, str(path))
            self.assertEqual(settings.filter, "B")

    def test_invalid_test_package_names(self):
        """Отклонить строчные буквы, цифры и знаки в тестовом имени."""
        for name in ("a", "A1", "A-B", "А", ""):
            with self.subTest(name=name):
                args = self.replace_option("--package", name)
                self.assert_cli_error(args + ["--test-mode"], "--package")

    def test_missing_test_repository(self):
        """Показать ошибку для отсутствующего файла тестового репозитория."""
        with TemporaryDirectory() as directory:
            args = [
                "--package", "A", "--test-mode",
                "--repository", str(Path(directory) / "missing.json")
            ]
            self.assert_cli_error(args, "--repository")

    def test_directory_instead_of_file(self):
        """Отклонить путь к папке вместо тестового файла."""
        with TemporaryDirectory() as directory:
            self.assert_cli_error([
                "--package", "A", "--test-mode", "--repository", directory
            ], "--repository")

    def test_unreadable_file(self):
        """Перевести отказ доступа к файлу в понятную ошибку параметра."""
        with patch("src.main.Path.is_file", return_value=True):
            with patch("src.main.Path.open", side_effect=PermissionError):
                with self.assertRaisesRegex(ValueError, "не удалось открыть"):
                    validate_file("private.json")

    def test_main_output(self):
        """Вывести связи реального графа, сохранив цикл и конечную вершину."""
        graph = {"bash": ["libc6", "helper"], "libc6": ["bash"], "helper": []}
        code, output, errors, load = self.run_application(graph=graph)
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertEqual(output.splitlines(), [
            "Граф зависимостей для bash:", "bash -> libc6, helper",
            "libc6 -> bash", "helper -> нет исходящих связей"
        ])
        load.assert_called_once_with(
            "https://archive.ubuntu.com/ubuntu", "bash", ""
        )

    def test_no_dependencies(self):
        """Сохранить корень графа без исходящих связей."""
        code, output, errors, _ = self.run_application()
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertEqual(output.splitlines(), [
            "Граф зависимостей для bash:", "bash -> нет исходящих связей"
        ])

    def test_runtime_error(self):
        """Вывести ошибку данных или загрузки в stderr без трассировки."""
        code, output, errors, _ = self.run_application(
            error=ValueError("Сервер недоступен")
        )
        self.assertEqual(code, RUNTIME_ERROR)
        self.assertEqual(output, "")
        self.assertIn("Ошибка: Сервер недоступен", errors)
        self.assertNotIn("Traceback", errors)

    def test_test_mode_graph(self):
        """Построить достижимый граф из JSON без сетевого обращения."""
        graph = {"A": ["B", "C"], "B": ["C"], "C": []}
        code, output, errors, load = self.run_test_application(graph)
        self.assertEqual(code, SUCCESS)
        self.assertEqual(output.splitlines(), [
            "Граф зависимостей для A:", "A -> B, C", "B -> C",
            "C -> нет исходящих связей"
        ])
        self.assertEqual(errors, "")
        load.assert_not_called()

    def test_apt_filter_parameter(self):
        """Передать подстроку фильтра построителю графа Ubuntu."""
        code, _, errors, load = self.run_application(
            self.args + ["--filter", "lib"]
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        load.assert_called_once_with(
            "https://archive.ubuntu.com/ubuntu", "bash", "lib"
        )

    def test_test_mode_cycle(self):
        """Сохранить циклические рёбра в выводе без зависания программы."""
        code, output, errors, _ = self.run_test_application({
            "A": ["A", "B"], "B": ["C"], "C": ["A"]
        })
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertEqual(output.splitlines(), [
            "Граф зависимостей для A:", "A -> A, B", "B -> C", "C -> A"
        ])

    def test_test_mode_filter(self):
        """Остановить обход ветки исключённой вершины."""
        graph = {"A": ["B", "C"], "B": ["D"], "C": [], "D": []}
        code, output, errors, _ = self.run_test_application(
            graph, ["--filter", "B"]
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertEqual(output.splitlines(), [
            "Граф зависимостей для A:", "A -> C", "C -> нет исходящих связей"
        ])

    def test_filtered_test_root(self):
        """Вывести пустой граф после исключения начальной вершины."""
        code, output, errors, _ = self.run_test_application(
            {"A": []}, ["--filter", "A"]
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertEqual(output.splitlines(), [
            "Граф зависимостей для A:", "После фильтрации граф пуст."
        ])

    def test_filtered_apt_root(self):
        """Вывести пустой граф реального пакета после фильтрации."""
        code, output, errors, _ = self.run_application(
            self.args + ["--filter", "bash"], graph={}
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertEqual(output.splitlines(), [
            "Граф зависимостей для bash:", "После фильтрации граф пуст."
        ])

    def test_missing_test_root(self):
        """Показать ошибку отсутствующего корня без частичного результата."""
        code, output, errors, _ = self.run_test_application({"B": []})
        self.assertEqual(code, RUNTIME_ERROR)
        self.assertEqual(output, "")
        self.assertIn("A отсутствует", errors)

    def test_invalid_test_json(self):
        """Обработать синтаксическую ошибку и повтор ключа JSON."""
        for text in ('{"A": [', '{"A": [], "A": []}'):
            with self.subTest(text=text):
                code, output, errors, _ = self.run_test_application(
                    {}, raw_text=text
                )
                self.assertEqual(code, RUNTIME_ERROR)
                self.assertEqual(output, "")
                self.assertIn("Ошибка:", errors)
                self.assertNotIn("Traceback", errors)

    def test_invalid_test_reference(self):
        """Сообщить о ссылке на пакет, не описанный в тестовом JSON."""
        code, output, errors, _ = self.run_test_application({"A": ["B"]})
        self.assertEqual(code, RUNTIME_ERROR)
        self.assertEqual(output, "")
        self.assertIn("B не описан", errors)

    def test_help(self):
        """Показать справку и успешно завершить работу."""
        with redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as result:
                parse_args(["--help"])
        self.assertEqual(result.exception.code, SUCCESS)
        for option in (
            "--package", "--repository", "--test-mode", "--filter", "--reverse"
        ):
            self.assertIn(option, output.getvalue())


if __name__ == "__main__":
    unittest.main()
