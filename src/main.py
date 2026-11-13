"""Командная строка визуализатора зависимостей Ubuntu: этап 5."""

import argparse
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


if __package__:
    from .d2_visualization import generate_d2
    from .apt_graph import build_apt_dependency_graph
    from .dependency_graph import build_test_dependency_graph
    from .reverse_dependencies import (
        find_reverse_dependencies, get_apt_reverse_dependencies
    )
    from .test_repository import load_test_repository
else:
    from d2_visualization import generate_d2
    from apt_graph import build_apt_dependency_graph
    from dependency_graph import build_test_dependency_graph
    from reverse_dependencies import (
        find_reverse_dependencies, get_apt_reverse_dependencies
    )
    from test_repository import load_test_repository


SUCCESS = 0
RUNTIME_ERROR = 1


def validate_package(value, test_mode):
    """Проверить имя Ubuntu-пакета или тестовой вершины."""
    # В тестовом репозитории используются заглавные латинские буквы.
    pattern = r"[A-Z]+" if test_mode else r"[a-z0-9][a-z0-9+.-]+"
    if re.fullmatch(pattern, value):
        return
    if test_mode:
        raise ValueError("--package: нужны заглавные буквы A-Z.")
    raise ValueError(
        "--package: нужны минимум два символа: строчные буквы a-z, "
        "цифры, '+', '-' или '.'; первый символ — буква или цифра."
    )


def validate_url(value):
    """Проверить схему, наличие узла, порт и символы URL."""
    if any(char.isspace() or not char.isprintable() for char in value):
        raise ValueError("--repository: URL содержит недопустимые символы.")
    try:
        address = urlsplit(value)
        # Свойство port дополнительно проверяет формат и диапазон порта.
        _ = address.port
    except ValueError as error:
        raise ValueError("--repository: некорректный URL или порт.") from error
    if address.scheme not in ("http", "https") or not address.hostname:
        raise ValueError("--repository: нужен полный URL HTTP или HTTPS.")


def validate_file(value):
    """Проверить существование и доступность тестового файла."""
    path = Path(value)
    try:
        if not path.is_file():
            raise ValueError("--repository: тестовый файл не найден.")
        # Содержимое графа отдельно проверяет загрузчик JSON.
        with path.open("rb"):
            pass
    except OSError as error:
        raise ValueError("--repository: не удалось открыть файл.") from error


def validate_filter(value):
    """Разрешить пустой фильтр или подстроку без управляющих символов."""
    if value and (not value.strip() or not value.isprintable()):
        raise ValueError(
            "--filter: нужна подстрока без управляющих символов; "
            "значение только из пробелов недопустимо."
        )


def validate_args(args):
    """Проверить настройки с учётом выбранного источника данных."""
    validate_package(args.package, args.test_mode)
    if args.test_mode:
        validate_file(args.repository)
    else:
        validate_url(args.repository)
    validate_filter(args.filter)


def parse_args(argv=None):
    """Прочитать параметры варианта 14 и режим обратного поиска."""
    parser = argparse.ArgumentParser(
        description="Визуализатор зависимостей Ubuntu/apt: этап 5.",
        allow_abbrev=False
    )
    parser.add_argument(
        "--package", required=True, help="Имя анализируемого пакета"
    )
    parser.add_argument(
        "--repository", required=True,
        help="URL репозитория или путь к тестовому файлу"
    )
    # Переключатель включается самим присутствием в командной строке.
    parser.add_argument(
        "--test-mode", action="store_true",
        help="Использовать локальный тестовый репозиторий"
    )
    parser.add_argument(
        "--filter", default="", help="Подстрока для исключения пакетов"
    )
    parser.add_argument(
        "--reverse", action="store_true",
        help="Вывести пакеты, зависящие от указанного --package"
    )
    args = parser.parse_args(argv)
    try:
        validate_args(args)
    except ValueError as error:
        parser.error(str(error))
    return args


def print_graph(root, graph):
    """Вывести только D2: комментарий с корнем, вершины и связи."""
    print(f"# Граф зависимостей для {root}")
    print(generate_d2(graph))


def print_reverse_dependencies(package, packages, excluded_substring=""):
    """Вывести потребителей, отсутствие результата или исключение цели."""
    print(f"Обратные зависимости для {package}:")
    if excluded_substring and excluded_substring in package:
        print("Целевой пакет исключён фильтром.")
    elif not packages:
        print("Обратных зависимостей в выбранном репозитории нет.")
    else:
        for name in packages:
            print(f"- {name}")


def run_test_mode(args):
    """Прочитать JSON и выполнить прямой или обратный обход."""
    repository = load_test_repository(args.repository)
    if args.reverse:
        packages = find_reverse_dependencies(
            repository, args.package, args.filter
        )
        print_reverse_dependencies(args.package, packages, args.filter)
        return
    graph = build_test_dependency_graph(repository, args.package, args.filter)
    print_graph(args.package, graph)


def run_apt_mode(args):
    """Загрузить индекс Ubuntu и выполнить выбранный поиск."""
    if args.reverse:
        packages = get_apt_reverse_dependencies(
            args.repository, args.package, args.filter
        )
        print_reverse_dependencies(args.package, packages, args.filter)
        return
    graph = build_apt_dependency_graph(
        args.repository, args.package, args.filter
    )
    print_graph(args.package, graph)


def main(argv=None):
    """Выполнить выбранную операцию и вернуть код завершения."""
    args = parse_args(argv)
    try:
        if args.test_mode:
            run_test_mode(args)
        else:
            run_apt_mode(args)
    except ValueError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return RUNTIME_ERROR
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
