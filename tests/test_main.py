"""Проверки параметров, вывода зависимостей и ошибок второго этапа."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.main import RUNTIME_ERROR, SUCCESS, main, parse_args, validate_file


CLI_ERROR = 2


class TestCommandLine(unittest.TestCase):
    """Проверить настройки, ошибки всех параметров и вывод прототипа."""

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

    def run_application(self, args=None, dependencies=None, error=None):
        """Запустить CLI с подменой загрузки и перехватом обоих потоков."""
        output, errors = io.StringIO(), io.StringIO()
        with patch(
            "src.main.get_direct_dependencies", side_effect=error,
            return_value=[] if dependencies is None else dependencies
        ) as load:
            with redirect_stdout(output), redirect_stderr(errors):
                code = main(self.args if args is None else args)
        return code, output.getvalue(), errors.getvalue(), load

    def test_default_settings(self):
        """Прочитать обязательные параметры и значения по умолчанию."""
        args = parse_args(self.args)
        self.assertEqual(args.package, "bash")
        self.assertEqual(args.repository, "https://archive.ubuntu.com/ubuntu")
        self.assertFalse(args.test_mode)
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
        """Отклонить значение после флага тестового режима."""
        self.assert_cli_error(self.args + ["--test-mode=false"], "--test-mode")

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
        """Вывести все прямые зависимости с их типами и условиями."""
        dependencies = [
            ("Pre-Depends", "libc6 (>= 2.34)"),
            ("Depends", "helper | other")
        ]
        code, output, errors, load = self.run_application(
            dependencies=dependencies
        )
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertEqual(output.splitlines(), [
            "Прямые зависимости пакета bash:",
            "Pre-Depends: libc6 (>= 2.34)", "Depends: helper | other"
        ])
        load.assert_called_once_with(
            "https://archive.ubuntu.com/ubuntu", "bash"
        )

    def test_no_dependencies(self):
        """Сообщить об отсутствии обязательных прямых зависимостей."""
        code, output, errors, _ = self.run_application()
        self.assertEqual(code, SUCCESS)
        self.assertEqual(errors, "")
        self.assertEqual(output.splitlines(), [
            "Прямые зависимости пакета bash:",
            "Обязательных прямых зависимостей нет."
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

    def test_test_mode_is_next_stage(self):
        """Не передавать локальный JSON загрузчику реального репозитория."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            path.write_text('{"A": []}', encoding="utf-8")
            code, output, errors, load = self.run_application([
                "--package", "A", "--repository", str(path), "--test-mode"
            ])
        self.assertEqual(code, RUNTIME_ERROR)
        self.assertEqual(output, "")
        self.assertIn("этапе 3", errors)
        load.assert_not_called()

    def test_filter_does_not_hide_direct_dependencies(self):
        """На этапе 2 вывести все прямые зависимости независимо от фильтра."""
        code, output, _, _ = self.run_application(
            self.args + ["--filter", "lib"], [("Depends", "libc6")]
        )
        self.assertEqual(code, SUCCESS)
        self.assertIn("Depends: libc6", output)

    def test_help(self):
        """Показать справку и успешно завершить работу."""
        with redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as result:
                parse_args(["--help"])
        self.assertEqual(result.exception.code, SUCCESS)
        for option in ("--package", "--repository", "--test-mode", "--filter"):
            self.assertIn(option, output.getvalue())


if __name__ == "__main__":
    unittest.main()
